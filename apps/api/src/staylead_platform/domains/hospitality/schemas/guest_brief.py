"""Hospitality-owned guest travel brief schema and semantic validation."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
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


class GuestPatchAuthorization(BaseModel):
    """Same-turn provenance asserted for one proposed operation."""

    model_config = ConfigDict(extra="forbid")
    operation_index: int = Field(ge=0, le=11)
    op: Literal["set_dates", "set_adults", "add_child", "set_child_age", "remove_child", "clarify"]
    target_fields: list[str] = Field(min_length=1, max_length=2)
    intent: Literal["explicit_request", "clarification"]
    current_turn_quote: str = Field(min_length=1, max_length=500)


GuestTurnIntent = Literal["hotel_information", "guest_state", "guest_edit", "courtesy"]


def validate_guest_patch_authorization(
    operations: tuple[dict[str, Any], ...], authorizations: Any, question: str,
) -> None:
    """Require one target-matched, current-utterance quote for every mutation."""
    if not operations:
        if authorizations:
            raise ValueError("Patch authorizations require proposed operations.")
        return
    try:
        records = [GuestPatchAuthorization.model_validate(item) for item in authorizations]
    except (TypeError, ValidationError) as exc:
        raise ValueError("Every guest edit requires valid current-turn authorization.") from exc
    if len(records) != len(operations):
        raise ValueError("Every guest edit requires exactly one current-turn authorization.")
    for index, (operation, record) in enumerate(zip(operations, records, strict=True)):
        op = operation.get("op")
        expected_targets = _patch_target_fields(operation)
        expected_intent = "clarification" if op == "clarify" else "explicit_request"
        if (
            record.operation_index != index or record.op != op
            or record.target_fields != expected_targets or record.intent != expected_intent
            or not record.current_turn_quote.strip()
            or record.current_turn_quote not in question
        ):
            raise ValueError("Guest edit authorization does not match the current turn operation.")


def validate_preparation_metadata(
    payload: Any, patch: GuestBriefProposal | None, question: str,
) -> tuple[tuple[str, ...], tuple[dict[str, Any], ...]]:
    intents = tuple(dict.fromkeys(getattr(payload, "turn_intents", ())))
    valid_intents = {"hotel_information", "guest_state", "guest_edit", "courtesy"}
    if not intents or any(intent not in valid_intents for intent in intents):
        raise ValueError("Preparation must classify at least one current-turn intent.")
    authorizations = tuple(
        item.model_dump(mode="json") for item in getattr(payload, "guest_patch_authorizations", ())
    )
    operations = patch.operations if patch is not None else ()
    try:
        validate_guest_patch_authorization(operations, authorizations, question)
    except ValueError as exc:
        raise ValueError("The proposed guest edit lacks current-turn authorization.") from exc
    if operations and "guest_edit" not in intents:
        raise ValueError("Guest edits require the current turn to be classified as an edit.")
    return intents, authorizations


def validate_committed_turn_channels(
    payload: Any, intents: tuple[str, ...], pending_fields: tuple[str, ...], authorized_targets: tuple[str, ...],
) -> None:
    """Enforce prepared turn scope even when a provider ignores native JSON schema hints."""
    valid_intents = {"hotel_information", "guest_state", "guest_edit", "courtesy"}
    if not intents or any(intent not in valid_intents for intent in intents):
        raise ValueError("The committed answer has no persisted current-turn intent.")
    acknowledgement = getattr(payload, "conversational_acknowledgement", None)
    if acknowledgement is not None and "courtesy" not in intents:
        raise ValueError("A courtesy acknowledgement is outside the prepared current-turn intent.")
    required_clarifications = required_pending_clarification_fields(pending_fields, authorized_targets)
    clarification = getattr(payload, "guest_clarification", None)
    if required_clarifications and (
        clarification is None or clarification.field not in required_clarifications
    ):
        raise ValueError("The committed answer omitted a required authorized pending-field question.")
    if any(field.endswith(".age") for field in pending_fields) and not getattr(payload, "unknowns", ()):
        raise ValueError("A pending child age requires a direct age question.")
    if "hotel_information" in intents:
        return
    if getattr(payload, "supported_claims", ()) or getattr(payload, "conflicts", ()):
        raise ValueError("Hotel information channels are outside the prepared current-turn scope.")
    unknowns = getattr(payload, "unknowns", ())
    pending_can_be_asked = any(
        field == "dates.check_out" or field.endswith(".age") for field in pending_fields
    )
    missing_guest_state = (
        "guest_state" in intents and not authorized_targets and not pending_fields
    )
    if unknowns and (
        len(unknowns) != 1 or not pending_can_be_asked and not missing_guest_state
        or any(not item.strip() for item in unknowns)
    ):
        raise ValueError("Only one pending guest detail may be clarified outside a hotel-information turn.")


def required_pending_clarification_fields(
    pending_fields: tuple[str, ...], authorized_targets: tuple[str, ...],
) -> tuple[str, ...]:
    fields = [
        field for field in pending_fields
        if field in authorized_targets and not field.endswith(".age")
    ]
    if any(field in authorized_targets for field in ("dates.check_in", "dates.check_out")):
        fields.extend(
            field for field in ("dates.check_in", "dates.check_out")
            if field in pending_fields and field not in fields
        )
    return tuple(dict.fromkeys(fields))


def _patch_target_fields(operation: dict[str, Any]) -> list[str]:
    op = operation.get("op")
    if op == "set_dates":
        return [f"dates.{name}" for name in ("check_in", "check_out") if operation.get(name) is not None]
    if op == "set_adults":
        return ["party.adults"]
    if op == "add_child":
        return ["party.children"]
    if op == "set_child_age":
        return [f"party.children.{operation.get('member_id')}.age"]
    if op == "remove_child":
        return [f"party.children.{operation.get('member_id')}"]
    if op == "clarify" and isinstance(operation.get("field"), str):
        return [operation["field"]]
    return []


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
