import pytest
from fastapi.testclient import TestClient
from staylead_platform.composition.startup.domain_profile import (
    UnsupportedDomainError,
    select_domain_profile,
)
from staylead_platform.entrypoints.app import create_app


def test_health_reports_selected_hospitality_profile() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "domain": "hospitality"}


def test_unsupported_domain_profile_is_rejected() -> None:
    with pytest.raises(UnsupportedDomainError):
        select_domain_profile("electrical_equipment")
