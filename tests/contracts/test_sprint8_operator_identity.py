import pytest
from pydantic import SecretStr, ValidationError

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.infrastructure.identity.operator import (
    DevOperatorCredential,
    resolve_dev_operator,
)


def test_dev_operator_token_resolves_only_to_configured_server_principal() -> None:
    token = "s8-test-token-" + "x" * 32
    credential = DevOperatorCredential(
        token=SecretStr(token), operator_id="local-operator-s8",
        property_id="HTL-S8-DEMO", permissions=frozenset({"guide:read", "guide:write"}),
    )

    principal = resolve_dev_operator(token, [credential])

    assert principal is not None
    assert principal.operator_id == "local-operator-s8"
    assert principal.property_id == "HTL-S8-DEMO"
    assert principal.permissions == frozenset({"guide:read", "guide:write"})
    assert resolve_dev_operator("wrong-token", [credential]) is None
    assert token not in repr(credential)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_dev_operator_credentials_are_rejected_outside_dev_targets(environment: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment=environment,
            dev_operator_credentials=[{
                "token": "s8-test-token-" + "x" * 32, "operator_id": "local-operator-s8",
                "property_id": "HTL-S8-DEMO", "permissions": ["guide:read", "guide:write"],
            }],
        )


def test_dev_operator_credentials_have_no_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.dev_operator_credentials == []


@pytest.mark.parametrize("credential", [
    {"token": "", "operator_id": "local-operator-s8", "property_id": "HTL-S8-DEMO", "permissions": ["guide:read"]},
    {"token": "x" * 40, "operator_id": "", "property_id": "HTL-S8-DEMO", "permissions": ["guide:read"]},
    {"token": "x" * 40, "operator_id": "local-operator-s8", "property_id": "", "permissions": ["guide:read"]},
    {"token": "x" * 40, "operator_id": "local-operator-s8", "property_id": "HTL-S8-DEMO", "permissions": []},
    {"token": "x" * 40, "operator_id": "local-operator-s8", "property_id": "HTL-S8-DEMO", "permissions": ["admin"]},
])
def test_operator_credentials_require_bounded_identity_and_supported_permissions(credential: dict) -> None:
    with pytest.raises(ValidationError):
        DevOperatorCredential.model_validate(credential)


def test_duplicate_operator_tokens_are_rejected() -> None:
    token = "s8-test-token-" + "x" * 32
    common = {"token": token, "operator_id": "local-operator-s8", "permissions": ["guide:read", "guide:write"]}

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            dev_operator_credentials=[
                {**common, "property_id": "HTL-S8-DEMO"},
                {**common, "property_id": "HTL-OTHER"},
            ],
        )
