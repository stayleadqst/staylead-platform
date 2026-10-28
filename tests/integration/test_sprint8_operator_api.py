"""Real operator API → M1 lifecycle → guest-visible snapshot integration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.knowledge_repository import (
    PostgresKnowledgeFactRepository,
)
from staylead_platform.infrastructure.persistence.local_guide_repository import (
    PostgresLocalGuideRepository,
)
from staylead_platform.infrastructure.persistence.store import (
    apply_migrations,
    get_completed_response,
    hotels,
    knowledge_facts,
    knowledge_media,
    knowledge_packs,
    knowledge_sources,
    lifecycle_operations,
)
from staylead_platform.infrastructure.source_connectors.local_guide import (
    activate_local_guide_source,
    import_local_guide_pack,
    refresh_local_guide_source,
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    Usage,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("STAYLEAD_S8_B_DATABASE_URL"), reason="isolated Sprint 8 B PostgreSQL database not configured",
)


class LocalGuideGuestProvider:
    """Offline M2/M3 provider double; local-guide selection itself stays deterministic."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        self.calls.append(payload)
        if "candidate_index" in payload:
            value: dict[str, object] = {
                "fact_ids": [], "guest_patch": None, "turn_intents": ["local_guide", "hotel_information"],
                "explicit_language_tag": "fr", "inferred_language_tag": None,
            }
        elif payload.get("guest_brief_patch_enabled") is True:
            value = {
                "fact_ids": [], "guest_patch": None, "turn_intents": ["local_guide", "hotel_information"],
                "explicit_language_tag": "fr", "inferred_language_tag": None,
                "supported_claims": [], "unknowns": [], "conflicts": [], "guest_claims": [],
                "guest_brief_refs": [], "label_bundle": {},
            }
        else:
            label_bundle = {
                key: FRENCH_LOCAL_GUIDE_LABELS.get(key, "Information à confirmer")
                for key in payload.get("missing_label_keys", [])
            }
            value = {
                "supported_claims": [], "unknowns": ["Some details need confirmation."],
                "conflicts": [], "guest_patch": None, "turn_intents": ["local_guide", "hotel_information"],
                "guest_claims": [], "guest_clarification": None,
                "conversational_acknowledgement": None, "guest_brief_refs": [],
                "explicit_language_tag": None, "inferred_language_tag": None,
                "label_bundle": label_bundle,
            }
        return GenerationResult(
            text=json.dumps(value, ensure_ascii=False), provider="offline-fake", deployment="s8-test",
            model="local-guide-fake", request_id=f"s8-fake-{len(self.calls)}",
            usage=Usage(input_tokens=2, output_tokens=3, total_tokens=5),
        )


FRENCH_LOCAL_GUIDE_LABELS = {
    "local_guide_title": "Suggestions locales", "local_guide_sources": "Sources",
    "local_guide_sponsored": "Sponsorisé", "local_guide_unknown": "À confirmer",
    "local_guide_fit": "Pourquoi cette suggestion", "local_guide_duration": "Durée de visite",
    "local_guide_hours": "État des horaires", "local_guide_conflicts": "Conflits entre sources",
    "local_guide_synthetic": "Informations synthétiques du pilote technique.",
    "local_guide_fit_status": "Correspondance possible", "local_guide_unknown_status": "Besoin requis non vérifié",
    "local_guide_interest_quiet": "Calme", "local_guide_interest_budget": "Budget",
    "local_guide_interest_culture": "Culture", "local_guide_interest_social": "Vie sociale",
    "local_guide_interest_nature": "Nature", "local_guide_interest_indoor": "En intérieur",
    "local_guide_interest_history": "Histoire",
    "local_guide_verify": "Confirmez les besoins importants et les informations actuelles auprès du lieu.",
    "local_guide_per_person": "par personne",
}


