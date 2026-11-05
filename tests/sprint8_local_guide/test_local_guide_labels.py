from __future__ import annotations

from staylead_platform.domains.hospitality.registration.local_guide_labels import (
    LOCAL_GUIDE_LABEL_KEYS,
    resolve_local_guide_label_bundle,
)


def test_complete_safe_bundle_is_accepted_as_a_unit() -> None:
    proposed = {key: f"Traduit {key}" for key in LOCAL_GUIDE_LABEL_KEYS}
    assert resolve_local_guide_label_bundle("fr-CA", proposed) == proposed


def test_invalid_partial_or_unsafe_bundle_uses_reviewed_french_and_arabic_labels() -> None:
    for locale in ("fr", "ar"):
        labels = resolve_local_guide_label_bundle(locale, {"local_guide_title": "<script>"})
        assert set(labels) == set(LOCAL_GUIDE_LABEL_KEYS)
        assert "<script>" not in labels.values()
        assert labels["local_guide_title"] != "Local suggestions"


def test_label_bundle_cannot_smuggle_numeric_or_price_claims() -> None:
    unsafe = {key: f"Label {key}" for key in LOCAL_GUIDE_LABEL_KEYS}
    unsafe["local_guide_title"] = "100% allergen safe"
    resolved = resolve_local_guide_label_bundle("fr", unsafe)
    assert resolved["local_guide_title"] == "Suggestions locales"


def test_english_bundle_is_fixed_and_unknown_languages_have_safe_english_fallback() -> None:
    assert resolve_local_guide_label_bundle("en", None)["local_guide_title"] == "Local suggestions"
    assert resolve_local_guide_label_bundle("zz", None)["local_guide_title"] == "Local suggestions"
    proposed = {key: f"Etiqueta {key}" for key in LOCAL_GUIDE_LABEL_KEYS}
    assert resolve_local_guide_label_bundle("zz", proposed) == proposed
