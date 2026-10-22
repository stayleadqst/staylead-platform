"""Deployment-selected domain profile composition."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainProfile:
    name: str


class UnsupportedDomainError(ValueError):
    pass


def select_domain_profile(name: str) -> DomainProfile:
    """Select a compiled-in profile. Hospitality is scaffolded; others are unsupported."""
    if name == "hospitality":
        return DomainProfile(name="hospitality")
    raise UnsupportedDomainError(f"Domain profile {name!r} is not available in this skeleton.")