class PreferenceGuestProvider(LocalGuideGuestProvider):
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        self.calls.append(payload)
        question = str(payload.get("question", ""))
        quote = "Prefer indoor visits." if question.startswith("Prefer indoor") else (
            "quiet dinner under 100000 VND per person, peanut-safe and step-free"
        )
        if "candidate_index" in payload:
            value: dict[str, object] = {
                "fact_ids": [],
                "guest_patch": {"ops": [{
                    "op": "set_local_guide_preferences",
                    **({"interests": ["quiet", "indoor"]} if question.startswith("Prefer indoor") else {
                        "venue_kinds": ["dining"], "interests": ["quiet"], "budget_amount": 100000,
                        "budget_currency": "VND", "budget_basis": "per_person", "budget_strength": "hard",
                        "allergy_requirements": ["peanut"], "hard_accessibility_needs": ["step_free"],
                    }),
                    "current_turn_quote": quote,
                }]},
                "turn_intents": ["guest_edit", "local_guide", "hotel_information"],
                "explicit_language_tag": "fr" if not question.startswith("Prefer indoor") else None,
                "inferred_language_tag": None,
            }
        elif payload.get("guest_brief_patch_enabled") is True:
            value = {
                "supported_claims": [], "unknowns": [], "conflicts": [],
                "guest_patch": {"ops": [{
                    "op": "set_local_guide_preferences",
                    **({"interests": ["quiet", "indoor"]} if question.startswith("Prefer indoor") else {
                        "venue_kinds": ["dining"], "interests": ["quiet"], "budget_amount": 100000,
                        "budget_currency": "VND", "budget_basis": "per_person", "budget_strength": "hard",
                        "allergy_requirements": ["peanut"], "hard_accessibility_needs": ["step_free"],
                    }),
                    "current_turn_quote": quote,
                }]},
                "turn_intents": ["guest_edit", "local_guide", "hotel_information"],
                "explicit_language_tag": "fr" if not question.startswith("Prefer indoor") else None,
                "inferred_language_tag": None, "guest_claims": [], "guest_brief_refs": [],
                "label_bundle": {},
            }
        else:
            label_bundle = {
                key: FRENCH_LOCAL_GUIDE_LABELS.get(key, "Information à confirmer")
                for key in payload.get("missing_label_keys", [])
            }
            value = {
                "supported_claims": [], "unknowns": [], "conflicts": [], "guest_patch": None,
                "turn_intents": ["guest_edit", "local_guide", "hotel_information"],
                "guest_claims": [], "guest_brief_refs": [], "explicit_language_tag": None,
                "inferred_language_tag": None, "label_bundle": label_bundle,
            }
        return GenerationResult(
            text=json.dumps(value, ensure_ascii=False), provider="offline-fake", deployment="s8-test",
            model="preference-fake", request_id=f"s8-pref-{len(self.calls)}",
            usage=Usage(input_tokens=2, output_tokens=3, total_tokens=5),
        )


