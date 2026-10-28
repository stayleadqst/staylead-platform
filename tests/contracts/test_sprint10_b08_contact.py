import asyncio
import json
import time

import pytest
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.dependencies.guest_chat import _booking_channel
from staylead_platform.domains.hospitality.schemas.grounded_answer import (
    HospitalityGroundedAnswer,
)
from staylead_platform.domains.hospitality.schemas.guest_brief import (
    validate_committed_turn_channels,
)
from staylead_platform.domains.hospitality.schemas.preparation_output import (
    preparation_answer_output_schema,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    ProviderError,
)

from tests.b08.api_app import B08OfflineProvider


def test_booking_channel_projects_contact_and_hours_for_only_the_resolved_property() -> None:
    settings = Settings(
        booking_destination_by_hotel={"harbor": "https://booking.example/harbor"},
        booking_contact_by_hotel={"harbor": "+1 555 0100", "lagoon": "+1 555 0200"},
        booking_contact_hours_by_hotel={"harbor": "Daily, 09:00–17:00", "lagoon": "Weekdays"},
    )

    harbor = _booking_channel(settings, "harbor")
    lagoon = _booking_channel(settings, "lagoon")
    unknown = _booking_channel(settings, "pine")

    assert harbor == {
        "destination_url": "https://booking.example/harbor",
        "contact": "+1 555 0100",
        "contact_hours": "Daily, 09:00–17:00",
        "destination_kind": "synthetic_demo",
    }
    assert lagoon["destination_url"] is None
    assert lagoon["contact"] == "+1 555 0200"
    assert lagoon["contact_hours"] == "Weekdays"
    assert unknown["destination_url"] is None
    assert unknown["contact"] is None
    assert unknown["contact_hours"] is None


def test_booking_contact_hours_are_bounded_and_control_free() -> None:
    settings = Settings(
        booking_destination_by_hotel={},
        booking_contact_by_hotel={"newline": "Desk\nCall", "long": "x" * 241, "ok": "  +1 555 0100  "},
        booking_contact_hours_by_hotel={"newline": "Daily\n09:00", "long": "x" * 161, "ok": "  Daily 09:00–17:00  "},
    )

    assert _booking_channel(settings, "newline")["contact"] is None
    assert _booking_channel(settings, "newline")["contact_hours"] is None
    assert _booking_channel(settings, "long")["contact"] is None
    assert _booking_channel(settings, "long")["contact_hours"] is None
    assert _booking_channel(settings, "ok")["contact"] == "+1 555 0100"
    assert _booking_channel(settings, "ok")["contact_hours"] == "Daily 09:00–17:00"


def test_b08_offline_preparation_answer_preserves_classified_turn_intent() -> None:
    schema = preparation_answer_output_schema((), (), None)
    request = GenerationRequest(
        instructions="test-only",
        input_text=json.dumps({
            "question": "How can I contact the hotel?",
            "facts": [],
        }),
        response_schema=schema,
        response_envelope_key="response",
    )

    result = asyncio.run(B08OfflineProvider(fault_mode="none").generate(request))
    payload = HospitalityGroundedAnswer.model_validate_json(result.text)

    assert payload.turn_intents == ["booking_request"]
    assert payload.supported_claims == []
    assert payload.unknowns == []
    assert payload.conflicts == []
    validate_committed_turn_channels(payload, tuple(payload.turn_intents), (), ())


def test_b08_offline_committed_answer_does_not_reclassify_turn_intent() -> None:
    request = GenerationRequest(
        instructions="test-only",
        input_text=json.dumps({"question": "How can I contact the hotel?", "facts": []}),
    )

    result = asyncio.run(B08OfflineProvider(fault_mode="none").generate(request))

    assert "turn_intents" not in json.loads(result.text)


def test_b08_offline_timeout_fault_uses_clock_and_recovers_after_first_failure() -> None:
    provider = B08OfflineProvider(fault_mode="first_answer_timeout")
    request = GenerationRequest(
        instructions="test-only",
        input_text=json.dumps({
            "question": "Trigger timeout in the test provider.",
            "facts": [],
        }),
        response_schema=preparation_answer_output_schema((), (), None),
        response_envelope_key="response",
    )

    started = time.monotonic()
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.generate(request))
    elapsed = time.monotonic() - started

    assert error.value.code == "provider_timeout"
    assert error.value.retryable is True
    assert 0.9 <= elapsed < 1.5

    recovered = asyncio.run(provider.generate(request))
    assert recovered.provider == "offline-b08-browser"
