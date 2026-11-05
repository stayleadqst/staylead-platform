"""Opt-in validation diagnostics stay typed, redacted, and local-only."""

import asyncio
import json

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.dependencies.guest_chat import GuestChatError
from staylead_platform.entrypoints.app import create_app

DIAGNOSTICS = {
    "code": "model_validation",
    "error_count": 1,
    "errors": [{"loc": ["supported_claims", 0, "fact_ids"], "type": "too_short"}],
}


def _response(*, enabled: bool, environment: str = "development") -> dict:
    app = create_app(Settings(
        _env_file=None, database_url="sqlite://", ai_provider="disabled",
        environment=environment, validation_diagnostics=enabled,
    ))
    handler = app.exception_handlers[GuestChatError]
    error = GuestChatError(
        502, "invalid_model_output", "The model returned an invalid answer.", retryable=True,
        partial_result={"status": "partial_success", "answer": ""},
        validation_diagnostics=DIAGNOSTICS,
    )
    response = asyncio.run(handler(None, error))
    return json.loads(response.body)


def test_validation_diagnostics_are_opt_in_and_hidden_outside_local_test() -> None:
    default = _response(enabled=False)
    assert "validation_diagnostics" not in default["error"]
    assert default["error"]["message"] == "The model returned an invalid answer."

    opted_in = _response(enabled=True)
    assert opted_in["error"]["validation_diagnostics"] == DIAGNOSTICS

    production = _response(enabled=True, environment="production")
    assert "validation_diagnostics" not in production["error"]
