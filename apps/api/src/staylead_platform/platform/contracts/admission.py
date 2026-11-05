"""Provider-neutral guest admission limits shared across composition and storage."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GuestAdmissionLimits:
    turns_per_session: int = 12
    turns_per_hotel: int = 120
    window_seconds: int = 600
    in_flight_per_session: int = 1
    in_flight_per_hotel: int = 4
    provider_calls_per_request: int = 2
    lease_seconds: int = 45
