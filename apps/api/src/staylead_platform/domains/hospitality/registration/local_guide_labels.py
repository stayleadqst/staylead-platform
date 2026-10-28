"""Small Hospitality-owned labels for local-guide results."""

from __future__ import annotations

import re
import unicodedata

LOCAL_GUIDE_LABELS_EN: dict[str, str] = {
    "local_guide_title": "Local suggestions",
    "local_guide_sources": "Source records",
    "local_guide_sponsored": "Sponsored",
    "local_guide_unknown": "Needs confirmation",
    "local_guide_fit": "Why it may fit",
    "local_guide_duration": "Visit duration",
    "local_guide_hours": "Hours status",
    "local_guide_conflicts": "Source conflicts",
    "local_guide_synthetic": "Synthetic technical-pilot information.",
    "local_guide_fit_status": "Possible fit",
    "local_guide_unknown_status": "Unverified for a required need",
    "local_guide_interest_quiet": "Quiet",
    "local_guide_interest_budget": "Budget",
    "local_guide_interest_culture": "Culture",
    "local_guide_interest_social": "Social",
    "local_guide_interest_nature": "Nature",
    "local_guide_interest_indoor": "Indoor",
    "local_guide_interest_history": "History",
    "local_guide_verify": "Confirm hard requirements and current details with the venue.",
    "local_guide_per_person": "per person",
}
LOCAL_GUIDE_LABEL_KEYS = tuple(LOCAL_GUIDE_LABELS_EN)
_URL = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_TRANSLATIONS = {
    "fr": {
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
    },
    "ar": {
        "local_guide_title": "اقتراحات محلية", "local_guide_sources": "سجلات المصادر",
        "local_guide_sponsored": "برعاية", "local_guide_unknown": "بحاجة إلى تأكيد",
        "local_guide_fit": "سبب ملاءمة الاقتراح", "local_guide_duration": "مدة الزيارة",
        "local_guide_hours": "حالة ساعات العمل", "local_guide_conflicts": "تعارض المصادر",
        "local_guide_synthetic": "معلومات اصطناعية للتجربة التقنية.",
        "local_guide_fit_status": "قد يكون مناسباً", "local_guide_unknown_status": "لم يتم التحقق من متطلب أساسي",
        "local_guide_interest_quiet": "هادئ", "local_guide_interest_budget": "الميزانية",
        "local_guide_interest_culture": "الثقافة", "local_guide_interest_social": "اجتماعي",
        "local_guide_interest_nature": "الطبيعة", "local_guide_interest_indoor": "داخلي",
        "local_guide_interest_history": "التاريخ",
        "local_guide_verify": "يرجى تأكيد المتطلبات الأساسية والتفاصيل الحالية مع المكان.",
        "local_guide_per_person": "للشخص الواحد",
    },
    "vi": {
        "local_guide_title": "Gợi ý địa phương", "local_guide_sources": "Nguồn thông tin",
        "local_guide_sponsored": "Được tài trợ", "local_guide_unknown": "Cần xác nhận",
        "local_guide_fit": "Lý do phù hợp", "local_guide_duration": "Thời lượng tham quan",
        "local_guide_hours": "Trạng thái giờ mở cửa", "local_guide_conflicts": "Nguồn có thông tin khác nhau",
        "local_guide_synthetic": "Thông tin tổng hợp cho thử nghiệm kỹ thuật.",
        "local_guide_fit_status": "Có thể phù hợp", "local_guide_unknown_status": "Chưa xác minh nhu cầu bắt buộc",
        "local_guide_interest_quiet": "Yên tĩnh", "local_guide_interest_budget": "Ngân sách",
        "local_guide_interest_culture": "Văn hóa", "local_guide_interest_social": "Giao lưu",
        "local_guide_interest_nature": "Thiên nhiên", "local_guide_interest_indoor": "Trong nhà",
        "local_guide_interest_history": "Lịch sử", "local_guide_verify": "Hãy xác nhận nhu cầu quan trọng và thông tin hiện tại với địa điểm.",
        "local_guide_per_person": "mỗi người",
    },
    "zh": {
        "local_guide_title": "当地推荐", "local_guide_sources": "信息来源", "local_guide_sponsored": "赞助内容",
        "local_guide_unknown": "需要确认", "local_guide_fit": "推荐原因", "local_guide_duration": "游览时长",
        "local_guide_hours": "营业时间状态", "local_guide_conflicts": "来源信息冲突",
        "local_guide_synthetic": "技术试点的合成信息。", "local_guide_fit_status": "可能合适",
        "local_guide_unknown_status": "尚未核实强制需求", "local_guide_interest_quiet": "安静",
        "local_guide_interest_budget": "预算", "local_guide_interest_culture": "文化",
        "local_guide_interest_social": "社交", "local_guide_interest_nature": "自然",
        "local_guide_interest_indoor": "室内", "local_guide_interest_history": "历史",
        "local_guide_verify": "请向场所确认重要需求和当前信息。",
        "local_guide_per_person": "每人",
    },
    "ja": {
        "local_guide_title": "周辺のおすすめ", "local_guide_sources": "情報源", "local_guide_sponsored": "スポンサー情報",
        "local_guide_unknown": "要確認", "local_guide_fit": "おすすめの理由", "local_guide_duration": "所要時間",
        "local_guide_hours": "営業時間の状態", "local_guide_conflicts": "情報源の不一致",
        "local_guide_synthetic": "技術パイロット用の合成情報です。", "local_guide_fit_status": "候補として適合",
        "local_guide_unknown_status": "必須条件は未確認", "local_guide_interest_quiet": "静か",
        "local_guide_interest_budget": "予算", "local_guide_interest_culture": "文化",
        "local_guide_interest_social": "交流", "local_guide_interest_nature": "自然",
        "local_guide_interest_indoor": "屋内", "local_guide_interest_history": "歴史",
        "local_guide_verify": "重要な条件と最新情報を施設に確認してください。",
        "local_guide_per_person": "1人あたり",
    },
}

