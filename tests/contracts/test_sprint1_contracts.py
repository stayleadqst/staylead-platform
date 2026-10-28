import json

from pydantic import BaseModel

from staylead_platform.platform.contracts.state import (
    DomainValidator,
    ExpectedVersion,
    ResultDependencies,
    ResultFreshness,
    SourceVersion,
    StateEnvelope,
    StateScope,
)
from staylead_platform.platform.guest_context.sessions.signing import (
    InvalidSessionToken,
    issue_token,
    verify_token,
)


def test_signed_session_token_is_hotel_bound_and_expires() -> None:
    token = issue_token(secret="test", session_id="s1", hotel_id="HTL-CITY01", expires_at=200)

    assert verify_token(token, secret="test", now=100).hotel_id == "HTL-CITY01"
    try:
        verify_token(token + "x", secret="test", now=100)
    except InvalidSessionToken:
        pass
    else:
        raise AssertionError("tampered token should be rejected")
    try:
        verify_token(token, secret="test", now=200)
    except InvalidSessionToken:
        pass
    else:
        raise AssertionError("expired token should be rejected")


def test_state_contracts_are_typed_and_can_mark_source_results_stale() -> None:
    class AlternateDomainBrief(BaseModel):
        dates: str
        travelers: int

    class AlternateValidator(DomainValidator[AlternateDomainBrief]):
        def validate(self, payload: object) -> AlternateDomainBrief:
            return AlternateDomainBrief.model_validate(payload)

    state = StateEnvelope(
        scope=StateScope(hotel_id="property-1", subject_id="session-1"),
        version=4,
        payload=AlternateValidator().validate({"dates": "2026-11-01", "travelers": 2}),
    )
    result = ResultDependencies(
        brief_version=state.version,
        sources=(SourceVersion(source_id="guide-1", version="3"),),
        freshness=ResultFreshness.STALE,
        affected_dependencies=("stay-plan",),
    )

    assert state.payload.travelers == 2
    assert result.freshness is ResultFreshness.STALE
    assert ExpectedVersion(4).value == state.version
    assert json.loads(state.payload.model_dump_json())["dates"] == "2026-11-01"
