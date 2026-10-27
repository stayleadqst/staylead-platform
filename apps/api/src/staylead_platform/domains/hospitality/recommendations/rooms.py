"""Validate model-proposed room arrangements and calculate source-backed estimates."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError

from staylead_platform.domains.hospitality.schemas.room_advice import (
    RoomAdviceLocalizationPreparation,
    RoomAdviceOption,
    RoomAdvicePreparation,
    room_advice_localization_output_schema,
)
from staylead_platform.platform.contracts.room_advice import (
    RoomAdviceCandidate,
    RoomAdviceContext,
    RoomAdviceDraft,
    RoomAdviceHotelAnswer,
    RoomAdviceHotelClaim,
    RoomAdviceResult,
)

_CLAIM_TEMPLATES = {
    "claim.party_fit": "This arrangement fits the confirmed party and verified room rules.",
    "claim.bed_setup": "The listed bed setup matches the verified bed configuration.",
    "claim.reference_price": "Reference room-rate estimate for the stay: {amount} {currency}.",
    "claim.policy_confirmation": "Some room details still need confirmation.",
    "claim.accessibility_confirmation": "Accessibility fit is not confirmed for this room.",
    "claim.preference_tradeoff": "This option does not meet a bed-sharing or bed-type preference.",
    "claim.charges_confirmation": "Some child or extra bedding charges are not included in this estimate.",
}
_QUESTION_TEMPLATES = {
    "question.dates": "What are your check-in and check-out dates?",
    "question.party": "How many adults will stay?",
    "question.age": "How old is each child?",
    "question.room": "Which room requirement should I use?",
    "question.budget_strength": "Is this budget a hard limit or a target?",
    "question.accessibility_confirmation": (
        "Your access needs are recorded, but no checked option has confirmed them. "
        "Please ask the hotel to confirm whether the room can meet them."
    ),
    "question.rate_basis": "Could you confirm whether this rate is per room per night?",
    "question.rate_validity_window": "These stay dates fall outside the source rate period. Could you confirm current pricing?",
    "question.hard_budget_exceeded": "This arrangement exceeds the confirmed budget. Would you like to adjust the budget or try another arrangement?",
    "question.source_fact_conflict": "The room source records conflict. Could I look for another room arrangement?",
    "question.room_rule_conflict": "This arrangement conflicts with a confirmed room rule. Would you like me to try another arrangement?",
    "question.generic": "Could you confirm this room detail?",
}
_PRESENTATION_TEMPLATES = {**_CLAIM_TEMPLATES, **_QUESTION_TEMPLATES}
_CLAIM_KEYS = {code: f"claim.{code}" for code in (
    "party_fit", "bed_setup", "reference_price", "policy_confirmation",
    "accessibility_confirmation", "preference_tradeoff", "charges_confirmation",
)}
_QUESTION_FIELD_KEYS = {
    "dates.check_in": "question.dates", "dates.check_out": "question.dates",
    "party.adults": "question.party", "party.children.age": "question.age",
    "room_requirements.budget_strength": "question.budget_strength",
    "room_requirements.hard_accessibility_needs": "question.accessibility_confirmation",
    "room_advice": "question.room",
}
_OPEN_LOCALE_BUILTINS = {"en", "vi", "zh", "ja"}
_URL_OR_MARKUP = re.compile(r"(?:[a-z][a-z0-9+.-]{1,15}://|mailto:|www\.)|[<>]", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def _language(locale: str | None) -> str:
    return (locale or "en").split("-")[0].lower()


def _open_locale(locale: str | None) -> bool:
    return _language(locale) not in _OPEN_LOCALE_BUILTINS


def _valid_presentation_labels(raw: object) -> dict[str, str]:
    if not isinstance(raw, (list, tuple)):
        return {}
    labels: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            return {}
        key, text = item.get("key"), item.get("text")
        if key not in _PRESENTATION_TEMPLATES or key in labels or not isinstance(text, str):
            return {}
        template = _PRESENTATION_TEMPLATES[key]
        expected = set(_PLACEHOLDER.findall(template))
        found = _PLACEHOLDER.findall(text)
        if set(found) != expected or len(found) != len(expected):
            return {}
        without_placeholders = _PLACEHOLDER.sub("", text)
        if (not text.strip() or len(text) > 160 or _URL_OR_MARKUP.search(without_placeholders)
                or any(char in without_placeholders for char in "{}")
                or any(char.isdecimal() for char in without_placeholders)
                or any(unicodedata.category(char).startswith("C") for char in text)):
            return {}
        labels[key] = text.strip()
    return labels


def _result_question_key(result: RoomAdviceResult, field: object) -> str:
    if field == "room_requirements.budget_strength":
        return "question.budget_strength"
    if field == "room_requirements.hard_accessibility_needs":
        return (
            "question.accessibility_confirmation"
            if result.explanation_inputs.get("known_hard_accessibility_needs") is True
            else "question.room"
        )
    unknowns = set(result.explanation_inputs.get("unknowns", ()))
    conflicts = set(result.explanation_inputs.get("conflicts", ()))
    if "rate_basis" in unknowns:
        return "question.rate_basis"
    if "rate_validity_window" in unknowns:
        return "question.rate_validity_window"
    if field == "room_advice" and conflicts:
        conflict = next(iter(sorted(conflicts)))
        return {
            "hard_budget_exceeded": "question.hard_budget_exceeded",
            "source_fact_conflict": "question.source_fact_conflict",
        }.get(conflict, "question.room_rule_conflict")
    if isinstance(field, str):
        if field in _QUESTION_FIELD_KEYS:
            return _QUESTION_FIELD_KEYS[field]
        if field.startswith("party.children.") and field.endswith(".age"):
            return "question.age"
        if field.startswith("room_requirements."):
            return "question.room"
    return "question.generic"


def _needed_presentation_keys(result: RoomAdviceResult) -> tuple[str, ...]:
    keys = {
        _CLAIM_KEYS[rationale["claim_code"]]
        for option in result.options for rationale in option.get("rationale", ())
        if rationale.get("claim_code") in _CLAIM_KEYS
    }
    keys.update(_result_question_key(result, question.get("field")) for question in result.questions)
    return tuple(sorted(keys))


def _draft_rationale_presentation_keys(draft: RoomAdviceDraft) -> set[str]:
    """Rationale label keys explicitly attached to model candidates before M4 filtering."""
    keys = {
        _CLAIM_KEYS[claim_code]
        for option in draft.options for rationale in option.rationale
        if (claim_code := (rationale.get("claim_code") if isinstance(rationale, dict)
                           else getattr(rationale, "claim_code", None))) in _CLAIM_KEYS
    }
    return keys


def _project_checked_presentation_labels(
    result: RoomAdviceResult, draft: RoomAdviceDraft, candidate_labels: dict[str, str],
) -> dict[str, str]:
    """Bind labels to candidate claims or checked questions, then project all required keys."""
    needed = set(_needed_presentation_keys(result))
    allowed = _draft_rationale_presentation_keys(draft) | {
        key for key in needed if key.startswith("question.")
    }
    if not set(candidate_labels) <= allowed:
        return {}
    projected = {key: text for key, text in candidate_labels.items() if key in needed}
    return projected if set(projected) == needed else {}


def _source(fact: dict[str, Any], generation: int) -> dict[str, Any] | None:
    provenance = fact.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("source_generation", generation) != generation:
        return None
    if not provenance.get("source_id") or not provenance.get("source_version"):
        return None
    return {
        "source_id": provenance["source_id"],
        "source_version": provenance["source_version"],
        "source_hash": provenance.get("source_hash", ""),
        "source_generation": generation,
        "fact_id": fact.get("fact_id"),
    }


def _member_ids(brief: dict[str, Any]) -> tuple[set[str], dict[str, int | None], int | None]:
    party = brief.get("party") or {}
    adults = party.get("adults")
    children = party.get("children") or []
    members: set[str] = set()
    ages: dict[str, int | None] = {}
    if isinstance(adults, int) and not isinstance(adults, bool) and 1 <= adults <= 30:
        for index in range(1, adults + 1):
            members.add(f"adult-{index}")
            ages[f"adult-{index}"] = None
    for child in children:
        if not isinstance(child, dict) or not isinstance(child.get("member_id"), str):
            continue
        member_id = child["member_id"]
        members.add(member_id)
        age = child.get("age")
        ages[member_id] = age if isinstance(age, int) and not isinstance(age, bool) else None
    return members, ages, adults if isinstance(adults, int) else None


def _nights(brief: dict[str, Any]) -> int | None:
    dates = brief.get("dates") or {}
    try:
        check_in = date.fromisoformat(dates["check_in"])
        check_out = date.fromisoformat(dates["check_out"])
    except (KeyError, TypeError, ValueError):
        return None
    count = (check_out - check_in).days
    return count if count > 0 else None


def _rate_covers_stay(rate: dict[str, Any], brief: dict[str, Any]) -> bool | None:
    """Check charged nights against the source window; checkout day is not charged."""
    dates = brief.get("dates") or {}
    try:
        check_in = date.fromisoformat(dates["check_in"])
        check_out = date.fromisoformat(dates["check_out"])
        valid_from = date.fromisoformat(rate["valid_from"])
        valid_to = date.fromisoformat(rate["valid_to"])
    except (KeyError, TypeError, ValueError):
        return None
    if check_out <= check_in:
        return None
    return check_in >= valid_from and check_out.fromordinal(check_out.toordinal() - 1) <= valid_to


def _active_facts(context: RoomAdviceContext) -> tuple[dict[str, Any], ...]:
    active = []
    utc_day = datetime.now(UTC).date().isoformat()
    for fact in context.facts:
        if (fact.get("hotel_id") != context.hotel_id
                or fact.get("status") not in {"confirmed", "unknown", "needs_confirmation"}
                or fact.get("valid_from", "9999-12-31") > utc_day
                or fact.get("valid_to", "0000-01-01") < utc_day
                or _source(fact, context.source_generation) is None):
            continue
        active.append(fact)
    return tuple(active)


def _localized_rationale(
    claim_code: str, locale: str | None, *, subtotal: int | None,
    currency: str | None, presentation_labels: dict[str, str] | None = None,
) -> tuple[str, str, bool]:
    language = _language(locale)
    labels = {
        "en": {
            "party_fit": "This arrangement fits the confirmed party and verified room rules.",
            "bed_setup": "The listed bed setup matches the verified bed configuration.",
            "reference_price": f"Reference room-rate estimate for the stay: {subtotal} {currency}.",
            "policy_confirmation": "Some room details still need confirmation.",
            "accessibility_confirmation": "Accessibility fit is not confirmed for this room.",
            "preference_tradeoff": "This option does not meet a bed-sharing or bed-type preference.",
            "charges_confirmation": "Some child or extra bedding charges are not included in this estimate.",
        },
        "vi": {
            "party_fit": "Phương án này phù hợp với số khách và quy tắc phòng đã xác nhận.",
            "bed_setup": "Cách bố trí giường khớp với cấu hình giường đã xác nhận.",
            "reference_price": f"Giá phòng tham khảo cho kỳ lưu trú: {subtotal} {currency}.",
            "policy_confirmation": "Một số chi tiết về phòng cần được xác nhận thêm.",
            "accessibility_confirmation": "Chưa xác nhận được mức độ phù hợp về khả năng tiếp cận.",
            "preference_tradeoff": "Phương án này chưa đáp ứng ưu tiên về chia sẻ giường hoặc loại giường.",
            "charges_confirmation": "Ước tính này chưa gồm một số khoản phí cho trẻ em hoặc giường bổ sung.",
        },
        "zh": {
            "party_fit": "此安排符合已确认的入住人数和房间规则。",
            "bed_setup": "所列床位安排符合已核实的床位配置。",
            "reference_price": f"本次入住的参考房费估算：{subtotal} {currency}。",
            "policy_confirmation": "部分房间信息仍需确认。",
            "accessibility_confirmation": "此房间的无障碍适配情况尚未确认。",
            "preference_tradeoff": "此方案未满足一项床位共享或床型偏好。",
            "charges_confirmation": "此估算未包含部分儿童费用或额外床位费用。",
        },
        "ja": {
            "party_fit": "この配置は、確認済みの人数と客室ルールに適合しています。",
            "bed_setup": "記載されたベッド配置は、確認済みの構成に一致します。",
            "reference_price": f"滞在全体の参考室料：{subtotal} {currency}。",
            "policy_confirmation": "客室に関する一部の情報は確認が必要です。",
            "accessibility_confirmation": "この客室のバリアフリー適合性は未確認です。",
            "preference_tradeoff": "この案は希望されたベッド配置の一部に合っていません。",
            "charges_confirmation": "この見積もりには一部の子ども料金や追加ベッド料金が含まれていません。",
        },
    }
    if language not in labels and presentation_labels:
        template = presentation_labels.get(_CLAIM_KEYS[claim_code])
        if template:
            return template.format(amount=subtotal, currency=currency), language, False
    labels_for_language = labels.get(language, labels["en"])
    return labels_for_language[claim_code], language if language in labels else "en", language not in labels


def _localized_question(
    field: object, locale: str | None, presentation_labels: dict[str, str] | None = None,
) -> tuple[str | None, str, bool]:
    if not isinstance(field, str):
        return None, "en", True
    if field in {"dates.check_in", "dates.check_out"}:
        key = "dates"
    elif field == "party.adults":
        key = "party"
    elif field == "party.children.age" or field.startswith("party.children.") and field.endswith(".age"):
        key = "age"
    elif field == "room_requirements.budget_strength":
        key = "budget_strength"
    elif field == "room_requirements.hard_accessibility_needs":
        key = "accessibility_confirmation"
    elif field == "room_advice" or field.startswith("room_requirements."):
        key = "room"
    else:
        return None, "en", True
    language = _language(locale)
    questions = {
        "en": {"dates": "What are your check-in and check-out dates?",
               "party": "How many adults will stay?", "age": "How old is each child?",
               "room": "Which room requirement should I use?",
               "budget_strength": "Is this budget a hard limit or a target?",
               "accessibility_confirmation": (
                   "Your access needs are recorded, but no checked option has confirmed them. "
                   "Please ask the hotel to confirm whether the room can meet them."
               )},
        "vi": {"dates": "Bạn nhận phòng và trả phòng vào ngày nào?",
               "party": "Có bao nhiêu người lớn sẽ lưu trú?", "age": "Mỗi trẻ bao nhiêu tuổi?",
               "room": "Tôi nên áp dụng yêu cầu phòng nào?",
               "budget_strength": "Ngân sách này là giới hạn bắt buộc hay mức mục tiêu?",
               "accessibility_confirmation": (
                   "Tôi đã ghi nhận yêu cầu tiếp cận, nhưng chưa có phương án nào được xác nhận là đáp ứng. "
                   "Vui lòng nhờ khách sạn xác nhận phòng có đáp ứng các yêu cầu này không."
               )},
        "zh": {"dates": "您的入住和退房日期是什么时候？",
               "party": "将有几位成人入住？", "age": "每位儿童分别几岁？",
               "room": "您希望我采用哪项房间要求？",
               "budget_strength": "这项预算是硬性上限还是目标金额？",
               "accessibility_confirmation": (
                   "我已记录您的无障碍需求，但目前没有已核实的方案确认能够满足。请向酒店确认客房是否符合这些需求。"
               )},
        "ja": {"dates": "チェックイン日とチェックアウト日を教えてください。",
               "party": "宿泊する大人は何人ですか？", "age": "お子様はそれぞれ何歳ですか？",
               "room": "どの客室条件を適用しますか？",
               "budget_strength": "この予算は上限ですか、それとも目標額ですか？",
               "accessibility_confirmation": (
                   "アクセシビリティのご要望を記録しましたが、確認済みの案では対応できると確認できていません。客室が要件を満たすかホテルにご確認ください。"
               )},
    }
    label_key = _QUESTION_FIELD_KEYS.get(field)
    if label_key is None:
        label_key = f"question.{key}"
    if language not in questions and presentation_labels and label_key in presentation_labels:
        return presentation_labels[label_key], language, False
    return (questions.get(language, questions["en"])[key],
            language if language in questions else "en", language not in questions)


def _localized_result_question(
    result: RoomAdviceResult, field: object, locale: str | None,
    presentation_labels: dict[str, str] | None = None,
) -> tuple[str, str, bool]:
    language = _language(locale)
    unknowns = set(result.explanation_inputs.get("unknowns", ()))
    conflicts = set(result.explanation_inputs.get("conflicts", ()))
    if field == "room_requirements.budget_strength":
        return _localized_question(field, locale, presentation_labels)
    if (field == "room_requirements.hard_accessibility_needs"
            and result.explanation_inputs.get("known_hard_accessibility_needs") is not True):
        return _localized_question("room_advice", locale, presentation_labels)
    if "rate_basis" in unknowns:
        labels = {
            "en": "Could you confirm whether this rate is per room per night?",
            "vi": "Bạn xác nhận mức giá này tính theo phòng mỗi đêm được không?",
            "zh": "请确认此价格是否按每间客房每晚计算。",
            "ja": "この料金が1室1泊あたりかどうか確認していただけますか？",
        }
        if language not in labels and presentation_labels and "question.rate_basis" in presentation_labels:
            return presentation_labels["question.rate_basis"], language, False
        return labels.get(language, labels["en"]), language if language in labels else "en", language not in labels
    if "rate_validity_window" in unknowns:
        labels = {
            "en": "These stay dates fall outside the source rate period. Could you confirm current pricing?",
            "vi": "Ngày lưu trú nằm ngoài thời hạn của giá nguồn. Bạn có thể xác nhận giá hiện tại không?",
            "zh": "入住日期超出来源价格的有效期。请确认当前价格。",
            "ja": "宿泊日が料金情報の有効期間外です。現在の料金をご確認いただけますか？",
        }
        if language not in labels and presentation_labels and "question.rate_validity_window" in presentation_labels:
            return presentation_labels["question.rate_validity_window"], language, False
        return labels.get(language, labels["en"]), language if language in labels else "en", language not in labels
    if field == "room_advice" and conflicts:
        labels_by_conflict = {
            "hard_budget_exceeded": {
                "en": "This arrangement exceeds the confirmed budget. Would you like to adjust the budget or try another arrangement?",
                "vi": "Phương án này vượt ngân sách đã xác nhận. Bạn muốn điều chỉnh ngân sách hay thử cách sắp xếp khác?",
                "zh": "此方案超出已确认的预算。您希望调整预算还是尝试其他安排？",
                "ja": "この案は確認済みの予算を超えています。予算を調整するか、別の案を試しますか？",
            },
            "source_fact_conflict": {
                "en": "The room source records conflict. Could I look for another room arrangement?",
                "vi": "Các nguồn thông tin về phòng đang mâu thuẫn. Tôi có thể tìm cách sắp xếp phòng khác không?",
                "zh": "房间来源信息存在冲突。我可以为您查找其他房间安排吗？",
                "ja": "客室の情報源に食い違いがあります。別の客室構成を探しましょうか？",
            },
        }
        conflict = next(iter(sorted(conflicts)))
        conflict_key = {
            "hard_budget_exceeded": "question.hard_budget_exceeded",
            "source_fact_conflict": "question.source_fact_conflict",
        }.get(conflict, "question.room_rule_conflict")
        if language not in labels_by_conflict.get(conflict, {}) and presentation_labels and conflict_key in presentation_labels:
            return presentation_labels[conflict_key], language, False
        labels = labels_by_conflict.get(conflict, {
            "en": "This arrangement conflicts with a confirmed room rule. Would you like me to try another arrangement?",
            "vi": "Phương án này mâu thuẫn với quy tắc phòng đã xác nhận. Bạn muốn tôi thử cách sắp xếp khác không?",
            "zh": "此安排与已确认的房间规则冲突。您希望我尝试其他安排吗？",
            "ja": "この案は確認済みの客室ルールと矛盾しています。別の配置を試しますか？",
        })
        return labels.get(language, labels["en"]), language if language in labels else "en", language not in labels
    text, question_locale, fallback = _localized_question(field, locale, presentation_labels)
    if text is None:
        if language == "ja":
            return "客室について確認させてください。", "ja", False
        if _open_locale(locale) and presentation_labels and "question.generic" in presentation_labels:
            return presentation_labels["question.generic"], _language(locale), False
        return _localized_question("room_advice", locale, presentation_labels)
    return text, question_locale, fallback


class HospitalityRoomAdvice:
    """Domain use case; model proposes, source-aware deterministic code validates."""

    @staticmethod
    def eligible_facts(context: RoomAdviceContext) -> tuple[dict[str, Any], ...]:
        """Return only current same-hotel facts bound to the trusted generation."""
        return _active_facts(context)

    @staticmethod
    def preparation_instructions(
        locale: str | None, *, include_hotel_answer: bool = False,
        include_presentation_labels: bool = False,
    ) -> str:
        from staylead_platform.domains.hospitality.prompts.room_advice import (
            ROOM_ADVICE_INSTRUCTIONS,
        )

        language = locale or "the guest's established language"
        mixed_faq = """For the mixed hotel-information plus room-advice request, also provide
