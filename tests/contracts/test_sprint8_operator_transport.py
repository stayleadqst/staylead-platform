from fastapi import FastAPI
from fastapi.testclient import TestClient

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.operator.router import router

TOKEN = "s8-operator-test-" + "a" * 32
GUEST_TOKEN = "eyJhbGciOiJIUzI1NiJ9.guest-session-token"


class FakeOperatorGuide:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def preview(self, hotel_id: str):
        self.calls.append(("preview", hotel_id))
        return {"hotel_id": hotel_id, "status": "staged"}

    def import_pack(self, hotel_id: str):
        self.calls.append(("import", hotel_id))
        return {"hotel_id": hotel_id, "status": "imported"}


def _client(*, permissions: list[str] | None = None, environment: str = "test"):
    app = FastAPI()
    app.state.settings = Settings(
        _env_file=None,
        environment=environment,
        dev_operator_credentials=[{
            "token": TOKEN, "operator_id": "local-operator-s8", "property_id": "HTL-S8-DEMO",
            "permissions": permissions or ["guide:read", "guide:write"],
        }],
    )
    app.state.operator_guide = FakeOperatorGuide()
    app.include_router(router)
    return TestClient(app), app.state.operator_guide


def test_direct_operator_preview_rejects_missing_invalid_guest_and_wrong_property_before_service() -> None:
    client, service = _client()
    endpoint = "/v1/operator/properties/HTL-S8-DEMO/guide/preview"

    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers={"Authorization": "Bearer wrong-token"}).status_code == 401
    assert client.get(endpoint, headers={"Authorization": f"Bearer {GUEST_TOKEN}"}).status_code == 401
    assert client.get(
        "/v1/operator/properties/HTL-OTHER/guide/preview",
        headers={"Authorization": f"Bearer {TOKEN}"},
    ).status_code == 403
    assert service.calls == []


def test_direct_operator_preview_allows_only_configured_principal_and_permission() -> None:
    client, service = _client(permissions=["guide:read"])

    response = client.get(
        "/v1/operator/properties/HTL-S8-DEMO/guide/preview",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json() == {"hotel_id": "HTL-S8-DEMO", "status": "staged"}
    assert service.calls == [("preview", "HTL-S8-DEMO")]
    denied = client.post(
        "/v1/operator/properties/HTL-S8-DEMO/guide/import",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert denied.status_code == 403
    assert service.calls == [("preview", "HTL-S8-DEMO")]


def test_operator_routes_are_disabled_outside_dev_and_test() -> None:
    client, service = _client(environment="development")
    client.app.state.settings.environment = "production"

    response = client.get(
        "/v1/operator/properties/HTL-S8-DEMO/guide/preview",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 404
    assert service.calls == []
