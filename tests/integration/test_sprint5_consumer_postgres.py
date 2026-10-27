"""End-to-end consumer ordering, replay, resume, and brief freshness contracts."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

import staylead_platform.composition.dependencies.guest_chat as guest_chat_composition
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    apply_migrations,
    get_guest_brief,
    get_guest_brief_receipt,
)
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import (
    import_fixture_pack,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    Usage,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality" / "knowledge-v1"
TEST_DSN = os.environ.get("STAYLEAD_TEST_DATABASE_URL")
EDIT = "Please set my dates to May 10 through May 13, 2027 for two adults and one child age 9. Also, what are the breakfast hours?"
EDIT_LATER = "Please set my dates to May 11 through May 14, 2027 for two adults and one child age 9."


@pytest.fixture(scope="module")
def engine():
    if not TEST_DSN:
        pytest.skip("Set STAYLEAD_TEST_DATABASE_URL to an isolated Sprint 5 consumer PostgreSQL database.")
    database = create_database_engine(TEST_DSN)
    apply_migrations(database)
    import_fixture_pack(database, FIXTURE_ROOT)
    yield database
    database.dispose()


class BriefConsumerProvider:
    """Deterministic provider that can fail after the first durable edit commit."""

    def __init__(self, *, fail_final_answer_once: bool = False, unknown_usage: bool = False) -> None:
        self.calls = 0
        self.fail_final_answer_once = fail_final_answer_once
        self.unknown_usage = unknown_usage
        self.failed = False
        self.patch_proposed = False
        self.inputs: list[dict[str, Any]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        payload = json.loads(request.input_text)
        self.inputs.append({"instructions": request.instructions, **payload})
        question = payload.get("question", "")
        patch_enabled = payload.get("guest_brief_patch_enabled") is True
        operations = []
        if patch_enabled and "set my dates" in question.lower():
            if "May 11" in question:
                check_in, check_out = "2027-05-11", "2027-05-14"
            else:
                check_in, check_out = "2027-05-10", "2027-05-13"
            operations = [
                {"op": "set_dates", "check_in": check_in, "check_out": check_out},
                {"op": "set_adults", "count": 2},
                {"op": "add_child", "age": 9},
            ]

        if "candidate_index" in payload:
            candidates = payload.get("candidate_index", [])
            result: dict[str, Any] = {
                "fact_ids": [candidates[0]["fact_id"]] if candidates else [],
                "turn_intents": ["hotel_information", "guest_edit"] if operations else ["hotel_information"],
            }
            if operations:
                result["guest_patch"] = {"ops": operations}
                result["guest_patch_authorizations"] = [
                    {"operation_index": 0, "op": "set_dates", "target_fields": ["dates.check_in", "dates.check_out"],
                     "intent": "explicit_request", "current_turn_quote": "May 10 through May 13, 2027" if "May 11" not in question else "May 11 through May 14, 2027"},
                    {"operation_index": 1, "op": "set_adults", "target_fields": ["party.adults"],
                     "intent": "explicit_request", "current_turn_quote": "two adults"},
                    {"operation_index": 2, "op": "add_child", "target_fields": ["party.children"],
                     "intent": "explicit_request", "current_turn_quote": "one child age 9"},
                ]
                self.patch_proposed = True
            return self._result(result)

        if self.fail_final_answer_once and self.patch_proposed and not self.failed and not patch_enabled:
            self.failed = True
            raise ProviderError("provider_failure", "Synthetic post-commit provider failure.", retryable=True)

        if operations:
            result = {"supported_claims": [], "unknowns": ["Your trip details were saved."],
                      "conflicts": [], "guest_patch": {"ops": operations},
                      "turn_intents": ["hotel_information", "guest_edit"],
                      "guest_patch_authorizations": [
                          {"operation_index": 0, "op": "set_dates", "target_fields": ["dates.check_in", "dates.check_out"],
                           "intent": "explicit_request", "current_turn_quote": "May 10 through May 13, 2027" if "May 11" not in question else "May 11 through May 14, 2027"},
                          {"operation_index": 1, "op": "set_adults", "target_fields": ["party.adults"],
                           "intent": "explicit_request", "current_turn_quote": "two adults"},
                          {"operation_index": 2, "op": "add_child", "target_fields": ["party.children"],
                           "intent": "explicit_request", "current_turn_quote": "one child age 9"},
                      ]}
            self.patch_proposed = True
            return self._result(result)

        facts = payload.get("facts", [])
        supported = []
        if facts:
            fact_id = facts[0]["fact_id"]
            supported = [{"text": "The hotel record includes the requested information.", "fact_ids": [fact_id]}]
        unknowns = [] if supported else ["That detail is not in the available hotel records."]
        result = {"supported_claims": supported, "unknowns": unknowns, "conflicts": []}
        if patch_enabled:
            result["turn_intents"] = ["hotel_information"]
            result["guest_patch_authorizations"] = []
        brief = payload.get("guest_brief") or {}
        if "nights" in question.lower() and brief.get("data", {}).get("dates", {}).get("nights") is not None:
            nights = brief["data"]["dates"]["nights"]
            result["guest_claims"] = [{"text": f"Your stay is {nights} nights.", "refs": ["dates.nights"]}]
        return self._result(result)

    def _result(self, value: dict[str, Any]) -> GenerationResult:
        return GenerationResult(
            text=json.dumps(value), provider="fake", deployment="consumer-test", model="offline-fake",
            request_id=f"consumer-{self.calls}",
            usage=Usage() if self.unknown_usage else Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


class UnscopedPreparationPatchProvider:
    """Returns a structurally valid edit without classifying this turn as an edit."""

    def __init__(self) -> None:
        self.calls = 0
        self.inputs: list[dict[str, Any]] = []

    async def generate(self, request: GenerationRequest):
        self.calls += 1
        payload = json.loads(request.input_text)
        self.inputs.append(payload)
        candidates = payload.get("candidate_index", [])
        question = payload["question"]
        if candidates:
            value = {
                "fact_ids": [candidates[0]["fact_id"]], "turn_intents": ["hotel_information"],
                "guest_patch": {"ops": [{"op": "set_dates", "check_in": "2027-05-10", "check_out": "2027-05-13"}]},
                "guest_patch_authorizations": [{
                    "operation_index": 0, "op": "set_dates",
                    "target_fields": ["dates.check_in", "dates.check_out"],
                    "intent": "explicit_request", "current_turn_quote": "May 10 through May 13, 2027",
                }],
            }
        else:
            value = {
                "supported_claims": [], "unknowns": [], "conflicts": [],
                "turn_intents": ["hotel_information"],
                "guest_patch": {"ops": [{"op": "set_adults", "count": 2}]},
                "guest_patch_authorizations": [{
                    "operation_index": 0, "op": "set_adults", "target_fields": ["party.adults"],
                    "intent": "explicit_request", "current_turn_quote": question,
                }],
            }
            if request.response_envelope_key:
                value = {request.response_envelope_key: value}
        return GenerationResult(
            text=json.dumps(value), provider="fake", deployment="unscoped-preparation",
            model="offline-fake", request_id=f"unscoped-{self.calls}",
            usage=Usage(input_tokens=3, output_tokens=4, total_tokens=7),
        )


def _client(engine, provider: BriefConsumerProvider, *, timeout_seconds: float = 20.0) -> tuple[TestClient, dict[str, Any]]:
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-five-test-signing-secret"),
        ai_turn_timeout_seconds=timeout_seconds,
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "harbor-city-demo"})
    assert opened.status_code == 201
    return client, opened.json()


def _post(client: TestClient, session: dict[str, Any], body: dict[str, str]):
    return client.post(
        f"/v1/guest/sessions/{session['session_id']}/messages", json=body,
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )


def test_mixed_edit_commits_before_answer_and_brief_remains_available_after_history_window(engine) -> None:
    provider = BriefConsumerProvider()
    client, session = _client(engine, provider)
    response = _post(client, session, {"request_id": str(uuid.uuid4()), "question": EDIT})
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["status"] == "completed"
    assert first["guest_brief"]["brief_version"] == 1
    assert first["guest_brief"]["dates"]["nights"] == 3
    assert len(first["guest_brief"]["party"]["children"]) == 1
    assert first["brief_receipt"]["answer_status"] == "completed"
    assert first["evidence"], "the mixed breakfast question should retain hotel evidence"
    assert first["trace"]["calls"] <= 2
    assert any(item.get("guest_brief", {}).get("brief_version") == 1 for item in provider.inputs if "facts" in item)
    committed_calls = [item for item in provider.inputs if item.get("guest_brief_patch_enabled") is False]
    assert committed_calls
    committed_instructions = committed_calls[-1]["instructions"]
    assert len(committed_instructions) < 3000
    assert "guest_patch" not in committed_instructions
    assert "set_dates" not in committed_instructions

    for _ in range(5):
        faq = _post(client, session, {"request_id": str(uuid.uuid4()), "question": "What are the breakfast hours?"})
        assert faq.status_code == 200, faq.text
    consumer = _post(client, session, {"request_id": str(uuid.uuid4()), "question": "How many nights is my stay?"})
    assert consumer.status_code == 200, consumer.text
    answer = consumer.json()
    assert answer["brief_dependent"] is True
    assert answer["brief_version_used"] == 1
    assert "3 nights" in answer["answer"]
    assert answer["trace"]["calls"] <= 2
    last_answer_input = next(item for item in reversed(provider.inputs) if item.get("question") == "How many nights is my stay?")
    assert last_answer_input["guest_brief"]["brief_version"] == 1


def test_preparation_rejects_unscoped_patch_before_m2_or_brief_mutation(engine) -> None:
    provider = UnscopedPreparationPatchProvider()
    client, session = _client(engine, provider)
    request_id = str(uuid.uuid4())
    question = "Please set my dates to May 10 through May 13, 2027 for two adults."
    before = get_guest_brief(engine, session_id=session["session_id"], hotel_id="HTL-CITY01")

    response = _post(client, session, {"request_id": request_id, "question": question})

    assert response.status_code == 502, (response.text, provider.inputs)
    assert response.json()["error"]["code"] == "invalid_model_output"
    assert provider.calls == 1, "invalid preparation metadata must be rejected before committed-answer M2"
    after = get_guest_brief(engine, session_id=session["session_id"], hotel_id="HTL-CITY01")
    assert after == before
    assert after.brief_version == 0
    assert after.pending_fields == ()
    assert get_guest_brief_receipt(
        engine, session_id=session["session_id"], hotel_id="HTL-CITY01", receipt_id=request_id,
    ) is None


def test_breakfast_preparation_rejects_unscoped_patch_as_invalid_model_output(engine) -> None:
    provider = UnscopedPreparationPatchProvider()
    client, session = _client(engine, provider)
    request_id = str(uuid.uuid4())
    question = "Breakfast buffet at Ben Gio, floor 1, 06:30-09:30?"
    before = get_guest_brief(engine, session_id=session["session_id"], hotel_id="HTL-CITY01")

    response = _post(client, session, {"request_id": request_id, "question": question})

    assert response.status_code == 502, (response.text, provider.inputs)
    assert response.json()["error"]["code"] == "invalid_model_output", provider.inputs
    assert provider.calls == 1, "invalid preparation metadata must fail before a second model call"
    assert get_guest_brief(engine, session_id=session["session_id"], hotel_id="HTL-CITY01") == before
    assert get_guest_brief_receipt(
        engine, session_id=session["session_id"], hotel_id="HTL-CITY01", receipt_id=request_id,
    ) is None


def test_unknown_provider_usage_remains_unavailable_in_api_trace(engine) -> None:
    provider = BriefConsumerProvider(unknown_usage=True)
    client, session = _client(engine, provider)
    response = _post(client, session, {"request_id": str(uuid.uuid4()), "question": EDIT})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["trace"]["calls"] == 2, "the test must exercise preparation plus committed-answer aggregation"
    assert result["trace"]["usage"] == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }


def test_cached_replay_freshness_lookup_failure_keeps_same_request_recoverable(engine) -> None:
    provider = BriefConsumerProvider()
    client, session = _client(engine, provider)
    request_id = str(uuid.uuid4())
    first = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "completed"
    calls_after_completion = provider.calls
    def fail_cached_freshness(*args, **kwargs):
        raise OperationalError("synthetic cached freshness lookup failure", None, Exception("synthetic"))

    with patch.object(guest_chat_composition, "get_guest_brief", fail_cached_freshness):
        uncertain = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert uncertain.status_code == 503, uncertain.text
    assert uncertain.json()["error"]["code"] == "freshness_unavailable"

    replay = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "completed"
    assert len(replay.json()["guest_brief"]["party"]["children"]) == 1
    assert provider.calls == calls_after_completion


def test_postcommit_failure_replays_same_id_and_resumes_without_resubmitting_edit(engine) -> None:
    provider = BriefConsumerProvider(fail_final_answer_once=True)
    client, session = _client(engine, provider)
    request_id = str(uuid.uuid4())
    failed = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert failed.status_code == 502, failed.text
    partial = failed.json()
    assert partial["status"] == "partial_success"
    assert partial["guest_brief"]["brief_version"] == 1
    assert partial["brief_receipt"]["status"] == "partial_success"
    assert partial["answer_status"] == "failed"
    persisted_scope = get_guest_brief_receipt(
        engine, session_id=session["session_id"], hotel_id="HTL-CITY01", receipt_id=request_id,
    )["answer_payload"]
    assert persisted_scope["turn_intents"] == ["hotel_information", "guest_edit"]
    assert persisted_scope["authorized_targets"] == ["dates.check_in", "dates.check_out", "party.adults", "party.children"]
    failed_calls = provider.calls

    replay = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "partial_success"
    assert replay.json()["guest_brief"]["brief_version"] == 1
    assert provider.calls == failed_calls

    resumed = _post(client, session, {
        "request_id": str(uuid.uuid4()), "answer_only_receipt_id": request_id,
    })
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["brief_receipt"]["answer_status"] == "completed"
    current = resumed.json()["guest_brief"]
    assert len(current["party"]["children"]) == 1
    assert current["dates"]["nights"] == 3
    resume_inputs = provider.inputs[-resumed.json()["trace"]["calls"]:]
    assert resume_inputs
    assert all(item.get("guest_brief_patch_enabled") is False for item in resume_inputs)
    assert all("set my dates" not in item.get("instructions", "").lower() for item in resume_inputs)
    assert resume_inputs[-1].get("turn_intents") == ["hotel_information", "guest_edit"]


def test_lost_apply_ack_returns_partial_and_same_id_recovery_never_duplicates_child(engine) -> None:
    provider = BriefConsumerProvider()
    client, session = _client(engine, provider)
    request_id = str(uuid.uuid4())
    apply_original = guest_chat_composition.apply_guest_brief_patch

    def commit_then_lose_ack(*args, **kwargs):
        apply_original(*args, **kwargs)
        raise OperationalError("synthetic commit acknowledgement unavailable", None, Exception("synthetic"))

    with patch.object(guest_chat_composition, "apply_guest_brief_patch", commit_then_lose_ack):
        first = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert first.status_code == 502, first.text
    partial = first.json()
    assert partial["status"] == "partial_success"
    assert partial["brief_receipt"]["answer_status"] == "failed"
    assert len(partial["guest_brief"]["party"]["children"]) == 1
    calls_after_commit = provider.calls

    replay = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "partial_success"
    assert len(replay.json()["guest_brief"]["party"]["children"]) == 1
    assert provider.calls == calls_after_commit

    resumed = _post(client, session, {
        "request_id": str(uuid.uuid4()), "answer_only_receipt_id": request_id,
    })
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["brief_receipt"]["answer_status"] == "completed"
    assert len(resumed.json()["guest_brief"]["party"]["children"]) == 1


def test_apply_commit_delayed_ack_past_deadline_returns_partial_and_same_id_recovery(engine) -> None:
    provider = BriefConsumerProvider()
    client, session = _client(engine, provider, timeout_seconds=1.0)
    request_id = str(uuid.uuid4())
    apply_original = guest_chat_composition.apply_guest_brief_patch

    def commit_then_delay_ack(*args, **kwargs):
        result = apply_original(*args, **kwargs)
        time.sleep(1.5)
        return result

    with patch.object(guest_chat_composition, "apply_guest_brief_patch", commit_then_delay_ack):
        timed_out = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert timed_out.status_code == 502, timed_out.text
    partial = timed_out.json()
    assert partial["status"] == "partial_success"
    assert partial["brief_receipt"]["answer_status"] == "failed"
    assert len(partial["guest_brief"]["party"]["children"]) == 1
    calls_after_timeout = provider.calls

    replay = _post(client, session, {"request_id": request_id, "question": EDIT})
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "partial_success"
    assert len(replay.json()["guest_brief"]["party"]["children"]) == 1
    assert provider.calls == calls_after_timeout


def test_uncertain_receipt_lookup_keeps_same_id_and_replay_recovers_without_provider(engine) -> None:
    provider = BriefConsumerProvider()
    client, session = _client(engine, provider)
    request_id = str(uuid.uuid4())
    apply_original = guest_chat_composition.apply_guest_brief_patch
    receipt_lookup_original = guest_chat_composition.get_guest_brief_receipt
    lookup_calls = 0

    def commit_then_lose_ack(*args, **kwargs):
        apply_original(*args, **kwargs)
        raise OperationalError("synthetic commit acknowledgement unavailable", None, Exception("synthetic"))

    def fail_first_receipt_lookup(*args, **kwargs):
        nonlocal lookup_calls
        lookup_calls += 1
        if lookup_calls == 1:
            raise OperationalError("synthetic receipt lookup failure", None, Exception("synthetic"))
        return receipt_lookup_original(*args, **kwargs)

    with patch.object(guest_chat_composition, "apply_guest_brief_patch", commit_then_lose_ack), \
            patch.object(guest_chat_composition, "get_guest_brief_receipt", fail_first_receipt_lookup):
        first = _post(client, session, {"request_id": request_id, "question": EDIT})
        assert first.status_code == 503, first.text
        assert first.json()["error"]["code"] == "brief_apply_outcome_unknown"
        calls_after_uncertain = provider.calls

        replay = _post(client, session, {"request_id": request_id, "question": EDIT})

    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "partial_success"
    assert len(replay.json()["guest_brief"]["party"]["children"]) == 1
    assert provider.calls == calls_after_uncertain


def test_dependent_replay_goes_stale_but_pure_faq_does_not_after_later_edit(engine) -> None:
    provider = BriefConsumerProvider()
    client, session = _client(engine, provider)
    first_id = str(uuid.uuid4())
    first = _post(client, session, {"request_id": first_id, "question": EDIT})
    assert first.status_code == 200, first.text

    dependent_id = str(uuid.uuid4())
    dependent = _post(client, session, {"request_id": dependent_id, "question": "How many nights is my stay?"})
    assert dependent.status_code == 200, dependent.text
    assert dependent.json()["brief_dependent"] is True
    faq_id = str(uuid.uuid4())
    faq = _post(client, session, {"request_id": faq_id, "question": "What are the breakfast hours?"})
    assert faq.status_code == 200, faq.text
    assert faq.json().get("brief_dependent") is not True

    changed = _post(client, session, {"request_id": str(uuid.uuid4()), "question": EDIT_LATER})
    assert changed.status_code == 200, changed.text
    stale_replay = _post(client, session, {"request_id": dependent_id, "question": "How many nights is my stay?"})
    assert stale_replay.status_code == 200, stale_replay.text
    assert stale_replay.json()["brief_narrative_stale"] is True
    assert stale_replay.json()["guest_brief"]["brief_version"] == 2

    faq_replay = _post(client, session, {"request_id": faq_id, "question": "What are the breakfast hours?"})
    assert faq_replay.status_code == 200, faq_replay.text
    assert faq_replay.json().get("brief_dependent") is not True
    assert faq_replay.json().get("brief_narrative_stale") is not True
    assert faq_replay.json()["guest_brief"]["brief_version"] == 2