`hotel_answer` with `supported_claims`, `unknowns`, and `conflicts`. Answer the guest's
hotel-information question only from `hotel_information_facts`; every supported claim
must include its exact supporting `fact_ids`. Keep claims concise and literal. Do not
include room recommendation rationale here; that belongs in candidate rationale codes.
When there is no supported answer, return a concise `unknowns` entry. The server validates
this answer against the selected facts before release."""
        suffix = f"\n{mixed_faq}" if include_hotel_answer else ""
        labels = ""
        if include_presentation_labels:
            labels = """
For open-language presentation, return `presentation_labels` as a list of `{key,text}`. Translate
only the supplied `presentation_templates` whose keys you actually use in returned `rationale`
or `questions`. Do not add explanations. Use only bounded keys in the schema. The
`claim.reference_price` template must contain exactly `{amount}` and `{currency}`; all other
templates have no placeholders. Leave numbers, URLs, factual claims, and extra keys out. The
server validates phrases and inserts checked amount/currency values itself.
"""
        return f"{ROOM_ADVICE_INSTRUCTIONS}{suffix}{labels}\nRespond in {language}."

    @staticmethod
    def preparation_output_schema(
        *, include_hotel_answer: bool = False, include_presentation_labels: bool = False,
    ) -> dict[str, Any]:
        from staylead_platform.domains.hospitality.schemas.room_advice import (
            room_advice_output_schema,
        )

        return room_advice_output_schema(
            include_hotel_answer=include_hotel_answer,
            include_presentation_labels=include_presentation_labels,
        )

    @staticmethod
    def relocalize(
        result: RoomAdviceResult, locale: str | None,
        presentation_labels: dict[str, str] | None = None,
    ) -> RoomAdviceResult:
        """Re-render trusted presentation text without changing a checked decision."""
        localized = deepcopy(result)
        labels = presentation_labels
        if labels is None and result.presentation_locale == locale:
            labels = result.presentation_labels
        labels = labels or {}
        needed = _needed_presentation_keys(result)
        if set(labels) != set(needed):
            labels = {}
        for option in localized.options:
            cost = option.get("cost") or {}
            for rationale in option.get("rationale") or []:
                text, rationale_locale, fallback = _localized_rationale(
                    rationale["claim_code"], locale,
                    subtotal=cost.get("total"), currency=cost.get("currency"),
                    presentation_labels=labels,
                )
                rationale.update({"text": text, "locale": rationale_locale,
                                  "locale_fallback": fallback,
                                  "presentation_key": _CLAIM_KEYS[rationale["claim_code"]]})
        for question in localized.questions:
            presentation_key = _result_question_key(localized, question.get("field"))
            text, question_locale, fallback = _localized_result_question(
                localized, question.get("field"), locale, labels,
            )
            question.update({"reason": text, "locale": question_locale,
                             "locale_fallback": fallback,
                             "presentation_key": presentation_key})
        return replace(
            localized, presentation_labels=dict(labels),
            presentation_locale=locale if labels else None,
        )

    @staticmethod
    def needs_presentation_labels(locale: str | None) -> bool:
        return _open_locale(locale)

    @staticmethod
    def presentation_templates() -> dict[str, str]:
        return dict(_PRESENTATION_TEMPLATES)

    @staticmethod
    def localization_request(
        result: RoomAdviceResult, locale: str | None,
    ) -> dict[str, Any] | None:
        if not _open_locale(locale):
            return None
        keys = _needed_presentation_keys(result)
        if not keys:
            return None
        return {
            "keys": keys,
            "instructions": (
                f"Translate only the supplied approved room-advice phrase templates into {locale}. "
                "Return each requested key exactly once and no extra text. Preserve exact placeholders. "
                "Do not add facts, numbers, URLs, or markup."
            ),
            "input": {"locale": locale, "presentation_templates": {key: _PRESENTATION_TEMPLATES[key] for key in keys}},
            "response_schema": room_advice_localization_output_schema(keys),
        }

    @staticmethod
    def parse_localization(
        text: str, *, expected_keys: tuple[str, ...], locale: str | None,
    ) -> dict[str, str]:
        if not _open_locale(locale):
            return {}
        try:
            parsed = RoomAdviceLocalizationPreparation.model_validate_json(text)
        except ValidationError:
            return {}
        labels = _valid_presentation_labels([
            item.model_dump(mode="json") for item in parsed.presentation_labels
        ])
        if set(labels) != set(expected_keys):
            return {}
        return labels

    @staticmethod
    def parse_draft(text: str) -> RoomAdviceDraft:
        parsed = RoomAdvicePreparation.model_validate_json(text)
        return RoomAdviceDraft(
            status="ready" if parsed.options else "needs_clarification",
            options=tuple(RoomAdviceCandidate(
                option_id=item.option_id,
                rooms=tuple(room.model_dump(mode="json") for room in item.rooms),
                assignments=tuple(assignment.model_dump(mode="json") for assignment in item.assignments),
                rationale=tuple(claim.model_dump(mode="json") for claim in item.rationale),
            ) for item in parsed.options),
            questions=tuple(item.model_dump(mode="json") for item in parsed.questions),
            hotel_answer=(RoomAdviceHotelAnswer(
                supported_claims=tuple(RoomAdviceHotelClaim(
                    text=claim.text, fact_ids=tuple(claim.fact_ids),
                ) for claim in parsed.hotel_answer.supported_claims),
                unknowns=tuple(parsed.hotel_answer.unknowns),
                conflicts=tuple(parsed.hotel_answer.conflicts),
            ) if parsed.hotel_answer is not None else None),
            presentation_labels=tuple(item.model_dump(mode="json") for item in parsed.presentation_labels),
        )

    @staticmethod
    def select_facts(
        facts: tuple[dict[str, Any], ...], *, question: str,
        brief_data: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        del question, brief_data
        # Keep machine-readable catalog/rates plus guest-approved narrative policies
        # needed for accessibility, guardian and sharing trade-offs.
        selected = [fact for fact in facts if (
            fact.get("field") in {"room_type", "reference_rate"}
            or fact.get("topic") in {"room", "rooms", "occupancy", "accessibility"}
        )]
        return tuple(selected[:80])

    async def recommend(
        self, *, context: RoomAdviceContext, draft: RoomAdviceDraft,
        deadline: float | None = None,
    ) -> RoomAdviceResult:
        del deadline  # Bounds are owned by the caller/provider; this operation is deterministic.
        active = _active_facts(context)
        presentation_labels = _valid_presentation_labels(draft.presentation_labels)

        def relocalize_checked(result: RoomAdviceResult) -> RoomAdviceResult:
            labels = _project_checked_presentation_labels(result, draft, presentation_labels)
            return self.relocalize(result, context.locale, labels)

        source_facts = {fact["fact_id"]: fact for fact in active}
        room_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in active:
            if fact.get("field") == "room_type" and isinstance(fact.get("value"), dict):
                room_type_id = fact["value"].get("room_type_id")
                if isinstance(room_type_id, str):
                    room_groups[room_type_id].append(fact)
        conflicted_room_ids = {
            room_id for room_id, group in room_groups.items()
            if len({repr(fact.get("value")) for fact in group}) > 1
        }
        rooms = {room_id: group[0] for room_id, group in room_groups.items()
                 if room_id not in conflicted_room_ids}
        rates = [fact for fact in active
                 if fact.get("field") == "reference_rate" and isinstance(fact.get("value"), dict)]
        rate_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in rates:
            rate_type_id = fact["value"].get("room_type_id")
            if isinstance(rate_type_id, str):
                rate_groups[rate_type_id].append(fact)
        conflicted_rate_types = {
            room_id for room_id, group in rate_groups.items()
            if len({repr(fact.get("value")) for fact in group}) > 1
        }
        members, ages, adults = _member_ids(context.brief_data)
        pending = set(context.pending_fields)
        questions = []
        for item in draft.questions:
            field = item.get("field")
            if isinstance(field, str):
                questions.append({"field": field})
        if adults is None or not members:
            questions.append({"field": "party.adults"})
            result = RoomAdviceResult(
                status="needs_clarification", brief_version=context.brief_version,
                source_generation=context.source_generation,
                source_refs=tuple(_source(f, context.source_generation) for f in active),
                questions=tuple(questions), explanation_inputs={"unknowns": ["party size"]},
                hotel_answer=draft.hotel_answer,
            )
            return relocalize_checked(result)
        if len(members) > 40:
            result = RoomAdviceResult(
                status="processing_limit", brief_version=context.brief_version,
                source_generation=context.source_generation,
                source_refs=tuple(_source(f, context.source_generation) for f in active),
                questions=tuple(questions), explanation_inputs={"unknowns": ["party exceeds checked assignment limit"]},
                hotel_answer=draft.hotel_answer,
            )
            return relocalize_checked(result)
        if any(field == "party.children.member" or field.startswith("party.children.") for field in pending):
            questions.append({"field": "party.children.age"})
        requirements = context.brief_data.get("room_requirements") or {}
        budget_strength_unknown = (
            requirements.get("budget_amount") is not None
            and requirements.get("budget_strength") not in {"hard", "target"}
        )
        if budget_strength_unknown:
            pending.add("room_requirements.budget_strength")
        if "room_requirements.budget_strength" in pending:
            questions.append({"field": "room_requirements.budget_strength"})
        other_pending_room_requirements = (
            pending - {"room_requirements.budget_strength"}
            if budget_strength_unknown else pending
        )
        if "room_requirements" in other_pending_room_requirements or any(
            field.startswith("room_requirements.") for field in other_pending_room_requirements
        ):
            questions.append({"field": "room_advice"})
            result = RoomAdviceResult(
                status="needs_clarification", brief_version=context.brief_version,
                source_generation=context.source_generation,
                source_refs=tuple(_source(f, context.source_generation) for f in active),
                questions=tuple(questions),
                explanation_inputs={"unknowns": ["room requirements"]},
                hotel_answer=draft.hotel_answer,
            )
            return relocalize_checked(result)
        if draft.status != "ready" or not draft.options:
            explanation_inputs = {"unknowns": ["no checked room candidate"]}
            if (requirements.get("hard_accessibility_needs")
                    and "room_requirements.hard_accessibility_needs" not in pending):
                explanation_inputs["known_hard_accessibility_needs"] = True
            result = RoomAdviceResult(
                status=(draft.status if draft.status != "ready" else "needs_clarification"),
                brief_version=context.brief_version, source_generation=context.source_generation,
                source_refs=tuple(_source(f, context.source_generation) for f in active),
                questions=tuple(questions), explanation_inputs=explanation_inputs,
                hotel_answer=draft.hotel_answer,
            )
            return relocalize_checked(result)

        options: list[dict[str, Any]] = []
        seen_option_ids: set[str] = set()
        all_claim_ids: set[str] = set()
        if draft.hotel_answer is not None:
            all_claim_ids.update(
                fact_id for claim in draft.hotel_answer.supported_claims for fact_id in claim.fact_ids
            )
        invalid_reasons: list[str] = []
        rejected_alternatives: list[dict[str, Any]] = []
        for raw in draft.options:
            try:
                candidate = RoomAdviceOption.model_validate({
                    "option_id": raw.option_id, "rooms": raw.rooms, "assignments": raw.assignments,
                    "rationale": raw.rationale,
                })
            except (TypeError, ValidationError):
                invalid_reasons.append("invalid_candidate_shape")
                continue
            if candidate.option_id in seen_option_ids:
                invalid_reasons.append("duplicate_option_id")
                continue
            seen_option_ids.add(candidate.option_id)
            if len({item.room_index for item in candidate.rooms}) != len(candidate.rooms):
                invalid_reasons.append("duplicate_room_index")
                continue
            room_records = {item.room_index: rooms.get(item.room_type_id) for item in candidate.rooms}
            if any(item is None for item in room_records.values()):
                if any(item.room_type_id in conflicted_room_ids for item in candidate.rooms):
                    invalid_reasons.append("source_fact_conflict")
                    all_claim_ids.update(fact["fact_id"] for room in candidate.rooms
                                         for fact in room_groups.get(room.room_type_id, ()))
                else:
                    invalid_reasons.append("unsupported_room_type")
                continue
            # Bind the decision, including negative/unknown checks, to the approved
            # room source that was actually evaluated.
            all_claim_ids.update(record["fact_id"] for record in room_records.values() if record)
            assignments = [item.model_dump(mode="json") for item in candidate.assignments]
            assigned_ids = [item["member_id"] for item in assignments]
            if len(assigned_ids) != len(set(assigned_ids)) or set(assigned_ids) != members:
                invalid_reasons.append("party_assignment_mismatch")
                continue
            room_indices = set(room_records)
            if room_indices != set(range(len(room_records))) or any(
                item["room_index"] not in room_indices for item in assignments
            ) or {item["room_index"] for item in assignments} != room_indices:
                invalid_reasons.append("room_count_mismatch")
                continue
            requirements = context.brief_data.get("room_requirements") or {}
            if isinstance(requirements.get("max_rooms"), int) and len(room_records) > requirements["max_rooms"]:
                invalid_reasons.append("hard_room_count_exceeded")
                continue
            by_room: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for item in assignments:
                by_room[item["room_index"]].append(item)
            checks: list[dict[str, Any]] = []
            feasible = True
            unpriced_bedding = False
            for room_index, guests in by_room.items():
                room_fact = room_records[room_index]
                assert room_fact is not None
                room = room_fact["value"]
                room_adults = sum(item["member_id"].startswith("adult-") for item in guests)
                room_children = len(guests) - room_adults
                occupancy = room.get("max_occupancy")
                max_adults = room.get("max_adults")
                max_children = room.get("max_children")
                if not all(isinstance(v, int) and v >= 0 for v in (occupancy, max_adults, max_children)):
                    checks.append({"code": "occupancy", "status": "unknown", "fact_ids": [room_fact["fact_id"]]})
                elif (len(guests) > occupancy or room_adults > max_adults or room_children > max_children):
                    feasible = False
                    checks.append({"code": "occupancy", "status": "conflict", "fact_ids": [room_fact["fact_id"]]})
                else:
                    checks.append({"code": "occupancy", "status": "pass", "fact_ids": [room_fact["fact_id"]]})
                beds = room.get("beds") if isinstance(room.get("beds"), list) else []
                instances = [bed for bed in beds if isinstance(bed, dict)
                             for _ in range(int(bed.get("count", 0)))
                             if isinstance(bed.get("count"), int) and bed.get("count", 0) > 0]
                selected_bed_types = {item.get("bed_type") for item in guests}
                hard_beds = requirements.get("hard_bed_types") or []
                special_needs = {"cot": any(any(token in value.casefold() for token in ("cot", "crib", "nôi"))
                                               for value in hard_beds if isinstance(value, str)),
                                 "extra_bed": any(value.casefold() == "extra_bed" or "extra bed" in value.casefold() or "giường phụ" in value.casefold()
                                                  for value in hard_beds if isinstance(value, str))}
                ordinary_hard_beds = [value for value in hard_beds
                                      if isinstance(value, str) and value.casefold() != "extra_bed"
                                      and not any(token in value.casefold() for token in (
                                          "cot", "crib", "nôi", "extra bed", "giường phụ",
                                      ))]
                if ordinary_hard_beds and not selected_bed_types <= set(ordinary_hard_beds):
                    feasible = False
                    checks.append({"code": "hard_bed_type", "status": "conflict", "fact_ids": [room_fact["fact_id"]]})
                avoided = selected_bed_types.intersection(requirements.get("avoided_bed_types") or [])
                if avoided:
                    checks.append({"code": "avoided_bed_type", "status": "not_met", "fact_ids": [room_fact["fact_id"]]})
                preferred = requirements.get("preferred_bed_types") or []
                if preferred:
                    checks.append({"code": "preferred_bed_type", "status": "pass" if selected_bed_types.intersection(preferred)
                                   else "not_met", "fact_ids": [room_fact["fact_id"]]})
                sharing_preference = requirements.get("sharing")
                for special_name, key in (("cot", "cot_rule"), ("extra_bed", "extra_bed")):
                    if not special_needs[special_name]:
                        continue
                    policy = room.get(key) or {}
                    if policy.get("allowed") is False:
                        cot_text = str(room.get("cot", "")).casefold() if special_name == "cot" else ""
                        prose_contradicts = special_name == "cot" and (
                            any(token in cot_text for token in ("free", "miễn phí", "vnd", "usd", "eur"))
                            or bool(re.search(r"\d", cot_text))
                        )
                        if prose_contradicts:
                            checks.append({"code": f"{special_name}_policy", "status": "unknown",
                                           "fact_ids": [room_fact["fact_id"]]})
                            unpriced_bedding = True
                        else:
                            feasible = False
                            checks.append({"code": f"{special_name}_policy", "status": "conflict", "fact_ids": [room_fact["fact_id"]]})
                    elif policy.get("allowed") is True:
                        checks.append({"code": f"{special_name}_policy", "status": "pass", "fact_ids": [room_fact["fact_id"]]})
                        unpriced_bedding = True
                    else:
                        checks.append({"code": f"{special_name}_policy", "status": "unknown", "fact_ids": [room_fact["fact_id"]]})
                        unpriced_bedding = True
                by_instance = Counter(item.get("bed_index") for item in guests)
                if (not instances or any(item.get("bed_index") is None or not item.get("bed_type")
                                          for item in guests)):
                    checks.append({"code": "bed_configuration", "status": "unknown", "fact_ids": [room_fact["fact_id"]]})
                elif any(not isinstance(index, int) or index >= len(instances)
                         or item.get("bed_type") != instances[index].get("type")
                         for item in guests for index in [item.get("bed_index")]) or any(count > int(instances[index].get("occupant_capacity", 0))
                         for index, count in by_instance.items()):
                    feasible = False
                    checks.append({"code": "bed_configuration", "status": "conflict", "fact_ids": [room_fact["fact_id"]]})
                elif any(count > 1 for count in by_instance.values()):
                    if sharing_preference == "avoid":
                        feasible = False
                        checks.append({"code": "bed_sharing_preference", "status": "conflict", "fact_ids": [room_fact["fact_id"]]})
                    elif sharing_preference == "prefer":
                        checks.append({"code": "bed_sharing_preference", "status": "pass", "fact_ids": [room_fact["fact_id"]]})
                    sharing_groups = (context.brief_data.get("party") or {}).get("bed_sharing") or []
                    consent_ok = True
                    consent_known = True
                    for bed_index, count in by_instance.items():
                        if count <= 1:
                            continue
                        actual = {item["member_id"] for item in guests if item.get("bed_index") == bed_index}
                        rule = next((group for group in sharing_groups
                                     if set(group.get("member_ids", ())) == actual), None)
                        if rule is None:
                            consent_known = False
                        elif rule.get("allow_share") is not True:
                            consent_ok = False
                    if not consent_known:
                        checks.append({"code": "bed_sharing_consent", "status": "unknown", "fact_ids": [room_fact["fact_id"]]})
                    elif not consent_ok:
                        feasible = False
                        checks.append({"code": "bed_sharing_consent", "status": "conflict", "fact_ids": [room_fact["fact_id"]]})
                    else:
                        checks.append({"code": "bed_configuration", "status": "pass", "fact_ids": [room_fact["fact_id"]]})
                        checks.append({"code": "bed_sharing_consent", "status": "pass", "fact_ids": [room_fact["fact_id"]]})
                else:
                    checks.append({"code": "bed_configuration", "status": "pass", "fact_ids": [room_fact["fact_id"]]})
                    if sharing_preference == "prefer":
                        checks.append({"code": "bed_sharing_preference", "status": "not_met", "fact_ids": [room_fact["fact_id"]]})
                separate_bed_members = {
                    child.get("member_id") for child in (context.brief_data.get("party") or {}).get("children", [])
                    if child.get("requires_separate_bed") is True
                }
                separate_assignments = [item for item in guests if item["member_id"] in separate_bed_members]
                if separate_assignments:
                    def sleeping_surface(item: dict[str, Any]) -> tuple[int, str | None] | None:
                        index = item.get("bed_index")
                        if not isinstance(index, int):
                            return None
                        if item.get("bed_type") == "bunk":
                            position = item.get("bed_position")
                            return (index, position) if position in {"upper", "lower"} else None
                        return index, None

                    surface_counts = Counter(
                        surface for item in guests if (surface := sleeping_surface(item)) is not None
                    )
                    required_surfaces = [sleeping_surface(item) for item in separate_assignments]
                    if (any(surface is None for surface in required_surfaces)
                            or any(sleeping_surface(item) is None for item in guests)):
                        checks.append({"code": "separate_bed_requirement", "status": "unknown",
                                       "fact_ids": [room_fact["fact_id"]]})
                    elif any(surface_counts[surface] > 1 for surface in required_surfaces):
                        feasible = False
                        checks.append({"code": "separate_bed_requirement", "status": "conflict",
                                       "fact_ids": [room_fact["fact_id"]]})
                    else:
                        checks.append({"code": "separate_bed_requirement", "status": "pass",
                                       "fact_ids": [room_fact["fact_id"]]})
                bunk_positions = Counter(
                    (item.get("bed_index"), item.get("bed_position"))
                    for item in guests if item.get("bed_type") == "bunk"
                )
                if any(count > 1 for count in bunk_positions.values()):
                    feasible = False
                    checks.append({"code": "bunk_position_capacity", "status": "conflict",
                                   "fact_ids": [room_fact["fact_id"]]})
                for assignment in guests:
                    if assignment.get("bed_type") != "bunk" or assignment["member_id"].startswith("adult-"):
                        continue
                    age = ages.get(assignment["member_id"])
                    position = assignment.get("bed_position")
                    if position is None:
                        checks.append({"code": "bunk_position_policy", "status": "unknown", "fact_ids": [room_fact["fact_id"]]})
                    elif position == "upper" and isinstance(age, int) and age < 6:
                        feasible = False
                        checks.append({"code": "bunk_position_policy", "status": "conflict", "fact_ids": [room_fact["fact_id"]]})
                    elif position == "upper" and age == 6:
                        # The prose says the upper bunk starts at age six while the
                        # authored age-six boundary example prohibits it. Preserve both.
                        checks.append({"code": "bunk_position_policy", "status": "unknown", "fact_ids": [room_fact["fact_id"]]})
                    else:
                        checks.append({"code": "bunk_position_policy", "status": "pass", "fact_ids": [room_fact["fact_id"]]})
                if room_children:
                    if any(ages.get(item["member_id"]) is None for item in guests if not item["member_id"].startswith("adult-")):
                        checks.append({"code": "child_age_policy", "status": "unknown", "fact_ids": [room_fact["fact_id"]]})
                    else:
                        for item in guests:
                            age = ages.get(item["member_id"])
                            if age is None or item["member_id"].startswith("adult-"):
                                continue
                            policy = room.get("age_policy") or {}
                            minimum = policy.get("room_min_age_inclusive")
                            maximum = policy.get("room_max_age_exclusive")
                            if isinstance(minimum, int) and age < minimum or isinstance(maximum, int) and age >= maximum:
                                feasible = False
                                checks.append({"code": "child_age_policy", "status": "conflict", "fact_ids": [room_fact["fact_id"]]})
                                break
                        else:
                            checks.append({"code": "child_age_policy", "status": "pass", "fact_ids": [room_fact["fact_id"]]})
                    guardian_links = (context.brief_data.get("party") or {}).get("guardians") or {}
                    guardian_ok = True
                    for child in guests:
                        member_id = child["member_id"]
                        if member_id.startswith("adult-"):
                            continue
                        age = ages.get(member_id)
                        policy = room.get("age_policy") or {}
                        threshold = policy.get("guardian_required_below_age_exclusive", 18)
                        if isinstance(age, int) and isinstance(threshold, int) and age < threshold:
                            guardian_id = guardian_links.get(member_id)
                            if not guardian_id or guardian_id not in members or guardian_id not in {
                                item["member_id"] for item in guests
                            }:
                                guardian_ok = False
                    checks.append({"code": "guardian_relationship", "status": "pass" if guardian_ok else "unknown",
                                   "fact_ids": [room_fact["fact_id"]]})
                if requirements.get("hard_accessibility_needs"):
                    # The current approved room catalog carries free-text accessibility
                    # notes, not typed capabilities. Keep fit unverified until that source
                    # is structured; prose similarity cannot prove a hard requirement.
                    checks.append({"code": "accessibility", "status": "unknown", "fact_ids": [room_fact["fact_id"]]})
            if not feasible:
                invalid_reasons.append("candidate_fails_hard_room_check")
                continue
            rates_by_room = {
                index: next((fact for fact in rates
                             if fact["value"].get("room_type_id") == room_records[index]["value"].get("room_type_id")), None)
                for index in room_indices
            }
            if any(room_records[index]["value"].get("room_type_id") in conflicted_rate_types
                   for index in room_indices):
                invalid_reasons.append("source_fact_conflict")
                all_claim_ids.update(fact["fact_id"] for index in room_indices
                                     for fact in rate_groups.get(room_records[index]["value"].get("room_type_id"), ()))
                continue
            all_claim_ids.update(rate["fact_id"] for rate in rates_by_room.values() if rate)
            nights = _nights(context.brief_data)
            currencies = {rate["value"].get("currency") for rate in rates_by_room.values() if rate}
            nightly_complete = all(
                rate is not None and isinstance(rate["value"].get("amount"), int)
                and rate["value"].get("amount", -1) >= 0
                and rate["value"].get("currency")
                and (rate["value"].get("price_basis") or {}).get("unit") == "room_night"
                and (_rate_covers_stay(rate, context.brief_data) is not False)
                and isinstance((rate["value"].get("price_basis") or {}).get("included_adults"), int)
                for rate in rates_by_room.values()
            ) and len(currencies) == 1
            nightly_subtotal = sum(rate["value"]["amount"] for rate in rates_by_room.values()) if nightly_complete else None
            base_complete = nightly_complete and nights is not None
            subtotal = nightly_subtotal * nights if base_complete and nightly_subtotal is not None else None
            base_subtotal = subtotal
            complete = base_complete
            additional_total = 0
            breakdown = []
            rate_basis_unknown = False
            rate_window_unknown = False
            for index, rate in rates_by_room.items():
                room_guests = by_room[index]
                child_members = [item["member_id"] for item in room_guests
                                 if not item["member_id"].startswith("adult-")]
                age_limit = (room_records[index]["value"].get("age_policy") or {}).get(
                    "child_rate_age_max_exclusive"
                )
                child_count = 0
                adult_rate_child_count = 0
                unknown_rate_age_count = 0
                for member_id in child_members:
                    age = ages.get(member_id)
                    if not isinstance(age_limit, int) or age is None:
                        unknown_rate_age_count += 1
                    elif age < age_limit:
                        child_count += 1
                    else:
                        adult_rate_child_count += 1
                room_adult_count = sum(item["member_id"].startswith("adult-") for item in room_guests)
                room_priced_adult_count = room_adult_count + adult_rate_child_count
                if rate:
                    all_claim_ids.add(rate["fact_id"])
                    rate_unit = (rate["value"].get("price_basis") or {}).get("unit")
                    rate_covers_stay = _rate_covers_stay(rate, context.brief_data)
                    if rate_unit != "room_night":
                        complete = False
                        breakdown.append({"label": "reference room rate", "amount": None,
                                          "currency": rate["value"].get("currency"), "status": "unknown",
                                          "basis": f"unsupported rate basis ({rate_unit or 'unspecified'}); confirm a room-night rate",
                                          "fact_ids": [rate["fact_id"]]})
                        rate_basis_unknown = True
                    elif rate_covers_stay is False:
                        complete = False
                        rate_window_unknown = True
                        breakdown.append({"label": "reference room rate", "amount": None,
                                          "currency": rate["value"].get("currency"), "status": "unknown",
                                          "basis": "stay dates fall outside the source rate validity window",
                                          "fact_ids": [rate["fact_id"]]})
                    elif nights is not None and isinstance(rate["value"].get("amount"), int):
                        amount = rate["value"]["amount"] * nights
                        breakdown.append({"label": f"{room_records[index]['value'].get('name', 'Room')} reference rate",
                                          "amount": amount, "currency": rate["value"].get("currency"),
                                          "status": "known", "basis": f"1 room × {nights} night(s)",
                                          "fact_ids": [rate["fact_id"]]})
                    else:
                        complete = False
                        breakdown.append({"label": "reference room rate", "amount": None,
                                          "currency": rate["value"].get("currency"), "status": "unknown",
                                          "basis": "complete stay dates and rate required", "fact_ids": [rate["fact_id"]]})
                    if unknown_rate_age_count:
                        complete = False
                        breakdown.append({"label": "age-based guest charges", "amount": None,
                                          "currency": rate["value"].get("currency"), "status": "unknown",
                                          "basis": "source-backed child-rate age limit and guest age required",
                                          "fact_ids": [rate["fact_id"], room_records[index]["fact_id"]]})
                    if child_count and rate["value"].get("child_charge_status") not in {"included", "confirmed"}:
                        complete = False
                        breakdown.append({"label": "child charges", "amount": None,
                                          "currency": rate["value"].get("child_charge_currency"), "status": "unknown",
                                          "basis": rate["value"].get("child_charge_basis"), "fact_ids": [rate["fact_id"]]})
                    elif child_count and rate["value"].get("child_charge_status") != "included":
                        amount = rate["value"].get("child_charge_amount")
                        basis = rate["value"].get("child_charge_basis")
                        if (isinstance(amount, int) and basis == "per child per room night" and nights
                                and rate["value"].get("child_charge_currency") == rate["value"].get("currency")):
                            charge = amount * child_count * nights
                            additional_total += charge
                            breakdown.append({"label": "child charges", "amount": charge,
                                              "currency": rate["value"].get("child_charge_currency"), "status": "known",
                                              "basis": f"{child_count} child(ren) × {nights} night(s)",
                                              "fact_ids": [rate["fact_id"]]})
                        else:
                            complete = False
                            breakdown.append({"label": "child charges", "amount": None,
                                              "currency": rate["value"].get("child_charge_currency"), "status": "unknown",
                                              "basis": basis, "fact_ids": [rate["fact_id"]]})
                    included_adults = int((rate["value"].get("price_basis") or {}).get("included_adults", 0))
                    extra_adult_count = max(0, room_priced_adult_count - included_adults)
                    if extra_adult_count and rate["value"].get("extra_adult_charge_status") not in {"included", "confirmed"}:
                        complete = False
                        breakdown.append({"label": "extra adult charges", "amount": None,
                                          "currency": rate["value"].get("extra_adult_charge_currency"), "status": "unknown",
                                          "basis": rate["value"].get("extra_adult_charge_basis"), "fact_ids": [rate["fact_id"]]})
                    elif extra_adult_count and rate["value"].get("extra_adult_charge_status") != "included":
                        amount = rate["value"].get("extra_adult_charge_amount")
                        basis = rate["value"].get("extra_adult_charge_basis")
                        if (isinstance(amount, int) and basis == "per adult per room night" and nights
                                and rate["value"].get("extra_adult_charge_currency") == rate["value"].get("currency")):
                            charge = amount * extra_adult_count * nights
                            additional_total += charge
                            breakdown.append({"label": "extra adult charges", "amount": charge,
                                              "currency": rate["value"].get("extra_adult_charge_currency"), "status": "known",
                                              "basis": f"{extra_adult_count} extra adult(s) × {nights} night(s)",
                                              "fact_ids": [rate["fact_id"]]})
                        else:
                            complete = False
                            breakdown.append({"label": "extra adult charges", "amount": None,
                                              "currency": rate["value"].get("extra_adult_charge_currency"), "status": "unknown",
                                              "basis": basis, "fact_ids": [rate["fact_id"]]})
                else:
                    complete = False
                    breakdown.append({"label": "room rate", "amount": None, "currency": None,
                                      "status": "unknown", "basis": "no active reference rate", "fact_ids": []})
                all_claim_ids.add(room_records[index]["fact_id"])
            if complete and subtotal is not None:
                subtotal += additional_total
            if unpriced_bedding:
                complete = False
            if not complete:
                checks.append({"code": "cost_completeness", "status": "unknown",
                               "fact_ids": [rate["fact_id"] for rate in rates_by_room.values() if rate]})
            if budget_strength_unknown:
                checks.append({"code": "budget_strength", "status": "unknown",
                               "fact_ids": [rate["fact_id"] for rate in rates_by_room.values() if rate]})
            if rate_basis_unknown:
                checks.append({"code": "rate_basis", "status": "unknown",
                               "fact_ids": [rate["fact_id"] for rate in rates_by_room.values() if rate
                                            and (rate["value"].get("price_basis") or {}).get("unit") != "room_night"]})
                rate_question = {
                    "en": "Could you confirm whether this rate is per room per night?",
                    "vi": "Bạn xác nhận mức giá này tính theo phòng mỗi đêm được không?",
                    "zh": "请确认此价格是否按每间客房每晚计算。",
                }
                language = (context.locale or "en").split("-")[0].lower()
                questions.append({"field": "room_advice", "reason": rate_question.get(language, rate_question["en"]),
                                  "locale": language if language in rate_question else "en",
                                  "locale_fallback": language not in rate_question})
            if rate_window_unknown:
                checks.append({"code": "rate_validity_window", "status": "unknown",
                               "fact_ids": [rate["fact_id"] for rate in rates_by_room.values() if rate
                                            and _rate_covers_stay(rate, context.brief_data) is False]})
            if requirements.get("budget_strength") == "hard" and requirements.get("budget_amount") is not None:
                budget_currency = requirements.get("budget_currency")
                comparable = nightly_complete and len(currencies) == 1 and budget_currency in currencies
                if requirements.get("budget_basis", "stay_total") == "stay_total":
                    known_lower_bound = base_subtotal + additional_total if base_subtotal is not None else None
                    complete_basis_value = known_lower_bound if complete else None
                elif nightly_subtotal is not None:
                    if additional_total == 0:
                        known_lower_bound = nightly_subtotal
                    elif nights and additional_total % nights == 0:
                        known_lower_bound = nightly_subtotal + additional_total // nights
                    else:
                        known_lower_bound = None
                    complete_basis_value = known_lower_bound if complete and nights else None
                else:
                    known_lower_bound = None
                    complete_basis_value = None
                basis_value = known_lower_bound if comparable else None
                if basis_value is not None and basis_value > requirements["budget_amount"]:
                    invalid_reasons.append("hard_budget_exceeded")
                    rejected_alternatives.append({"option_id": candidate.option_id,
                                                  "reason": "hard_budget_exceeded",
                                                  "fact_ids": sorted({
                                                      *(room_records[index]["fact_id"] for index in room_indices),
                                                      *(rate["fact_id"] for rate in rates_by_room.values() if rate),
                                                  })})
                    continue
                if basis_value is None or complete_basis_value is None:
                    checks.append({"code": "budget", "status": "unknown", "fact_ids": [rate["fact_id"] for rate in rates_by_room.values() if rate]})
            unknown_codes = {check["code"] for check in checks if check["status"] == "unknown"}
            option_fact_ids = {room_records[index]["fact_id"] for index in room_indices}
            option_fact_ids.update(rate["fact_id"] for rate in rates_by_room.values() if rate)
            safe_rationale = []
            room_requirements = context.brief_data.get("room_requirements") or {}
            checks_by_code: dict[str, list[str]] = defaultdict(list)
            for check in checks:
                checks_by_code[check["code"]].append(check["status"])
            fit_codes = {
                "occupancy", "bed_configuration", "guardian_relationship", "child_age_policy",
                "bunk_position_policy", "bunk_position_capacity", "bed_sharing_consent",
                "separate_bed_requirement",
                "cot_policy", "extra_bed_policy", "accessibility",
            }
            fit_verified = all(
                status == "pass"
                for code, statuses in checks_by_code.items() if code in fit_codes
                for status in statuses
            )
            fit_verified = fit_verified and len(checks_by_code["occupancy"]) == len(room_indices)
            fit_verified = fit_verified and len(checks_by_code["bed_configuration"]) == len(room_indices)
            if room_requirements.get("hard_accessibility_needs"):
                fit_verified = fit_verified and len(checks_by_code["accessibility"]) == len(room_indices)
            tradeoff_present = any(
                check["status"] == "not_met" and check["code"] in {
                    "avoided_bed_type", "preferred_bed_type", "bed_sharing_preference",
                } for check in checks
            )
            charges_unknown = any(
                item.get("status") == "unknown" and any(token in item.get("label", "")
                                                         for token in ("child", "adult", "bedding", "cot"))
                for item in breakdown
            ) or unpriced_bedding
            for claim in candidate.rationale:
                cited = set(claim.fact_ids)
                if (not cited or not cited <= option_fact_ids
                        or any(fact_id not in source_facts for fact_id in cited)):
                    continue
                allowed = (
                    claim.claim_code == "party_fit" and fit_verified
                    or claim.claim_code == "bed_setup"
                    and len(checks_by_code["bed_configuration"]) == len(room_indices)
                    and all(status == "pass" for status in checks_by_code["bed_configuration"])
                    and all(status == "pass" for code in ("bed_sharing_consent", "bunk_position_policy",
                                                           "bunk_position_capacity")
                            for status in checks_by_code.get(code, []))
                    or claim.claim_code == "reference_price" and complete
                    or claim.claim_code == "policy_confirmation" and bool(unknown_codes)
                    or claim.claim_code == "accessibility_confirmation" and bool(room_requirements.get("hard_accessibility_needs"))
                    and "accessibility" in unknown_codes
                    or claim.claim_code == "preference_tradeoff" and tradeoff_present
                    or claim.claim_code == "charges_confirmation" and charges_unknown
                )
                if (not allowed or claim.claim_code == "reference_price" and (
                    not subtotal or len(currencies) != 1
                )):
                    continue
                text, rationale_locale, locale_fallback = _localized_rationale(
                    claim.claim_code, context.locale, subtotal=subtotal,
                    currency=next(iter(currencies)) if len(currencies) == 1 else None,
                    presentation_labels=presentation_labels,
                )
                safe_rationale.append({"claim_code": claim.claim_code, "text": text,
                                       "locale": rationale_locale,
                                       "locale_fallback": locale_fallback,
                                       "fact_ids": sorted(cited)})
                all_claim_ids.update(cited)
            options.append({
                "option_id": candidate.option_id,
                "rooms": [{"room_index": room.room_index, "room_type_id": room.room_type_id}
                          for room in candidate.rooms], "assignments": assignments,
                "checks": checks,
                "rationale": safe_rationale,
                "cost": {"currency": next(iter(currencies)) if len(currencies) == 1 else None,
                         "nightly_subtotal": sum(rate["value"]["amount"] for rate in rates_by_room.values())
                         if nightly_complete else None,
                         "total": subtotal if complete else None,
                         "status": "complete" if complete else "incomplete", "breakdown": breakdown},
            })
        unknown_checks = any(check["status"] == "unknown" for option in options for check in option["checks"])
        tradeoffs = sorted({check["code"] for option in options for check in option["checks"]
                            if check["status"] == "not_met"})
        if options:
            accepted_incomplete_cost = any(option["cost"]["status"] != "complete" for option in options)
            status = "partial" if unknown_checks or accepted_incomplete_cost or tradeoffs else "ready"
        elif invalid_reasons:
            status = "conflict" if any(reason in {
                "candidate_fails_hard_room_check", "hard_budget_exceeded", "hard_room_count_exceeded",
                "source_fact_conflict",
            } for reason in invalid_reasons) else "unsupported"
        else:
            status = "needs_clarification"
        if invalid_reasons and not options:
            questions.extend({"field": "room_advice", "reason": reason.replace("_", " ")}
                             for reason in dict.fromkeys(invalid_reasons))
        source_refs = tuple(_source(source_facts[fact_id], context.source_generation)
                            for fact_id in sorted(all_claim_ids) if fact_id in source_facts)
        result = RoomAdviceResult(
            status=status, brief_version=context.brief_version,
            source_generation=context.source_generation, source_refs=source_refs,
            options=tuple(options), questions=tuple(questions),
            explanation_inputs={
                "supported_fact_ids": sorted(all_claim_ids),
                "unknowns": sorted({check["code"] for option in options for check in option["checks"]
                                     if check["status"] == "unknown"}),
                "conflicts": sorted(set(invalid_reasons)) if not options else [],
                "rejected_alternatives": rejected_alternatives,
                "tradeoffs": tradeoffs,
                "availability": "unknown",
                "rationale_locale": context.locale or "en",
            },
            hotel_answer=draft.hotel_answer,
        )
        return relocalize_checked(result)


__all__ = ["HospitalityRoomAdvice"]
