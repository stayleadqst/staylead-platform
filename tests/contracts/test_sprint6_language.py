import pytest
from staylead_platform.platform.contracts.language import (
    language_direction,
    normalize_language_tag,
)
from staylead_platform.platform.conversation.orchestrator.grounded_qa import (
    ConversationFailure,
    _numeric_forms,
    _validate_supported_literals,
)
from staylead_platform.platform.conversation.responses.presentation_labels import (
    ENGLISH_LABELS,
    LABEL_KEYS,
    label_source_texts,
    missing_label_keys,
    resolve_label_bundle,
)


def test_open_language_tags_are_normalized_and_direction_is_script_aware() -> None:
    assert normalize_language_tag("ZH-hant-tw") == "zh-Hant-TW"
    assert normalize_language_tag("ar") == "ar"
    assert normalize_language_tag("English") == "english"
    assert normalize_language_tag("not a language") is None
    assert language_direction("ar") == "rtl"
    assert language_direction("zh-Hant") == "ltr"
    assert language_direction("az-Arab") == "rtl"
    assert language_direction("en-Hebr") == "rtl"
    assert language_direction("ar-Latn") == "ltr"


def test_unicode_decimal_digits_match_without_punctuation_collisions() -> None:
    assert _numeric_forms("15.50") == _numeric_forms("١٥.٥٠")
    assert _numeric_forms("15.50") != _numeric_forms("1550")
    assert _numeric_forms("1,250") != _numeric_forms("1250")


def test_guard_preserves_ordered_date_time_literals_and_accepts_range_endpoints() -> None:
    breakfast = [{"value": "Breakfast from 06:30-09:30."}]
    _validate_supported_literals("Breakfast runs from 06:30 until 09:30.", breakfast)
    _validate_supported_literals("يبدأ الإفطار من ٠٦:٣٠ حتى ٠٩:٣٠.", breakfast)
    with pytest.raises(ConversationFailure, match="unsupported number"):
        _validate_supported_literals("Breakfast starts at 30:06.", [{"value": "Breakfast starts at 06:30."}])

    date = [{"value": "Check-in date: 2026-12-10."}]
    with pytest.raises(ConversationFailure, match="unsupported number"):
        _validate_supported_literals("Check-in date: 2026-10-12.", date)
    for source, answer in (
        ("10/12/2026", "12/10/2026"),
        ("10-12-2026", "12-10-2026"),
    ):
        _validate_supported_literals(f"Date: {source}.", [{"value": f"Date: {source}."}])
        with pytest.raises(ConversationFailure, match="unsupported number"):
            _validate_supported_literals(f"Date: {answer}.", [{"value": f"Date: {source}."}])
    with pytest.raises(ConversationFailure, match="unsupported number"):
        _validate_supported_literals("The amount is 15.51.", [{"value": "The amount is 15.50."}])


def test_label_bundle_cache_is_atomic_and_invalid_values_fall_back() -> None:
    translated = {key: f"翻译{key}" for key in LABEL_KEYS}
    assert resolve_label_bundle("zh", translated) == translated
    invalid = {key: f"ar-{key}" for key in LABEL_KEYS}
    invalid["copy"] = "<b>copy</b>"
    assert resolve_label_bundle("ar", invalid) == ENGLISH_LABELS
    assert resolve_label_bundle("ar", {"copy": "نسخ"}) == ENGLISH_LABELS


def test_english_labels_always_use_the_approved_source_text() -> None:
    proposed = {key: f"paraphrased {key}" for key in LABEL_KEYS}
    for language_tag in ("en", "en-US"):
        assert missing_label_keys(language_tag) == []
        assert resolve_label_bundle(language_tag, proposed) == ENGLISH_LABELS


def test_label_source_texts_projects_only_requested_known_labels() -> None:
    assert label_source_texts(("synthetic_notice", "copy", "not_a_label", 7)) == {
        "copy": ENGLISH_LABELS["copy"],
        "synthetic_notice": ENGLISH_LABELS["synthetic_notice"],
    }
