"""Test-only API target for B08's real browser-to-API flow with an offline provider."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from pydantic import SecretStr
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import apply_migrations
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import (
    import_fixture_pack,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    Usage,
)


class B08OfflineProvider:
    def __init__(self, *, fault_mode: str) -> None:
        self._fault_mode = fault_mode
        self._failed_once = False
        self._fault_timeout_seconds = 1.0
        self._fault_delay_seconds = 2.0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        question = str(payload.get("question", ""))
        if "candidate_index" in payload:
            candidates = payload.get("candidate_index", [])
            language = (
                "ar" if any("\u0600" <= char <= "\u06ff" for char in question)
                else "ko" if any("\uac00" <= char <= "\ud7a3" for char in question)
                else None
            )
            if "contact the hotel" in question.lower():
                value = {"fact_ids": [], "turn_intents": ["booking_request"]}
            else:
                value = {
                    "fact_ids": [
                        item["fact_id"] for item in candidates
                        if item.get("fact_id") == "F-HTL-CITY01-040"
                    ],
                    "turn_intents": ["hotel_information"],
                }
                if language:
                    value["inferred_language_tag"] = language
        else:
            if self._fault_mode == "first_answer_timeout" and "trigger timeout" in question.lower() and not self._failed_once:
                self._failed_once = True
                try:
                    async with asyncio.timeout(self._fault_timeout_seconds):
                        await asyncio.sleep(self._fault_delay_seconds)
                except TimeoutError as exc:
                    raise ProviderError(
                        "provider_timeout",
                        "The controlled offline provider timed out.",
                        retryable=True,
                    ) from exc
            facts = payload.get("facts", [])
            breakfast = next((item for item in facts if item.get("fact_id") == "F-HTL-CITY01-040"), None)
            arabic = any("\u0600" <= char <= "\u06ff" for char in question)
            korean = any("\uac00" <= char <= "\ud7a3" for char in question)
            preparation_answer = _is_preparation_answer_request(request)
            turn_intents = _classify_offline_intents(question)
            if preparation_answer and turn_intents == ["booking_request"]:
                value = {
                    "supported_claims": [],
                    "unknowns": [],
                    "conflicts": [],
                    "turn_intents": turn_intents,
                }
            else:
                value = {
                    "supported_claims": ([{
                        "text": (
                            "يُقدَّم الإفطار في بين جيو بالطابق الأول من 06:30 إلى 09:30."
                            if arabic else "조식은 1층 벤 지오에서 06:30부터 09:30까지 제공됩니다."
                            if korean else "Breakfast is at Ben Gio on floor 1 from 06:30 to 09:30."
                        ),
                        "fact_ids": [breakfast["fact_id"]],
                    }] if breakfast else []),
                    "unknowns": (["لا تذكر السجلات المتاحة ما إذا كان الفندق يضم مهبطًا للطائرات المروحية. يُرجى تأكيد ذلك مع الفندق."] if arabic else
                                 ["호텔에 헬기장이 있는지는 이용 가능한 기록에 나와 있지 않습니다. 호텔에 확인해 주세요."] if korean else
                                 ["The available records do not say whether the hotel has a helipad. "
                                  + "Please confirm helipad availability with the hotel."]),
                    "conflicts": [],
                }
            if preparation_answer and turn_intents != ["booking_request"]:
                value["turn_intents"] = turn_intents
            if arabic:
                value["inferred_language_tag"] = "ar"
            elif korean:
                value["inferred_language_tag"] = "ko"
        return GenerationResult(
            text=json.dumps(value), provider="offline-b08-browser", deployment="test-only",
            model="controlled-stub", request_id=f"b08-browser-{id(request)}",
            usage=Usage(input_tokens=4, output_tokens=5, total_tokens=9),
        )


def _is_preparation_answer_request(request: GenerationRequest) -> bool:
    schema = request.response_schema
    if not isinstance(schema, dict) or request.response_envelope_key is None:
        return False
    envelope = schema.get("properties", {}).get(request.response_envelope_key)
    branches = envelope.get("anyOf", ()) if isinstance(envelope, dict) else ()
    return any(
        isinstance(branch, dict)
        and {"supported_claims", "turn_intents", "guest_patch"}.issubset(
            branch.get("properties", {})
        )
        for branch in branches
    )


def _classify_offline_intents(question: str) -> list[str]:
    lowered = question.lower()
    if "contact" in lowered and "hotel" in lowered:
        return ["booking_request"]
    return ["hotel_information"]


def create_b08_test_app() -> FastAPI:
    if os.environ.get("B08_TEST_ONLY") != "1":
        raise RuntimeError("Set B08_TEST_ONLY=1 to run this test-only API app.")
    database_url = os.environ.get("B08_TEST_DATABASE_URL", "")
    parsed = urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path != "/staylead_s10_browser":
        raise RuntimeError("B08 browser API requires the isolated local staylead_s10_browser database.")
    if not os.environ.get("B08_SESSION_SECRET"):
        raise RuntimeError("Set an ephemeral B08_SESSION_SECRET for this local test process.")

    engine = create_database_engine(database_url)
    apply_migrations(engine)
    fixture_root = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality" / "knowledge-v1"
    import_fixture_pack(engine, fixture_root)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        ai_provider="disabled",
        ai_timeout_seconds=1,
        ai_turn_timeout_seconds=5,
        session_signing_secret=SecretStr(os.environ["B08_SESSION_SECRET"]),
        booking_contact_by_hotel={
            "harbor-city-demo": '+1 555 0100 <img src=x onerror="window.__b08Injected=true">',
        },
        booking_contact_hours_by_hotel={"harbor-city-demo": "Daily, 09:00–17:00"},
    )
    fault_mode = os.environ.get("B08_PROVIDER_FAULT", "none")
    if fault_mode not in {"none", "first_answer_timeout"}:
        raise RuntimeError("Unsupported B08 offline provider fault mode.")
    return create_app(settings, engine=engine, provider=B08OfflineProvider(fault_mode=fault_mode))
