from staylead_platform.platform.contracts.language import (
    language_direction,
    normalize_language_tag,
)
from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
    _numeric_forms,
)
from staylead_platform.platform.conversation.responses.presentation_labels import (
    ENGLISH_LABELS,
    LABEL_KEYS,
    resolve_label_bundle,
)


def test_open_language_tags_are_normalized_and_direction_is_script_aware() -> None:
    assert normalize_language_tag("ZH-hant-tw") == "zh-Hant-TW"
    assert normalize_language_tag("ar") == "ar"
    assert normalize_language_tag("English") == "english"
    assert normalize_language_tag("not a language") is None
    assert language_direction("ar") == "rtl"
    assert language_direction("zh-Hant") == "ltr"


def test_unicode_decimal_digits_match_without_punctuation_collisions() -> None:
    assert _numeric_forms("15.50") == _numeric_forms("١٥.٥٠")
    assert _numeric_forms("15.50") != _numeric_forms("1550")
    assert _numeric_forms("1,250") != _numeric_forms("1250")


def test_label_bundle_cache_is_atomic_and_invalid_values_fall_back() -> None:
    translated = {key: f"翻译{key}" for key in LABEL_KEYS}
    assert resolve_label_bundle("zh", translated) == translated
    invalid = {key: f"ar-{key}" for key in LABEL_KEYS}
    invalid["copy"] = "<b>copy</b>"
    assert resolve_label_bundle("ar", invalid) == ENGLISH_LABELS
    assert resolve_label_bundle("ar", {"copy": "نسخ"}) == ENGLISH_LABELS
