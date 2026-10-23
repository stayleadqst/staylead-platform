"""Hospitality-owned guest travel brief schema and semantic validation."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefProposal,
    GuestBriefSnapshot,
    ValidatedGuestBriefPatch,
)


class SetDates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set_dates"]
    check_in: str | None = None
    check_out: str | None = None


class SetAdults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set_adults"]
    count: int = Field(ge=1, le=30)


class AddChild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["add_child"]
    age: int | None = Field(default=None, ge=0, le=17)


class SetChildAge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set_child_age"]
    member_id: str
    age: int = Field(ge=0, le=17)


class RemoveChild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["remove_child"]
    member_id: str


class ClarifyField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["clarify"]
    field: str
    reason: str | None = Field(default=None, max_length=300)


GuestBriefOperation = Annotated[
    SetDates | SetAdults | AddChild | SetChildAge | RemoveChild | ClarifyField,
    Field(discriminator="op"),
]


class HospitalityGuestBriefPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ops: list[GuestBriefOperation] = Field(default_factory=list, max_length=12)


def _iso_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Dates must be explicit ISO calendar dates.") from exc
    if parsed.isoformat() != value:
        raise ValueError("Dates must use YYYY-MM-DD.")
    return parsed


def validate_guest_brief_proposal(
    current: GuestBriefSnapshot, proposal: GuestBriefProposal,
) -> ValidatedGuestBriefPatch:
    """Apply only explicit, well-formed guest facts and preserve all unrelated values."""
    try:
        patch = HospitalityGuestBriefPatch.model_validate({"ops": list(proposal.operations)})
    except ValidationError as exc:
        raise ValueError("The proposed guest brief edit is invalid.") from exc
    data = {
        "dates": dict(current.data.get("dates") or {}),
        "party": dict(current.data.get("party") or {}),
    }
    data["dates"].setdefault("check_in", None)
    data["dates"].setdefault("check_out", None)
    data["dates"].setdefault("nights", None)
    data["party"].setdefault("adults", None)
    data["party"]["children"] = [dict(child) for child in data["party"].get("children", [])]
    pending = set(current.pending_fields)
    fields: set[str] = set()
    delta: dict[str, object] = {"dates": {}, "party": {}}
    clarification = False
    changed = False
    for operation in patch.ops:
        if isinstance(operation, SetDates):
            old_in = _iso_date(data["dates"].get("check_in"))
            old_out = _iso_date(data["dates"].get("check_out"))
            candidates = {"check_in": old_in, "check_out": old_out}
            invalid: set[str] = set()
            unresolved_dates: set[str] = set()
            for name, value in (("check_in", operation.check_in), ("check_out", operation.check_out)):
                if value is None:
                    continue
                field = f"dates.{name}"
                fields.add(field)
                try:
                    candidates[name] = _iso_date(value)
                    pending.discard(field)
                except ValueError:
                    invalid.add(name)
                    unresolved_dates.add(name)
                    pending.add(field)
                    clarification = True

            check_in, check_out = candidates["check_in"], candidates["check_out"]
            if check_in is not None and check_out is not None and check_out <= check_in:
                # Reject only newly supplied conflicting endpoints; preserve any
                # previously confirmed endpoint and ask about the disputed field.
                disputed = []
                if operation.check_in is not None and check_in != old_in:
                    disputed.append("check_in")
                if operation.check_out is not None and check_out != old_out:
                    disputed.append("check_out")
                if not disputed:
                    disputed = [name for name, value in (
                        ("check_in", operation.check_in), ("check_out", operation.check_out),
                    ) if value is not None]
                for name in disputed:
                    candidates[name] = old_in if name == "check_in" else old_out
                    pending.add(f"dates.{name}")
                    unresolved_dates.add(name)
                clarification = True
                check_in, check_out = candidates["check_in"], candidates["check_out"]

            if invalid:
                clarification = True
            if check_in is None:
                pending.add("dates.check_in")
            if check_out is None:
                pending.add("dates.check_out")
            if (operation.check_in is not None and check_in is not None
                    and "check_in" not in unresolved_dates):
                pending.discard("dates.check_in")
            if (operation.check_out is not None and check_out is not None
                    and "check_out" not in unresolved_dates):
                pending.discard("dates.check_out")
            nights = (check_out - check_in).days if (
                check_in is not None and check_out is not None and check_out > check_in
            ) else None
            dates = {"check_in": check_in.isoformat() if check_in else None,
                     "check_out": check_out.isoformat() if check_out else None,
                     "nights": nights}
            date_delta = {key: value for key, value in dates.items()
                          if value != data["dates"].get(key)}
            if date_delta:
                data["dates"].update(date_delta)
                delta["dates"] = date_delta
                changed = True
            clarification = clarification or check_in is None or check_out is None
        elif isinstance(operation, SetAdults):
            fields.add("party.adults")
            pending.discard("party.adults")
            if data["party"].get("adults") != operation.count:
                data["party"]["adults"] = operation.count
                delta["party"]["adults"] = operation.count
                changed = True
        elif isinstance(operation, AddChild):
            member_id = str(uuid4())
            child = {"member_id": member_id, "age": operation.age}
            data["party"]["children"].append(child)
            fields.add(f"party.children.{member_id}")
            delta["party"].setdefault("children_added", []).append(child)
            if operation.age is None:
                pending.add(f"party.children.{member_id}.age")
                clarification = True
            pending.discard("party.children.member")
            changed = True
        elif isinstance(operation, SetChildAge):
            fields.add(f"party.children.{operation.member_id}.age")
            try:
                UUID(operation.member_id)
            except ValueError as exc:
                raise ValueError("A child edit must use a known stable member ID.") from exc
            child = next((item for item in data["party"]["children"]
                          if item.get("member_id") == operation.member_id), None)
            if child is None:
                raise ValueError("The referenced child is not in the current brief.")
            if child.get("age") != operation.age:
                child["age"] = operation.age
                delta["party"].setdefault("children_updated", []).append(dict(child))
                changed = True
            pending.discard(f"party.children.{operation.member_id}.age")
            pending.discard("party.children.member")
        elif isinstance(operation, RemoveChild):
            fields.add(f"party.children.{operation.member_id}")
            try:
                UUID(operation.member_id)
            except ValueError as exc:
                raise ValueError("A child edit must use a known stable member ID.") from exc
            matches = [item for item in data["party"]["children"]
                       if item.get("member_id") == operation.member_id]
            if not matches:
                raise ValueError("The referenced child is not in the current brief.")
            data["party"]["children"] = [item for item in data["party"]["children"]
                                           if item.get("member_id") != operation.member_id]
            delta["party"].setdefault("children_removed", []).extend(matches)
            pending.discard(f"party.children.{operation.member_id}.age")
            pending.discard("party.children.member")
            changed = True
        elif isinstance(operation, ClarifyField):
            child_age_field = operation.field.startswith("party.children.") and operation.field.endswith(".age")
            if child_age_field:
                try:
                    UUID(operation.field.split(".")[2])
                except ValueError as exc:
                    raise ValueError("Child clarification must use a stable member ID.") from exc
            if operation.field not in {"dates.check_in", "dates.check_out", "party.adults", "party.children.member"} and not child_age_field:
                raise ValueError("The clarification field is outside the guest brief.")
            fields.add(operation.field)
            pending.add(operation.field)
            clarification = True
    if not delta["dates"]:
        delta.pop("dates")
    if not delta["party"]:
        delta.pop("party")
    data_changed = data != current.data
    pending_changed = tuple(sorted(pending)) != current.pending_fields
    changed = changed or data_changed or pending_changed
    if data_changed and clarification:
        status = "partial_success"
    elif data_changed or (pending_changed and not clarification):
        status = "applied"
    elif clarification:
        status = "clarification"
    else:
        status = "no_change"
    return ValidatedGuestBriefPatch(data, tuple(sorted(pending)), delta, status,
                                    tuple(sorted(fields)))
