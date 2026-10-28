from staylead_platform.composition.dependencies import guest_chat
from staylead_platform.domains.hospitality.registration.local_guide_labels import (
    LOCAL_GUIDE_LABEL_KEYS,
    has_reviewed_local_guide_labels,
    local_guide_label_source_texts,
)
from staylead_platform.platform.conversation.responses.presentation_labels import (
    LABEL_KEYS,
    label_source_texts,
)


def test_reviewed_local_guide_languages_use_the_existing_core_label_budget(monkeypatch) -> None:
    monkeypatch.setattr(guest_chat, "missing_label_keys", lambda _locale: list(LABEL_KEYS))

    for locale in ("en", "fr", "ar", "vi", "zh", "ja"):
        assert has_reviewed_local_guide_labels(locale)
        missing, bundle_keys, sources = guest_chat._answer_label_request(locale, ("local_guide",))
        assert missing == LABEL_KEYS
        assert bundle_keys == LABEL_KEYS
        assert sources == label_source_texts(LABEL_KEYS)
        assert not set(sources).intersection(LOCAL_GUIDE_LABEL_KEYS)


def test_unreviewed_local_guide_locale_keeps_its_dynamic_domain_bundle() -> None:
    assert not has_reviewed_local_guide_labels("zz-ZZ")

    missing, bundle_keys, sources = guest_chat._answer_label_request("zz-ZZ", ("local_guide",))

    assert missing == LOCAL_GUIDE_LABEL_KEYS
    assert bundle_keys == LOCAL_GUIDE_LABEL_KEYS
    assert sources == local_guide_label_source_texts()


def test_nonlocal_room_and_faq_label_request_does_not_change(monkeypatch) -> None:
    monkeypatch.setattr(guest_chat, "missing_label_keys", lambda _locale: list(LABEL_KEYS))

    expected = (LABEL_KEYS, LABEL_KEYS, label_source_texts(LABEL_KEYS))
    assert guest_chat._answer_label_request("zh", ("room_advice",)) == expected
    assert guest_chat._answer_label_request("fr", ("hotel_information",)) == expected
