from staylead_platform.domains.hospitality.registration.local_guide_labels import (
    LOCAL_GUIDE_LABEL_KEYS,
    local_guide_label_source_texts,
    local_guide_source_status_label,
    local_guide_unknown_label,
    resolve_local_guide_label_bundle,
)


def test_local_guide_bundle_has_reviewed_french_and_arabic_copy() -> None:
    french = resolve_local_guide_label_bundle("fr-FR", {})
    arabic = resolve_local_guide_label_bundle("ar", {})

    assert set(french) == set(LOCAL_GUIDE_LABEL_KEYS)
    assert french["local_guide_per_person"] == "par personne"
    assert arabic["local_guide_per_person"] == "للشخص الواحد"
    assert all(len(value) <= 80 for value in (*french.values(), *arabic.values()))


def test_unknown_locale_uses_validated_model_bundle_and_specific_unknowns() -> None:
    proposed = {**local_guide_label_source_texts(), "local_guide_verify": "Confirmez ce point avec le lieu."}
    translated = {key: f"Phrase locale {index}" for index, key in enumerate(LOCAL_GUIDE_LABEL_KEYS)}
    translated["local_guide_verify"] = "Confirmez ce point avec le lieu."

    assert local_guide_unknown_label("allergy_unconfirmed", "fr-CA", proposed).startswith("Confirmez les ingrédients")
    assert local_guide_unknown_label("accessibility_unconfirmed", "zz-ZZ", translated) == translated["local_guide_verify"]
    assert local_guide_unknown_label("not-a-policy-code", "fr", translated) == translated["local_guide_verify"]
    assert local_guide_unknown_label("allergy_unconfirmed", "zz-ZZ", {"local_guide_verify": "http://unsafe"}) != "http://unsafe"


def test_source_lifecycle_status_is_localized_without_inventing_unknown_states() -> None:
    assert local_guide_source_status_label("approved", "fr-FR") == "Approuvé"
    assert local_guide_source_status_label("revoked", "ar") == "ملغى"
    assert local_guide_source_status_label("future_state", "fr") == "future_state"
