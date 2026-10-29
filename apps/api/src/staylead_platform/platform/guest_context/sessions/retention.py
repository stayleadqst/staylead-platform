"""Hospitality guest session retention policy for the technical pilot."""

from datetime import UTC, datetime, timedelta

SESSION_CONTENT_MAX_AGE = timedelta(hours=24)
OPERATIONAL_METADATA_MAX_AGE = timedelta(days=7)
ADMISSION_RESERVATION_WINDOW = timedelta(seconds=600)
RETENTION_POLICY_VERSION = "pilot-retention-24h-ops7d-v1"


def session_expiry(created_at: datetime) -> datetime:
    """Return the UTC expiry boundary anchored to session creation."""
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    return created_at.astimezone(UTC) + SESSION_CONTENT_MAX_AGE


def cleanup_delay_seconds(
    *, now: datetime, next_expiry: datetime | None, maintenance_interval_seconds: int,
) -> float:
    """Sleep until the nearest expiry, bounded by a routine maintenance interval."""
    if now.tzinfo is None or (next_expiry is not None and next_expiry.tzinfo is None):
        raise ValueError("cleanup timestamps must be timezone-aware")
    interval = max(1, int(maintenance_interval_seconds))
    if next_expiry is None:
        return float(interval)
    remaining = (next_expiry.astimezone(UTC) - now.astimezone(UTC)).total_seconds()
    return max(0.0, min(float(interval), remaining))
