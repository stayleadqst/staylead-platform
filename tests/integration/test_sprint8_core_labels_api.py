"""Fresh-cache core UI labels remain localized on reviewed local-guide turns."""

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
from staylead_platform.infrastructure.persistence.store import (
    apply_migrations,
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
)
from staylead_platform.platform.contracts.ai_provider import (
    GenerationRequest,
    GenerationResult,
    Usage,
)
from staylead_platform.platform.conversation.responses import presentation_labels
from staylead_platform.platform.conversation.responses.presentation_labels import LABEL_KEYS

pytestmark = pytest.mark.skipif(
    not os.getenv("STAYLEAD_S8_B_DATABASE_URL"), reason="isolated Sprint 8 B PostgreSQL database not configured",
)


LABELS = {
    "zh": {
        "send": "发送", "sending": "正在发送…", "copy": "复制", "copied": "已复制",
        "copy_failed": "无法复制", "retry_answer": "重试回答", "check_status": "检查回答状态",
        "brief": "当前旅行信息", "stay": "住宿", "nights": "晚", "adults": "成人",
        "children": "儿童", "age": "年龄", "unknown": "无法确认", "pending_age": "需要提供孩子年龄",
        "updated": "信息已更新", "partial_success": "信息已保存，回答待完成", "stale_answer": "此回答可能已过时",
        "ai_notice": "酒店信息人工智能助手", "synthetic_notice": "合成酒店信息演示体验",
    },
    "fr": {
        "send": "Envoyer", "sending": "Envoi…", "copy": "Copier", "copied": "Copié",
        "copy_failed": "Copie impossible", "retry_answer": "Réessayer la réponse", "check_status": "Vérifier la réponse",
        "brief": "Détails du séjour", "stay": "Séjour", "nights": "nuits", "adults": "adultes",
        "children": "enfants", "age": "âge", "unknown": "Non confirmé", "pending_age": "Âge de l'enfant requis",
        "updated": "Mis à jour", "partial_success": "Détails enregistrés, réponse en attente", "stale_answer": "Cette réponse peut être obsolète",
        "ai_notice": "Assistant IA pour les informations de l'hôtel", "synthetic_notice": "Démonstration avec données synthétiques",
    },
    "ar": {
        "send": "إرسال", "sending": "جارٍ الإرسال…", "copy": "نسخ", "copied": "تم النسخ",
        "copy_failed": "تعذر النسخ", "retry_answer": "أعد المحاولة", "check_status": "تحقق من حالة الإجابة",
        "brief": "تفاصيل الرحلة", "stay": "الإقامة", "nights": "ليالٍ", "adults": "بالغون",
        "children": "أطفال", "age": "العمر", "unknown": "غير مؤكد", "pending_age": "يلزم عمر الطفل",
        "updated": "تم التحديث", "partial_success": "تم حفظ التفاصيل والإجابة معلقة", "stale_answer": "قد تكون الإجابة قديمة",
        "ai_notice": "مساعد ذكاء اصطناعي لمعلومات الفندق", "synthetic_notice": "عرض توضيحي ببيانات اصطناعية",
    },
}


class CoreLabelProvider:
    def __init__(self, locale: str) -> None:
        self.locale = locale
        self.calls: list[dict[str, object]] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = json.loads(request.input_text)
        self.calls.append(payload)
        if "candidate_index" in payload:
            value: dict[str, object] = {
                "fact_ids": [], "guest_patch": None, "turn_intents": ["local_guide", "hotel_information"],
                "explicit_language_tag": self.locale, "inferred_language_tag": None,
            }
        elif payload.get("guest_brief_patch_enabled") is True:
            value = {
                "fact_ids": [], "guest_patch": None, "turn_intents": ["local_guide", "hotel_information"],
                "explicit_language_tag": self.locale, "inferred_language_tag": None,
                "supported_claims": [], "unknowns": [], "conflicts": [], "guest_claims": [],
                "guest_brief_refs": [], "label_bundle": {},
            }
        else:
            labels = LABELS[self.locale]
            requested = payload.get("missing_label_keys", [])
            value = {
                "supported_claims": [], "unknowns": [], "conflicts": [], "guest_patch": None,
                "turn_intents": ["local_guide", "hotel_information"], "guest_claims": [],
                "guest_clarification": None, "conversational_acknowledgement": None,
                "guest_brief_refs": [], "explicit_language_tag": None, "inferred_language_tag": None,
                "label_bundle": {key: labels[key] for key in requested if key in labels},
            }
        return GenerationResult(
            text=json.dumps(value, ensure_ascii=False), provider="offline-fake", deployment="s8-core-label-test",
            model="fake", request_id=f"core-label-{len(self.calls)}", usage=Usage(input_tokens=2, output_tokens=3, total_tokens=5),
        )