_UNKNOWN_CODE_LABELS = {
    "en": {
        "accessibility_unconfirmed": "Confirm the specific accessibility feature with the venue.",
        "allergy_unconfirmed": "Confirm ingredients and allergen cross-contact controls with the venue.",
        "child_safety_unconfirmed": "Confirm the relevant child-safety details with the venue.",
        "budget_unconfirmed": "Confirm the price, currency, and per-person basis with the venue.",
        "hours_unconfirmed": "Confirm current opening hours with the venue.",
        "conflict_unconfirmed": "Conflicting source values require confirmation.",
    },
    "fr": {
        "accessibility_unconfirmed": "Confirmez l'aménagement d'accessibilité précis auprès du lieu.",
        "allergy_unconfirmed": "Confirmez les ingrédients et les risques de contamination croisée auprès du lieu.",
        "child_safety_unconfirmed": "Confirmez les détails de sécurité pour les enfants auprès du lieu.",
        "budget_unconfirmed": "Confirmez le prix, la devise et le tarif par personne auprès du lieu.",
        "hours_unconfirmed": "Confirmez les horaires d'ouverture actuels auprès du lieu.",
        "conflict_unconfirmed": "Les valeurs des sources sont contradictoires et doivent être confirmées.",
    },
    "ar": {
        "accessibility_unconfirmed": "يرجى تأكيد ميزة سهولة الوصول المطلوبة مع المكان.",
        "allergy_unconfirmed": "يرجى تأكيد المكونات ومخاطر التلامس التحسسي مع المكان.",
        "child_safety_unconfirmed": "يرجى تأكيد تفاصيل سلامة الأطفال مع المكان.",
        "budget_unconfirmed": "يرجى تأكيد السعر والعملة وأساس السعر لكل شخص مع المكان.",
        "hours_unconfirmed": "يرجى تأكيد ساعات العمل الحالية مع المكان.",
        "conflict_unconfirmed": "تتعارض قيم المصادر ويجب تأكيدها.",
    },
    "vi": {
        "accessibility_unconfirmed": "Hãy xác nhận tính năng hỗ trợ tiếp cận cụ thể với địa điểm.",
        "allergy_unconfirmed": "Hãy xác nhận thành phần và nguy cơ nhiễm chéo dị nguyên với địa điểm.",
        "child_safety_unconfirmed": "Hãy xác nhận chi tiết an toàn cho trẻ em với địa điểm.",
        "budget_unconfirmed": "Hãy xác nhận giá, tiền tệ và cách tính theo người với địa điểm.",
        "hours_unconfirmed": "Hãy xác nhận giờ mở cửa hiện tại với địa điểm.",
        "conflict_unconfirmed": "Các giá trị nguồn đang mâu thuẫn và cần được xác nhận.",
    },
    "zh": {
        "accessibility_unconfirmed": "请向场所确认所需的具体无障碍设施。",
        "allergy_unconfirmed": "请向场所确认食材及过敏原交叉接触风险。",
        "child_safety_unconfirmed": "请向场所确认儿童安全相关详情。",
        "budget_unconfirmed": "请向场所确认价格、币种及每人计价方式。",
        "hours_unconfirmed": "请向场所确认当前营业时间。",
        "conflict_unconfirmed": "来源中的数值存在冲突，需要确认。",
    },
    "ja": {
        "accessibility_unconfirmed": "必要なバリアフリー設備を施設にご確認ください。",
        "allergy_unconfirmed": "食材とアレルゲンの交差接触リスクを施設にご確認ください。",
        "child_safety_unconfirmed": "子どもの安全に関する詳細を施設にご確認ください。",
        "budget_unconfirmed": "料金、通貨、1人あたりの料金基準を施設にご確認ください。",
        "hours_unconfirmed": "現在の営業時間を施設にご確認ください。",
        "conflict_unconfirmed": "情報源の値が異なるため、確認が必要です。",
    },
}


