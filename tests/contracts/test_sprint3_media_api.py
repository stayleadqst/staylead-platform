"""Focused HTTP checks for scoped guest media and data-driven hotel lookup."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from pydantic import SecretStr
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.dependencies import guest_chat as guest_chat_module
from staylead_platform.composition.dependencies.guest_chat import _media_reference
from staylead_platform.entrypoints.app import create_app
from staylead_platform.platform.contracts.knowledge import EligibleAsset, MediaDescriptor
from staylead_platform.platform.guest_context.sessions.signing import issue_token

SESSION_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_SESSION = "12345678-1234-4234-8234-123456789abd"
SECRET = "test-only-signing-secret"
PNG = b"\x89PNG\r\n\x1a\n\x00\xff"


class FakeMediaRepository:
    def __init__(self, hotel_id: str = "HTL-FOUR"):
        self.hotel_id = hotel_id

    def read_eligible_asset(self, hotel_id: str, media_id: str, now: datetime) -> EligibleAsset | None:
        if media_id != "IMG-ONE" or hotel_id != self.hotel_id:
            return None
        descriptor = MediaDescriptor(
            media_id="IMG-ONE", hotel_id=hotel_id, fact_ids=("F-ONE",), kind="image",
            mime_type="image/png", byte_size=len(PNG), sha256="0" * 64,
            caption="Approved view", alt_text="A hotel view", source_id="SRC-ONE", source_version="1",
        )
        return EligibleAsset(content=PNG, mime_type="image/png", descriptor=descriptor)

    def list_eligible_media(self, hotel_id: str, fact_ids: set[str], now: datetime,
                            *, timeout_seconds: float | None = None) -> list[MediaDescriptor]:
        return []


def token(session_id: str = SESSION_ID, hotel_id: str = "HTL-FOUR", *, expires: int | None = None) -> str:
    return issue_token(secret=SECRET, session_id=session_id, hotel_id=hotel_id,
                       expires_at=expires or int((datetime.now(UTC) + timedelta(hours=1)).timestamp()))


def make_client(monkeypatch, *, stored_hotel: str = "HTL-FOUR") -> TestClient:
    monkeypatch.setattr(guest_chat_module, "get_session", lambda engine, session_id: {
        "session_id": session_id, "hotel_id": stored_hotel,
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    })
    monkeypatch.setattr(guest_chat_module, "get_hotel_by_slug", lambda engine, slug: ({
        "hotel_id": "HTL-FOUR", "slug": slug, "public_config": {"name": "Fourth Hotel"},
        "config_version": "1",
    } if slug == "fourth-hotel" else None))
    settings = Settings(_env_file=None, database_url="sqlite://", ai_provider="disabled",
                        session_signing_secret=SecretStr(SECRET))
    app = create_app(settings)
    app.state.guest_chat._media_repository = FakeMediaRepository()
    return TestClient(app)


def test_hotel_lookup_is_data_driven_and_unknown_slug_is_clear(monkeypatch) -> None:
    client = make_client(monkeypatch)
    assert client.get("/v1/guest/hotels/fourth-hotel").json() == {
        "hotel_id": "HTL-FOUR", "hotel_slug": "fourth-hotel",
        "public_config": {"name": "Fourth Hotel"}, "config_version": "1",
        "guest_contract_version": "1",
    }
    unknown = client.get("/v1/guest/hotels/not-imported")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "hotel_unavailable"


def test_authenticated_media_returns_exact_bytes_mime_and_no_store(monkeypatch) -> None:
    client = make_client(monkeypatch)
    response = client.get(
        f"/v1/guest/sessions/{SESSION_ID}/media/IMG-ONE",
        headers={"Authorization": f"Bearer {token()}"},
    )
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"


def test_wrong_session_hotel_expired_and_ineligible_media_return_no_bytes(monkeypatch) -> None:
    client = make_client(monkeypatch)
    base = f"/v1/guest/sessions/{SESSION_ID}/media/IMG-ONE"
    wrong_path = client.get(f"/v1/guest/sessions/{OTHER_SESSION}/media/IMG-ONE",
                            headers={"Authorization": f"Bearer {token()}"})
    expired = client.get(base, headers={"Authorization": f"Bearer {token(expires=1)}"})
    wrong_hotel = make_client(monkeypatch, stored_hotel="HTL-OTHER").get(
        base, headers={"Authorization": f"Bearer {token()}"})
    client = make_client(monkeypatch)
    ineligible = client.get(f"/v1/guest/sessions/{SESSION_ID}/media/NOT-APPROVED",
                            headers={"Authorization": f"Bearer {token()}"})
    assert wrong_path.status_code == 403 and wrong_path.headers["content-type"].startswith("application/json")
    assert expired.status_code == 401 and expired.headers["content-type"].startswith("application/json")
    assert wrong_hotel.status_code == 401 and wrong_hotel.headers["content-type"].startswith("application/json")
    assert ineligible.status_code == 404 and ineligible.headers["content-type"].startswith("application/json")


def test_media_projection_requires_final_cited_fact_and_emits_no_arbitrary_url() -> None:
    descriptor = MediaDescriptor(
        media_id="IMG-ONE", hotel_id="HTL-FOUR", fact_ids=("F-ONE", "F-TWO"), kind="image",
        mime_type="image/png", byte_size=len(PNG), sha256="0" * 64,
        caption="Approved view", alt_text="A hotel view", source_id="SRC-ONE", source_version="1",
    )
    projected = _media_reference(descriptor, {"F-ONE"})
    assert projected is not None and projected["fact_ids"] == ["F-ONE"]
    assert "url" not in projected and "path" not in projected
    assert _media_reference(descriptor, {"F-UNKNOWN"}) is None