def _clear_pilot(engine) -> None:
    with engine.begin() as connection:
        connection.execute(delete(lifecycle_operations).where(lifecycle_operations.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(knowledge_media).where(knowledge_media.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(knowledge_facts).where(knowledge_facts.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(knowledge_sources).where(knowledge_sources.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(knowledge_packs).where(knowledge_packs.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(hotels).where(hotels.c.hotel_id == "HTL-S8-DEMO"))


def test_operator_import_preview_activate_refresh_revoke_delete_controls_guest_visibility() -> None:
    database_url = os.environ["STAYLEAD_S8_B_DATABASE_URL"]
    engine = create_database_engine(database_url)
    apply_migrations(engine)
    # This named database is reserved for B's tests; clear the fixed pilot identity
    # so reruns begin with the same staged state.
    _clear_pilot(engine)
    token = "s8-integration-" + uuid4().hex + uuid4().hex
    settings = Settings(
        _env_file=None, environment="test", database_url=database_url,
        dev_operator_credentials=[{
            "token": token, "operator_id": "local-operator-s8", "property_id": "HTL-S8-DEMO",
            "permissions": ["guide:read", "guide:write"],
        }],
    )
    client = TestClient(create_app(settings, engine=engine))
    operator = {"Authorization": f"Bearer {token}"}
    base = "/v1/operator/properties/HTL-S8-DEMO/guide"
    facts = PostgresKnowledgeFactRepository(engine)

    assert facts.list_guest_facts("HTL-S8-DEMO") == []
    unauthenticated = client.post(f"{base}/import")
    assert unauthenticated.status_code == 401
    wrong_property = client.post(
        "/v1/operator/properties/HTL-OTHER/guide/import", headers=operator,
    )
    assert wrong_property.status_code == 403

    imported = client.post(f"{base}/import", headers=operator)
    assert imported.status_code == 200, imported.text
    assert imported.json()["status"] in {"imported", "noop"}
    staged = client.get(f"{base}/preview", headers=operator)
    assert staged.status_code == 200, staged.text
    preview = staged.json()
    assert preview["lifecycle_status"] == "staged"
    assert len(preview["venues"]) == 6
    assert len(preview["providers"]) == 2
    assert len(preview["directional_routes"]) == 4
    assert preview["conflicts"]
    source = next(item for item in preview["source_refs"] if item["source_id"] == "S8-GUIDE-PRIMARY")

    def mutate(action: str, expected: dict, revision: str | None = None) -> dict:
        body = {
            "source_id": expected["source_id"],
            "expected_generation": expected["generation"],
            "expected_version": expected["version"],
            "expected_source_hash": expected["hash"],
            "operation_id": f"{action}-{uuid4().hex}",
        }
        if revision is not None:
            body["revision"] = revision
        response = client.post(f"{base}/{action}", headers=operator, json=body)
        assert response.status_code == 200, response.text
        return response.json()

    activated = mutate("activate", source)
    assert activated["status"] in {"applied", "replaced", "noop"}
    guest_before_refresh = facts.list_guest_facts("HTL-S8-DEMO")
    assert guest_before_refresh
    price_before = next(fact for fact in guest_before_refresh if fact.subject == "DIN-01" and fact.field == "price")
    assert price_before.value["amount"] == 100000
    current = client.get(f"{base}/preview", headers=operator).json()
    assert current["lifecycle_status"] in {"active", "partial", "staged"}
    source = next(item for item in current["source_refs"] if item["source_id"] == "S8-GUIDE-PRIMARY")

    refreshed = mutate("refresh", source, revision="primary-price-110000")
    assert refreshed["status"] in {"applied", "replaced", "noop"}
    guest_after_refresh = facts.list_guest_facts("HTL-S8-DEMO")
    price_after = next(fact for fact in guest_after_refresh if fact.subject == "DIN-01" and fact.field == "price")
    assert price_after.value["amount"] == 110000
    current = client.get(f"{base}/preview", headers=operator).json()
    source = next(item for item in current["source_refs"] if item["source_id"] == "S8-GUIDE-PRIMARY")

    revoked = mutate("revoke", source)
    assert revoked["lifecycle_status"] == "revoked"
    assert facts.list_guest_facts("HTL-S8-DEMO") == []
    current = client.get(f"{base}/preview", headers=operator).json()
    source = next(item for item in current["source_refs"] if item["source_id"] == "S8-GUIDE-PRIMARY")

    deleted = mutate("delete", source)
    assert deleted["lifecycle_status"] == "deleted"
    assert facts.list_guest_facts("HTL-S8-DEMO") == []


def test_guest_shortlist_needs_no_trip_dates_and_replay_preserves_old_snapshot() -> None:
    database_url = os.environ["STAYLEAD_S8_B_DATABASE_URL"]
    engine = create_database_engine(database_url)
    apply_migrations(engine)
    _clear_pilot(engine)
    root = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality"
    pack = root / "sprint8-local-guide-v1"
    imported = import_local_guide_pack(engine, pack, allowed_root=root)
    primary = next(source for source in imported["sources"] if source["source_id"] == "S8-GUIDE-PRIMARY")
    activate_local_guide_source(
        engine, pack, allowed_root=root, hotel_id="HTL-S8-DEMO", source_id=primary["source_id"],
        expected_generation=imported["generation"], expected_version=primary["version"],
        expected_source_hash=primary["source_hash"], operation_id=f"guest-activate-{uuid4().hex}",
    )
    provider = LocalGuideGuestProvider()
    settings = Settings(
        _env_file=None, environment="test", database_url=database_url, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-eight-local-guide-guest-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "lotus-pilot-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    endpoint = f"/v1/guest/sessions/{session['session_id']}/messages"
    request_id = str(uuid4())
    request = {"request_id": request_id, "question": "Find a quiet local place for dinner."}
    first = client.post(endpoint, headers=headers, json=request)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["guest_brief"]["brief_version"] == 0
    assert body["guest_brief"]["dates"] == {"check_in": None, "check_out": None, "nights": None}
    assert body["guest_brief"]["party"]["adults"] is None
    assert "room_advice" not in body
    assert body["local_guide"]["hotel_id"] == "HTL-S8-DEMO"
    assert body["local_guide"]["generation"] == 2
    assert body["local_guide"]["supported_claims"]
    assert body["local_guide"]["source_refs"]
    assert len(provider.calls) == 2
    assert body["presentation"]["local_guide_labels"]["local_guide_title"] == "Suggestions locales"
    assert body["presentation"]["direction"] == "ltr"
    old_dinner = next(item for item in body["local_guide"]["supported_claims"] if item["venue_id"] == "DIN-01")
    assert old_dinner["price"]["amount"] == 100000

    snapshot = PostgresLocalGuideRepository(engine).active_snapshot("HTL-S8-DEMO")
    source = next(item for item in snapshot.sources if item.source_id == "S8-GUIDE-PRIMARY")
    refresh_local_guide_source(
        engine, allowed_root=root, hotel_id="HTL-S8-DEMO", source_id=source.source_id,
        expected_generation=snapshot.generation, expected_version=source.source_version,
        expected_source_hash=source.source_hash, operation_id=f"guest-refresh-{uuid4().hex}",
        revision="primary-price-110000",
    )
    current_dinner_price = next(
        fact for fact in PostgresKnowledgeFactRepository(engine).list_guest_facts("HTL-S8-DEMO")
        if fact.subject == "DIN-01" and fact.field == "price"
    )
    assert current_dinner_price.value["amount"] == 110000

    historical = get_completed_response(
        engine, session_id=session["session_id"], hotel_id="HTL-S8-DEMO", request_id=request_id,
    )
    assert historical["local_guide"]["supported_claims"] == body["local_guide"]["supported_claims"]
    old_saved_dinner = next(item for item in historical["local_guide"]["supported_claims"]
                            if item["venue_id"] == "DIN-01")
    assert old_saved_dinner["price"]["amount"] == 100000
    replay = client.post(endpoint, headers=headers, json=request)
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "stale_source"
    freshness = client.post(f"/v1/guest/sessions/{session['session_id']}/freshness", headers=headers,
                            json={"request_id": request_id})
    assert freshness.status_code == 200, freshness.text
    assert freshness.json()["answer_eligibility"] == "stale"
    assert len(provider.calls) == 2


def test_guest_preference_commit_reaches_shortlist_and_later_edit_preserves_hard_need() -> None:
    database_url = os.environ["STAYLEAD_S8_B_DATABASE_URL"]
    engine = create_database_engine(database_url)
    apply_migrations(engine)
    _clear_pilot(engine)
    root = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality"
    pack = root / "sprint8-local-guide-v1"
    imported = import_local_guide_pack(engine, pack, allowed_root=root)
    primary = next(source for source in imported["sources"] if source["source_id"] == "S8-GUIDE-PRIMARY")
    activate_local_guide_source(
        engine, pack, allowed_root=root, hotel_id="HTL-S8-DEMO", source_id=primary["source_id"],
        expected_generation=imported["generation"], expected_version=primary["version"],
        expected_source_hash=primary["source_hash"], operation_id=f"pref-activate-{uuid4().hex}",
    )
    provider = PreferenceGuestProvider()
    settings = Settings(
        _env_file=None, environment="test", database_url=database_url, ai_provider="disabled",
        session_signing_secret=SecretStr("sprint-eight-guide-preferences-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "lotus-pilot-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    endpoint = f"/v1/guest/sessions/{session['session_id']}/messages"
    first = client.post(endpoint, headers=headers, json={
        "request_id": str(uuid4()),
        "question": "Please find a quiet dinner under 100000 VND per person, peanut-safe and step-free.",
    })
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["guest_brief"]["brief_version"] == 1
    first_preferences = first_body["guest_brief"]["local_guide_preferences"]
    assert first_preferences["budget_amount"] == 100000
    assert first_preferences["budget_strength"] == "hard"
    assert first_preferences["allergy_requirements"] == ["peanut"]
    assert first_preferences["hard_accessibility_needs"] == ["step_free"]
    assert first_body["presentation"]["local_guide_labels"]["local_guide_title"] == "Suggestions locales"
    assert "dates" not in first_body["guest_brief"] or first_body["guest_brief"]["dates"]["check_in"] is None
    committed_input = provider.calls[-1]
    assert committed_input["guest_brief"]["data"]["local_guide_preferences"] == first_preferences
    assert all(item["price"]["amount"] <= 100000
               for item in first_body["local_guide"]["supported_claims"] if item["price"].get("amount") is not None)
    assert any("allergy_unconfirmed" in item.get("unknown_codes", [])
               for item in first_body["local_guide"]["supported_claims"])
    allergy_claim = next(item for item in first_body["local_guide"]["supported_claims"]
                         if "allergy_unconfirmed" in item.get("unknown_codes", []))
    assert any("contamination croisée" in text.lower()
               for text in allergy_claim["localized_unknowns"]), allergy_claim["localized_unknowns"]

    second = client.post(endpoint, headers=headers, json={
        "request_id": str(uuid4()), "question": "Prefer indoor visits.",
    })
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["guest_brief"]["brief_version"] == 2
    prefs_after_edit = second_body["guest_brief"]["local_guide_preferences"]
    assert prefs_after_edit["interests"] == ["quiet", "indoor"]
    assert prefs_after_edit["budget_amount"] == 100000
    assert prefs_after_edit["budget_strength"] == "hard"
    assert prefs_after_edit["allergy_requirements"] == ["peanut"]
    assert prefs_after_edit["hard_accessibility_needs"] == ["step_free"]
    assert provider.calls[-1]["guest_brief"]["data"]["local_guide_preferences"] == prefs_after_edit
    assert len(provider.calls) == 4
    assert first_body["trace"]["calls"] == second_body["trace"]["calls"] == 2
