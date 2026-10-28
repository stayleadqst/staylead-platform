from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.dependencies.guest_chat import _booking_channel


def test_default_booking_channels_are_trusted_labeled_demo_links() -> None:
    channel = _booking_channel(Settings(), "harbor-city-demo")

    assert channel["destination_url"] == "https://booking.example/hotels/harbor-city-demo"
    assert channel["destination_kind"] == "synthetic_demo"


def test_booking_destination_rejects_unsafe_or_parameterized_config() -> None:
    for url in (
        "http://booking.example/hotel",
        "https://user:pass@booking.example/hotel",
        "https://booking.example/hotel?guest=guest@example.test",
        "https://booking.example/hotel#transcript",
        "javascript:alert(1)",
    ):
        settings = Settings(booking_destination_by_hotel={"hotel": url})
        assert _booking_channel(settings, "hotel")["destination_url"] is None


def test_missing_booking_destination_uses_only_configured_contact() -> None:
    settings = Settings(booking_destination_by_hotel={}, booking_contact_by_hotel={"hotel": "+1 555 0100"})

    channel = _booking_channel(settings, "hotel")

    assert channel["destination_url"] is None
    assert channel["contact"] == "+1 555 0100"
    assert channel["destination_kind"] == "configured"