def _clear_pilot(engine) -> None:
    with engine.begin() as connection:
        connection.execute(delete(lifecycle_operations).where(lifecycle_operations.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(knowledge_media).where(knowledge_media.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(knowledge_facts).where(knowledge_facts.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(knowledge_sources).where(knowledge_sources.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(knowledge_packs).where(knowledge_packs.c.hotel_id == "HTL-S8-DEMO"))
        connection.execute(delete(hotels).where(hotels.c.hotel_id == "HTL-S8-DEMO"))


@pytest.mark.parametrize("locale,question,expected_domain_title", [
    ("zh", "请用中文推荐附近的餐厅和景点。", "当地推荐"),
    ("fr", "Répondez en français et suggérez des lieux proches.", "Suggestions locales"),
    ("ar", "أجب بالعربية واقترح أماكن قريبة.", "اقتراحات محلية"),
])
def test_local_guide_turn_has_complete_core_and_reviewed_domain_labels_in_two_calls(
    locale: str, question: str, expected_domain_title: str,
) -> None:
    database_url = os.environ["STAYLEAD_S8_B_DATABASE_URL"]
    engine = create_database_engine(database_url)
    apply_migrations(engine)
    _clear_pilot(engine)
    fixture_root = Path(__file__).resolve().parents[2] / "fixtures" / "hospitality"
    pack = fixture_root / "sprint8-local-guide-v1"
    imported = import_local_guide_pack(engine, pack, allowed_root=fixture_root)
    primary = next(item for item in imported["sources"] if item["source_id"] == "S8-GUIDE-PRIMARY")
    activate_local_guide_source(
        engine, pack, allowed_root=fixture_root, hotel_id="HTL-S8-DEMO", source_id=primary["source_id"],
        expected_generation=imported["generation"], expected_version=primary["version"],
        expected_source_hash=primary["source_hash"], operation_id=f"labels-{uuid4().hex}",
    )
    presentation_labels._CACHE.clear()
    provider = CoreLabelProvider(locale)
    settings = Settings(
        _env_file=None, environment="test", database_url=database_url, ai_provider="disabled",
        session_signing_secret=SecretStr(f"sprint-eight-core-labels-{locale}-test-signing-secret"),
    )
    client = TestClient(create_app(settings, engine=engine, provider=provider))
    opened = client.post("/v1/guest/sessions", json={"hotel_slug": "lotus-pilot-demo"})
    assert opened.status_code == 201, opened.text
    session = opened.json()
    response = client.post(
        f"/v1/guest/sessions/{session['session_id']}/messages",
        headers={"Authorization": f"Bearer {session['access_token']}"},
        json={"request_id": str(uuid4()), "question": question},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(provider.calls) == 2
    assert provider.calls[-1]["missing_label_keys"] == list(LABEL_KEYS)
    assert set(body["presentation"]["labels"]) == set(LABEL_KEYS)
    assert body["presentation"]["labels"]["send"] == LABELS[locale]["send"]
    assert body["presentation"]["labels"]["brief"] == LABELS[locale]["brief"]
    assert body["presentation"]["labels_fallback"] is False
    assert body["presentation"]["local_guide_labels"]["local_guide_title"] == expected_domain_title
    assert body["presentation"]["local_guide_labels"]["local_guide_unknown"]
    assert set(body["presentation"]["local_guide_labels"]) >= {"local_guide_title", "local_guide_unknown"}
