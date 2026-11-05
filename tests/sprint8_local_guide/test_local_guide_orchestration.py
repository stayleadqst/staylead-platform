from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from staylead_platform.domains.hospitality.schemas.fact_selection import FactSelection
from staylead_platform.domains.hospitality.schemas.grounded_answer import (
    HospitalityGroundedAnswer,
    committed_answer_output_schema,
)
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    validate_committed_turn_channels,
    validate_guest_brief_proposal,
    validate_preparation_metadata,
)
from staylead_platform.domains.hospitality.schemas.preparation_output import (
    fact_selection_output_schema,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    Usage,
)
from staylead_platform.platform.contracts.guest_brief import GuestBriefSnapshot
from staylead_platform.platform.contracts.local_guide import LocalGuideResult
from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
    GroundedQAOrchestrator,
)


class TinyRetriever:
    def retrieve(self, hotel_id: str, question: str, history: list[dict[str, str]], *, timeout_seconds: float | None = None) -> Any:
        return type("Retrieval", (), {
            "facts": [], "candidate_index": [{"fact_id": "F-HTL-S8-DEMO-001", "topic": "local guide"}],
            "term_coverage": 0.0,
        })()

    def get_by_ids(self, hotel_id: str, fact_ids: set[str], *, timeout_seconds: float | None = None) -> list[dict[str, Any]]:
        return []

    @staticmethod
    def conflicts_for(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return []


class StubLocalGuide:
    def __init__(self) -> None:
        self.requests = []

    async def recommend(self, request: Any) -> LocalGuideResult:
        self.requests.append(request)
        return LocalGuideResult(
            hotel_id=request.hotel_id, generation=4, selected_venue_ids=("DIN-01",),
            fact_ids=("F-HTL-S8-DEMO-001",), supported_claims=({
                "venue_id": "DIN-01", "name": "Lotus Noodle", "kind": "dining", "fit_status": "fit",
                "reason_codes": ("interest:quiet",), "tradeoff_codes": (), "sponsored": False,
                "sponsor_label": None, "price": {"amount": 100000, "currency": "VND", "basis": "per_person"},
                "duration_minutes": 45, "hours_status": "confirmed", "unknowns": (),
                "fact_ids": ("F-HTL-S8-DEMO-001",),
            },),
            source_refs=({"source_id": "S8-GUIDE-PRIMARY", "source_version": "1.0", "fact_ids": ("F-HTL-S8-DEMO-001",)},),
        )


class TwoCallProvider:
    def __init__(self, patch: dict[str, Any]) -> None:
        self.patch = patch
        self.calls: list[GenerationRequest] = []
        self.responses: list[dict[str, Any]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls.append(request)
        if len(self.calls) == 1:
            payload = {
                "fact_ids": [], "guest_patch": {"ops": [self.patch]},
                "turn_intents": ["local_guide", "guest_edit"],
                "explicit_language_tag": "zh", "inferred_language_tag": None,
            }
        else:
            supplied = json.loads(request.input_text)
            assert supplied["local_guide_recommendations"][0]["venue_id"] == "DIN-01"
            payload = {
                "supported_claims": [], "unknowns": [], "conflicts": [], "guest_claims": [],
                "guest_brief_refs": [], "guest_clarification": None,
                "conversational_acknowledgement": None, "label_bundle": {},
            }
        self.responses.append(payload)
        return GenerationResult(
            text=json.dumps(payload, ensure_ascii=False), provider="fake", deployment="test", model="fake",
            request_id=f"req-{len(self.calls)}", usage=Usage(input_tokens=30, output_tokens=20, total_tokens=50),
        )


def _native_schema_accepts(schema: dict[str, Any], payload: dict[str, Any]) -> bool:
    script = """
const Ajv = require('./apps/web/node_modules/ajv');
const [schema, payload] = JSON.parse(process.argv[1]);
const valid = new Ajv({allErrors: true}).validate(schema, payload);
process.exit(valid ? 0 : 1);
"""
    result = subprocess.run(
        ["node", "-e", script, json.dumps([schema, payload], ensure_ascii=False)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, check=False,
    )
    return result.returncode == 0


def test_chinese_low_overlap_preparation_commits_typed_local_preferences_and_uses_two_calls() -> None:
    quote = "找安静的餐馆，人均预算不超过150000 VND。"
    patch = {
        "op": "set_local_guide_preferences", "venue_kinds": ["dining"], "interests": ["quiet"],
        "budget_amount": 150000, "budget_currency": "VND", "budget_basis": "per_person",
        "budget_strength": "hard", "current_turn_quote": quote,
    }
    provider = TwoCallProvider(patch)
    capability = StubLocalGuide()
    orchestrator = GroundedQAOrchestrator(
        provider=provider, retriever=TinyRetriever(), instructions="answer", committed_instructions="answer",
        response_schema=HospitalityGroundedAnswer, selection_instructions="select",
        committed_selection_instructions="select", selection_schema=FactSelection,
        preparation_selection_schema_factory=fact_selection_output_schema,
        preparation_metadata_validator=validate_preparation_metadata,
        committed_answer_validator=validate_committed_turn_channels, local_guide=capability,
        committed_output_schema_factory=committed_answer_output_schema,
        response_envelope_key="response",
    )
    empty = GuestBriefSnapshot(0, {"dates": {}, "party": {"adults": 1, "children": []}})
    prepared = asyncio.run(orchestrator.prepare_turn(
        hotel_id="HTL-S8-DEMO", question=quote, history=[], brief=empty,
    ))
    assert prepared.preparation_calls == 1
    assert prepared.turn_intents == ("local_guide", "guest_edit")
    committed_patch = validate_guest_brief_proposal(empty, prepared.guest_patch)
    brief = GuestBriefSnapshot(1, committed_patch.data, committed_patch.pending_fields)
    answer = asyncio.run(orchestrator.answer_committed_turn(
        hotel_id="HTL-S8-DEMO", question=quote, history=[], brief=brief,
        selected_fact_ids=prepared.selected_fact_ids, turn_intents=prepared.turn_intents,
        authorized_targets=tuple(committed_patch.source_fields),
    ))
    assert len(provider.calls) == 2
    assert len(capability.requests) == 1
    assert capability.requests[0].brief_data["local_guide_preferences"]["venue_kinds"] == ["dining"]
    assert answer.local_guide_result is not None
    assert answer.local_guide_result.selected_venue_ids == ("DIN-01",)
    final_schema = provider.calls[1].response_schema
    assert final_schema is not None
    assert _native_schema_accepts(final_schema, {"response": provider.responses[1]})
