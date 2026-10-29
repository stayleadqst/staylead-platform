"""Composition for protected development-only local-guide operations."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.engine import Engine

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.domains.hospitality.registration.local_guide import HospitalityLocalGuide
from staylead_platform.domains.hospitality.registration.local_guide_pack import HOTEL_ID
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.knowledge_repository import (
    PostgresKnowledgeFactRepository,
)
from staylead_platform.infrastructure.persistence.local_guide_repository import (
    PostgresLocalGuideRepository,
)
from staylead_platform.infrastructure.persistence.store import (
    IdempotencyConflict,
    ScopeError,
    VersionConflict,
)
from staylead_platform.infrastructure.source_connectors.local_guide import (
    activate_local_guide_source,
    import_local_guide_pack,
    refresh_local_guide_source,
    transition_local_guide_source,
)


class OperatorGuideError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[6]


class OperatorGuideApplication:
    """Transport-neutral adapter; property scope is supplied by authenticated server identity."""

    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        self._engine = engine or create_database_engine(settings.database_url)
        root = _workspace_root()
        self._pack_root = root / "fixtures" / "hospitality" / "sprint8-local-guide-v1"
        self._allowed_root = root / "fixtures" / "hospitality"
        self._operator_repository = PostgresLocalGuideRepository(self._engine)
        self._facts = PostgresKnowledgeFactRepository(self._engine)
        self._guide = HospitalityLocalGuide(
            self._facts,
            lambda hotel_id, now, _timeout: self._operator_repository.active_snapshot(hotel_id, now=now),
            self._operator_repository,
        )

    @staticmethod
    def _check_scope(hotel_id: str) -> None:
        if hotel_id != HOTEL_ID:
            raise OperatorGuideError(403, "operator_property_forbidden", "The operator is not authorized for this property.")

    def _call(self, callback: Any) -> Any:
        try:
            return callback()
        except OperatorGuideError:
            raise
        except (VersionConflict, IdempotencyConflict) as exc:
            raise OperatorGuideError(409, "guide_version_conflict", "The guide changed; refresh the preview and try again.") from exc
        except ScopeError as exc:
            raise OperatorGuideError(404, "guide_source_unavailable", "The requested guide source is unavailable.") from exc
        except ValueError as exc:
            raise OperatorGuideError(422, "invalid_guide_pack", "The local-guide source could not be validated.") from exc
        except Exception as exc:
            raise OperatorGuideError(503, "guide_storage_unavailable", "The local guide is temporarily unavailable.", retryable=True) from exc

    def preview(self, hotel_id: str) -> dict[str, Any]:
        self._check_scope(hotel_id)
        return self._call(lambda: asdict(self._guide.preview(hotel_id)))

    def import_pack(self, hotel_id: str) -> dict[str, Any]:
        self._check_scope(hotel_id)

        def run() -> dict[str, Any]:
            result = import_local_guide_pack(self._engine, self._pack_root, allowed_root=self._allowed_root)
            preview = asdict(self._guide.preview(hotel_id))
            result["sources"] = [ref for ref in preview["source_refs"] if str(ref.get("source_id", "")).startswith("S8-GUIDE-")]
            result["preview"] = preview
            return result

        return self._call(run)

    def activate(self, hotel_id: str, **values: Any) -> dict[str, Any]:
        self._check_scope(hotel_id)
        return self._call(lambda: activate_local_guide_source(
            self._engine, self._pack_root, allowed_root=self._allowed_root, hotel_id=hotel_id, **values,
        ))

    def refresh(self, hotel_id: str, **values: Any) -> dict[str, Any]:
        self._check_scope(hotel_id)
        return self._call(lambda: refresh_local_guide_source(
            self._engine, allowed_root=self._allowed_root, hotel_id=hotel_id, **values,
        ))

    def transition(
        self, hotel_id: str, *, action: Literal["delete", "revoke"], **values: Any,
    ) -> dict[str, Any]:
        self._check_scope(hotel_id)
        return self._call(lambda: transition_local_guide_source(
            self._engine, hotel_id=hotel_id, action=action, **values,
        ))


def create_operator_guide_application(
    settings: Settings, *, engine: Engine | None = None,
) -> OperatorGuideApplication | None:
    if settings.environment.lower() not in {"development", "test"} or not settings.dev_operator_credentials:
        return None
    return OperatorGuideApplication(settings, engine=engine)
