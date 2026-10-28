"""Protected development-only operator HTTP routes."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.composition.dependencies.operator_guide import OperatorGuideError
from staylead_platform.infrastructure.identity.operator import (
    OperatorPrincipal,
    resolve_dev_operator,
)


class SourceOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_generation: int = Field(ge=0)
    expected_version: str = Field(min_length=1, max_length=120)
    expected_source_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    revision: Literal["primary-price-110000", "secondary-hours-confirmed"] | None = None


class OperatorGuideService(Protocol):
    def import_pack(self, hotel_id: str) -> Any: ...
    def preview(self, hotel_id: str) -> Any: ...
    def activate(self, hotel_id: str, **values: Any) -> Any: ...
    def refresh(self, hotel_id: str, **values: Any) -> Any: ...
    def transition(self, hotel_id: str, *, action: Literal["delete", "revoke"], **values: Any) -> Any: ...


def _payload(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _principal(
    request: Request, authorization: str | None, property_id: str, permission: str,
) -> OperatorPrincipal:
    settings: Settings = request.app.state.settings
    if settings.environment.lower() not in {"development", "test"}:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "operator_unavailable", "message": "The operator interface is unavailable.", "retryable": False},
        })
    if not authorization or not authorization.startswith("Bearer ") or not authorization[7:]:
        raise HTTPException(status_code=401, detail={
            "error": {"code": "operator_auth_required", "message": "A valid operator credential is required.", "retryable": False},
        })
    principal = resolve_dev_operator(authorization[7:], settings.dev_operator_credentials)
    if principal is None:
        raise HTTPException(status_code=401, detail={
            "error": {"code": "invalid_operator_credential", "message": "A valid operator credential is required.", "retryable": False},
        })
    if principal.property_id != property_id:
        raise HTTPException(status_code=403, detail={
            "error": {"code": "operator_property_forbidden", "message": "The operator is not authorized for this property.", "retryable": False},
        })
    if permission not in principal.permissions:
        raise HTTPException(status_code=403, detail={
            "error": {"code": "operator_permission_required", "message": "The operator is not authorized for this action.", "retryable": False},
        })
    return principal


def _service(request: Request) -> OperatorGuideService:
    service = request.app.state.operator_guide
    if service is None:
        raise HTTPException(status_code=503, detail={
            "error": {"code": "operator_unavailable", "message": "The operator service is unavailable.", "retryable": True},
        })
    return service


def _call(callback: Any) -> Any:
    try:
        return _payload(callback())
    except OperatorGuideError as exc:
        raise HTTPException(status_code=exc.status, detail={
            "error": {"code": exc.code, "message": str(exc), "retryable": exc.retryable},
        }) from exc


router = APIRouter(prefix="/v1/operator/properties/{property_id}/guide", tags=["local guide operator"])


@router.get("/preview")
def preview_guide(
    request: Request, property_id: str, authorization: str | None = Header(default=None),
) -> Any:
    _principal(request, authorization, property_id, "guide:read")
    return _call(lambda: _service(request).preview(property_id))


@router.post("/import")
def import_guide(
    request: Request, property_id: str, authorization: str | None = Header(default=None),
) -> Any:
    _principal(request, authorization, property_id, "guide:write")
    return _call(lambda: _service(request).import_pack(property_id))


@router.post("/activate")
def activate_guide(
    request: Request, property_id: str, body: SourceOperationRequest,
    authorization: str | None = Header(default=None),
) -> Any:
    _principal(request, authorization, property_id, "guide:write")
    return _call(lambda: _service(request).activate(property_id, **body.model_dump(exclude_none=True)))


@router.post("/refresh")
def refresh_guide(
    request: Request, property_id: str, body: SourceOperationRequest,
    authorization: str | None = Header(default=None),
) -> Any:
    _principal(request, authorization, property_id, "guide:write")
    values = body.model_dump(exclude_none=True)
    if "revision" not in values:
        raise HTTPException(status_code=422, detail={
            "error": {"code": "refresh_revision_required", "message": "Choose an approved synthetic refresh revision.", "retryable": False},
        })
    return _call(lambda: _service(request).refresh(property_id, **values))


def _transition(
    request: Request, property_id: str, body: SourceOperationRequest,
    action: Literal["delete", "revoke"], authorization: str | None,
) -> Any:
    _principal(request, authorization, property_id, "guide:write")
    return _call(lambda: _service(request).transition(property_id, action=action, **body.model_dump(exclude_none=True)))


@router.post("/delete")
def delete_guide_source(
    request: Request, property_id: str, body: SourceOperationRequest,
    authorization: str | None = Header(default=None),
) -> Any:
    return _transition(request, property_id, body, "delete", authorization)


@router.post("/revoke")
def revoke_guide_source(
    request: Request, property_id: str, body: SourceOperationRequest,
    authorization: str | None = Header(default=None),
) -> Any:
    return _transition(request, property_id, body, "revoke", authorization)