def local_guide_label_source_texts() -> dict[str, str]:
    """Return bounded English source labels for this one Hospitality capability."""
    return dict(LOCAL_GUIDE_LABELS_EN)


def resolve_local_guide_label_bundle(locale: str | None, proposed: object) -> dict[str, str]:
    """Resolve a complete safe bundle, falling back to reviewed localizations when available."""
    language = (locale or "en").split("-")[0].lower()
    fallback = _TRANSLATIONS.get(language, LOCAL_GUIDE_LABELS_EN)
    if language == "en":
        return dict(LOCAL_GUIDE_LABELS_EN)
    valid = isinstance(proposed, dict) and set(proposed) == set(LOCAL_GUIDE_LABEL_KEYS)
    if valid:
        valid = all(
            isinstance(value, str) and bool(value.strip()) and len(value) <= 80
            and not _URL.search(value)
            and not any(unicodedata.category(char).startswith("C") for char in value)
            and not any(char.isdecimal() for char in value)
            and not any(char in value for char in "<>{}")
            for value in proposed.values()
        )
    if valid:
        return {key: proposed[key].strip() for key in LOCAL_GUIDE_LABEL_KEYS}
    return dict(fallback)


def local_guide_unknown_label(code: str, locale: str | None, proposed: object) -> str:
    """Render one finite evidence-status code in the selected language.

    Known locale strings are reviewed domain copy. For another locale, use the
    validated model-provided generic verification label rather than exposing an
    English diagnostic or pretending a static translation exists.
    """
    language = (locale or "en").split("-", 1)[0].lower()
    labels = _UNKNOWN_CODE_LABELS.get(language)
    if labels is not None and code in labels:
        return labels[code]
    if isinstance(proposed, dict):
        value = proposed.get("local_guide_verify")
        if (isinstance(value, str) and value.strip() and len(value) <= 80
                and not _URL.search(value) and not any(char in value for char in "<>{}")
                and not any(unicodedata.category(char).startswith("C") for char in value)):
            return value.strip()
    return LOCAL_GUIDE_LABELS_EN["local_guide_verify"]


_SOURCE_STATUS_LABELS = {
    "en": {"approved": "Approved", "refresh_failed": "Refresh failed", "revoked": "Revoked", "deleted": "Deleted", "staged": "Staged", "expired": "Expired", "not_yet_valid": "Not yet valid"},
    "fr": {"approved": "Approuvé", "refresh_failed": "Échec de l'actualisation", "revoked": "Révoqué", "deleted": "Supprimé", "staged": "En attente", "expired": "Expiré", "not_yet_valid": "Pas encore valide"},
    "ar": {"approved": "معتمد", "refresh_failed": "فشل التحديث", "revoked": "ملغى", "deleted": "محذوف", "staged": "قيد الانتظار", "expired": "منتهي الصلاحية", "not_yet_valid": "غير صالح بعد"},
    "vi": {"approved": "Đã duyệt", "refresh_failed": "Làm mới thất bại", "revoked": "Đã thu hồi", "deleted": "Đã xóa", "staged": "Đang chờ", "expired": "Đã hết hạn", "not_yet_valid": "Chưa có hiệu lực"},
    "zh": {"approved": "已批准", "refresh_failed": "刷新失败", "revoked": "已撤销", "deleted": "已删除", "staged": "待处理", "expired": "已过期", "not_yet_valid": "尚未生效"},
    "ja": {"approved": "承認済み", "refresh_failed": "更新失敗", "revoked": "取り消し済み", "deleted": "削除済み", "staged": "保留中", "expired": "期限切れ", "not_yet_valid": "まだ有効ではありません"},
}


def local_guide_source_status_label(status: str, locale: str | None) -> str:
    """Translate the finite M1 lifecycle state, preserving unknown states verbatim."""
    language = (locale or "en").split("-", 1)[0].lower()
    return _SOURCE_STATUS_LABELS.get(language, {}).get(status, status)
