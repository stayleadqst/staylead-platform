"""Hospitality-owned guest travel brief schema and semantic validation."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from staylead_platform.platform.contracts.guest_brief import (
    GuestBriefProposal,
    GuestBriefSnapshot,
    ValidatedGuestBriefPatch,
)

CANONICAL_BED_TYPES = (
    "bunk", "cot", "crib", "double", "extra_bed", "king", "queen", "single", "sofa_bed", "twin",
)
CanonicalBedType = Literal[
    "bunk", "cot", "crib", "double", "extra_bed", "king", "queen", "single", "sofa_bed", "twin",
]
HARD_BED_TYPES_DESCRIPTION = (
    "Exact canonical physical bed types only. A request for separate sleeping surfaces is an arrangement, "
    "not a bed type; do not infer single or twin from it."
)


class _PatchOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_turn_quote: str | None = Field(default=None, min_length=1, max_length=500, exclude=True)


class SetDates(_PatchOperation):
    op: Literal["set_dates"]
    check_in: str | None = None
    check_out: str | None = None


class SetAdults(_PatchOperation):
    op: Literal["set_adults"]
    count: int = Field(ge=1, le=30)


class AddChild(_PatchOperation):
    op: Literal["add_child"]
    age: int | None = Field(default=None, ge=0, le=17)
    guardian_adult_index: int | None = Field(default=None, ge=1, le=30)
    share_bed_with_guardian: bool | None = None
    requires_separate_bed: Literal[True] | None = None

    @model_validator(mode="after")
    def separate_bed_cannot_share_with_guardian(self) -> AddChild:
        if self.requires_separate_bed is True and self.share_bed_with_guardian is True:
            raise ValueError("A child requiring a separate bed cannot share with the guardian.")
        return self


class SetChildAge(_PatchOperation):
    op: Literal["set_child_age"]
    member_id: str
    age: int = Field(ge=0, le=17)


class SetChildSeparateBed(_PatchOperation):
    op: Literal["set_child_separate_bed"]
    child_id: str = Field(min_length=1, max_length=64)
    requires_separate_bed: bool


class RemoveChild(_PatchOperation):
    op: Literal["remove_child"]
    member_id: str


class SetRoomRequirements(_PatchOperation):
    op: Literal["set_room_requirements"]
    budget_amount: int | None = Field(default=None, ge=0, le=10_000_000_000)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    budget_basis: Literal["stay_total", "per_night"] | None = None
    budget_strength: Literal["hard", "target"] | None = None
    sharing: Literal["allow", "prefer", "avoid"] | None = Field(
        default=None, description="Bed sharing preference; this does not authorize sharing without party.bed_sharing consent.",
    )
    hard_accessibility_needs: list[str] | None = Field(default=None, max_length=8)
    preferred_accessibility_needs: list[str] | None = Field(default=None, max_length=8)
    hard_bed_types: list[CanonicalBedType] | None = Field(
        default=None, max_length=8, description=HARD_BED_TYPES_DESCRIPTION,
    )
    preferred_bed_types: list[str] | None = Field(default=None, max_length=8)
    avoided_bed_types: list[str] | None = Field(default=None, max_length=8)
    max_rooms: int | None = Field(default=None, ge=1, le=10)
    clear_fields: list[Literal[
        "budget_amount", "budget_currency", "budget_basis", "budget_strength", "sharing",
        "hard_accessibility_needs", "preferred_accessibility_needs", "hard_bed_types",
        "preferred_bed_types", "avoided_bed_types", "max_rooms",
    ]] = Field(default_factory=list, max_length=11)


class SetLocalGuidePreferences(_PatchOperation):
    """Typed trip preferences; hard needs require an exact current-turn quote."""

    op: Literal["set_local_guide_preferences"]
    venue_kinds: list[Literal["dining", "attraction"]] | None = Field(default=None, min_length=1, max_length=2)
    interests: list[Literal["quiet", "budget", "culture", "social", "nature", "indoor", "history"]] | None = Field(
        default=None, max_length=7,
    )
    pace: Literal["relaxed", "moderate", "active"] | None = None
    budget_amount: int | None = Field(default=None, ge=0, le=10_000_000)
    budget_currency: Literal["VND"] | None = None
    budget_basis: Literal["per_person"] | None = None
    budget_strength: Literal["hard", "target"] | None = None
    hard_accessibility_needs: list[Literal["step_free", "wheelchair_access"]] | None = Field(default=None, max_length=2)
    allergy_requirements: list[Literal["peanut", "shellfish", "dairy", "gluten"]] | None = Field(default=None, max_length=4)
    child_safety_required: bool | None = None
    clear_fields: list[Literal[
        "venue_kinds", "interests", "pace", "budget_amount", "budget_currency", "budget_basis",
        "budget_strength", "hard_accessibility_needs", "allergy_requirements", "child_safety_required",
    ]] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def coherent_budget(self) -> SetLocalGuidePreferences:
        if self.budget_amount is not None and (self.budget_currency != "VND" or self.budget_basis != "per_person"):
            raise ValueError("Local-guide budgets require VND and a per-person basis.")
        return self


class SetChildGuardian(_PatchOperation):
    op: Literal["set_child_guardian"]
    child_id: str = Field(min_length=1, max_length=64)
    guardian_id: str = Field(min_length=1, max_length=64)


class SetBedSharing(_PatchOperation):
    op: Literal["set_bed_sharing"]
    member_ids: list[str] = Field(min_length=2, max_length=10)
    allow_share: bool


class ClarifyField(_PatchOperation):
    op: Literal["clarify"]
    field: str
    reason: str | None = Field(default=None, max_length=300)


GuestBriefOperation = Annotated[
    SetDates | SetAdults | AddChild | SetChildAge | SetChildSeparateBed | RemoveChild | SetRoomRequirements
    | SetLocalGuidePreferences
    | SetChildGuardian | SetBedSharing | ClarifyField,
    Field(discriminator="op"),
]


class HospitalityGuestBriefPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ops: list[GuestBriefOperation] = Field(default_factory=list, max_length=12)


class GuestPatchAuthorization(BaseModel):
    """Same-turn provenance asserted for one proposed operation."""

    model_config = ConfigDict(extra="forbid")
    operation_index: int = Field(ge=0, le=11)
    op: Literal["set_dates", "set_adults", "add_child", "set_child_age", "set_child_separate_bed", "remove_child",
                "set_room_requirements", "set_local_guide_preferences", "set_child_guardian", "set_bed_sharing", "clarify"]
    target_fields: list[Annotated[str, Field(max_length=128, pattern=(
        r"^(?:dates\.(?:check_in|check_out)|party\.(?:adults|children|guardians|bed_sharing)|room_requirements|"
        r"party\.(?:children|guardians)\.[A-Za-z0-9_-]+(?:\.(?:age|requires_separate_bed))?|room_requirements\."
        r"(?:budget_amount|budget_currency|budget_basis|budget_strength|sharing|"
        r"hard_accessibility_needs|preferred_accessibility_needs|hard_bed_types|"
        r"preferred_bed_types|avoided_bed_types|max_rooms)|local_guide_preferences(?:\.(?:venue_kinds|interests|pace|budget_amount|budget_currency|budget_basis|budget_strength|hard_accessibility_needs|allergy_requirements|child_safety_required))?)$"
    ))]] = Field(min_length=1, max_length=11)
    intent: Literal["explicit_request", "clarification"]
    current_turn_quote: str = Field(min_length=1, max_length=500)


GuestTurnIntent = Literal["hotel_information", "guest_state", "guest_edit", "courtesy", "room_advice", "local_guide", "booking_request"]


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


def _inline_patch_authorizations(payload: Any, operations: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    patch = getattr(payload, "guest_patch", None)
    proposed_ops = tuple(getattr(patch, "ops", ())) if patch is not None else ()
    if len(proposed_ops) != len(operations):
        raise ValueError("Every guest edit requires one inline current-turn quote.")
    records = []
    for index, (model_operation, operation) in enumerate(zip(proposed_ops, operations, strict=True)):
        quote = getattr(model_operation, "current_turn_quote", None)
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError("Every guest edit requires one inline current-turn quote.")
        records.append({
            "operation_index": index,
            "op": operation.get("op"),
            "target_fields": _patch_target_fields(operation),
            "intent": "clarification" if operation.get("op") == "clarify" else "explicit_request",
            "current_turn_quote": quote,
        })
    return tuple(records)


def validate_inline_patch_quotes(patch: Any) -> None:
    """Require wire quotes while leaving the internal canonical proposal quote-free."""
    if patch is None:
        return
    for operation in getattr(patch, "ops", ()):
        quote = getattr(operation, "current_turn_quote", None)
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError("Every guest edit requires one inline current-turn quote.")


def validate_preparation_metadata(
    payload: Any, patch: GuestBriefProposal | None, question: str,
) -> tuple[tuple[str, ...], tuple[dict[str, Any], ...]]:
    intents = tuple(dict.fromkeys(getattr(payload, "turn_intents", ())))
    valid_intents = {"hotel_information", "guest_state", "guest_edit", "courtesy", "room_advice", "local_guide", "booking_request"}
    if not intents or any(intent not in valid_intents for intent in intents):
        raise ValueError("Preparation must classify at least one current-turn intent.")
    operations = patch.operations if patch is not None else ()
    if "guest_patch_authorizations" in getattr(payload, "model_fields_set", set()):
        raise ValueError("Patch authorization is derived from inline operation quotes.")
    authorizations = _inline_patch_authorizations(payload, operations)
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
    valid_intents = {"hotel_information", "guest_state", "guest_edit", "courtesy", "room_advice", "local_guide", "booking_request"}
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
    if "room_requirements.budget_strength" in pending_fields:
        fields.append("room_requirements.budget_strength")
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
        targets = ["party.children"]
        if operation.get("guardian_adult_index") is not None:
            targets.append("party.guardians")
        if operation.get("share_bed_with_guardian") is not None:
            targets.append("party.bed_sharing")
        return targets
    if op == "set_child_age":
        return [f"party.children.{operation.get('member_id')}.age"]
    if op == "set_child_separate_bed":
        return [f"party.children.{operation.get('child_id')}.requires_separate_bed"]
    if op == "remove_child":
        return [f"party.children.{operation.get('member_id')}"]
    if op == "set_child_guardian":
        return [f"party.guardians.{operation.get('child_id')}"]
    if op == "set_bed_sharing":
        return ["party.bed_sharing"]
    if op == "set_room_requirements":
        requirement_fields = (
            "budget_amount", "budget_currency", "budget_basis", "budget_strength", "sharing",
            "hard_accessibility_needs", "preferred_accessibility_needs", "hard_bed_types",
            "preferred_bed_types", "avoided_bed_types", "max_rooms",
        )
        cleared = set(operation.get("clear_fields") or ())
        return [
            f"room_requirements.{field}" for field in requirement_fields
            if field in cleared or operation.get(field) is not None
        ]
    if op == "set_local_guide_preferences":
        preference_fields = (
            "venue_kinds", "interests", "pace", "budget_amount", "budget_currency", "budget_basis",
            "budget_strength", "hard_accessibility_needs", "allergy_requirements", "child_safety_required",
        )
        cleared = set(operation.get("clear_fields") or ())
        return [
            f"local_guide_preferences.{field}" for field in preference_fields
            if field in cleared or operation.get(field) is not None
        ]
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
    if "room_requirements" in current.data:
        data["room_requirements"] = dict(current.data.get("room_requirements") or {})
    if "local_guide_preferences" in current.data:
        data["local_guide_preferences"] = dict(current.data.get("local_guide_preferences") or {})
    data["dates"].setdefault("check_in", None)
    data["dates"].setdefault("check_out", None)
    data["dates"].setdefault("nights", None)
    data["party"].setdefault("adults", None)
    data["party"]["children"] = [dict(child) for child in data["party"].get("children", [])]
    if "guardians" in data["party"]:
        data["party"]["guardians"] = dict(data["party"].get("guardians") or {})
    pending = set(current.pending_fields)
    fields: set[str] = set()
    delta: dict[str, object] = {"dates": {}, "party": {}, "room_requirements": {}, "local_guide_preferences": {}}
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
            if operation.requires_separate_bed is True:
                child["requires_separate_bed"] = True
            data["party"]["children"].append(child)
            fields.add(f"party.children.{member_id}")
            delta["party"].setdefault("children_added", []).append(child)
            if operation.guardian_adult_index is not None:
                adults = data["party"].get("adults") or 0
                if operation.guardian_adult_index > adults:
                    raise ValueError("The authorized guardian adult does not exist in the current brief.")
                guardian_id = f"adult-{operation.guardian_adult_index}"
                data["party"].setdefault("guardians", {})[member_id] = guardian_id
                delta["party"].setdefault("guardians", {})[member_id] = guardian_id
                fields.add(f"party.guardians.{member_id}")
            elif operation.share_bed_with_guardian is not None:
                raise ValueError("Explicit child bed sharing requires an identified guardian adult.")
            if operation.share_bed_with_guardian is not None:
                guardian_id = f"adult-{operation.guardian_adult_index}"
                group = {"member_ids": sorted((member_id, guardian_id)),
                         "allow_share": operation.share_bed_with_guardian}
                data["party"].setdefault("bed_sharing", []).append(group)
                delta["party"].setdefault("bed_sharing", []).append(group)
                fields.add("party.bed_sharing")
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
        elif isinstance(operation, SetChildSeparateBed):
            fields.add(f"party.children.{operation.child_id}.requires_separate_bed")
            try:
                UUID(operation.child_id)
            except ValueError as exc:
                raise ValueError("A child edit must use a known stable member ID.") from exc
            child = next((item for item in data["party"]["children"]
                          if item.get("member_id") == operation.child_id), None)
            if child is None:
                raise ValueError("The referenced child is not in the current brief.")
            if operation.requires_separate_bed:
                if child.get("requires_separate_bed") is not True:
                    child["requires_separate_bed"] = True
                    delta["party"].setdefault("children_updated", []).append(dict(child))
                    changed = True
            elif child.pop("requires_separate_bed", None) is not None:
                delta["party"].setdefault("children_updated", []).append(dict(child))
                changed = True
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
        elif isinstance(operation, SetChildGuardian):
            fields.add(f"party.guardians.{operation.child_id}")
            if not any(item.get("member_id") == operation.child_id for item in data["party"]["children"]):
                raise ValueError("The referenced child is not in the current brief.")
            adults = data["party"].get("adults") or 0
            if operation.guardian_id not in {f"adult-{index}" for index in range(1, adults + 1)}:
                raise ValueError("A guardian must be an identified adult in the current brief.")
            if data["party"].get("guardians", {}).get(operation.child_id) != operation.guardian_id:
                data["party"].setdefault("guardians", {})[operation.child_id] = operation.guardian_id
                delta["party"].setdefault("guardians", {})[operation.child_id] = operation.guardian_id
                changed = True
        elif isinstance(operation, SetRoomRequirements):
            fields.add("room_requirements")
            if set(operation.clear_fields) & {
                key for key in operation.model_fields_set - {"op", "clear_fields", "current_turn_quote"}
                if getattr(operation, key) is not None
            }:
                raise ValueError("A room requirement cannot be set and cleared in one operation.")
            requirements = data.setdefault("room_requirements", {})
            for key in operation.clear_fields:
                if key in requirements:
                    requirements.pop(key)
                    delta["room_requirements"][key] = None
                    changed = True
                pending.discard(f"room_requirements.{key}")
            for key in operation.model_fields_set - {"op", "clear_fields", "current_turn_quote"}:
                value = getattr(operation, key)
                if value is not None and requirements.get(key) != value:
                    requirements[key] = value
                    delta["room_requirements"][key] = value
                    changed = True
                if value is not None:
                    pending.discard(f"room_requirements.{key}")
        elif isinstance(operation, SetLocalGuidePreferences):
            if set(operation.clear_fields) & {
                key for key in operation.model_fields_set - {"op", "clear_fields", "current_turn_quote"}
                if getattr(operation, key) is not None
            }:
                raise ValueError("A local-guide preference cannot be set and cleared in one operation.")
            preferences = data.setdefault("local_guide_preferences", {})
            preference_fields = (
                "venue_kinds", "interests", "pace", "budget_amount", "budget_currency", "budget_basis",
                "budget_strength", "hard_accessibility_needs", "allergy_requirements", "child_safety_required",
            )
            for key in operation.clear_fields:
                if key in preferences:
                    preferences.pop(key)
                    delta["local_guide_preferences"][key] = None
                    changed = True
            for key in operation.model_fields_set - {"op", "clear_fields", "current_turn_quote"}:
                value = getattr(operation, key)
                if value is not None and preferences.get(key) != value:
                    preferences[key] = value
                    delta["local_guide_preferences"][key] = value
                    changed = True
            if preferences.get("budget_amount") is not None and preferences.get("budget_strength") not in {"hard", "target"}:
                pending.add("local_guide_preferences.budget_strength")
                clarification = True
            else:
                pending.discard("local_guide_preferences.budget_strength")
            fields.update(f"local_guide_preferences.{key}" for key in preference_fields
                          if key in operation.clear_fields or getattr(operation, key) is not None)
        elif isinstance(operation, SetBedSharing):
            fields.add("party.bed_sharing")
            all_members = {f"adult-{index}" for index in range(1, (data["party"].get("adults") or 0) + 1)}
            all_members.update(child["member_id"] for child in data["party"]["children"])
            if len(set(operation.member_ids)) != len(operation.member_ids) or not set(operation.member_ids) <= all_members:
                raise ValueError("Bed-sharing preference must name distinct current party members.")
            groups = [dict(group) for group in data["party"].get("bed_sharing", [])
                      if set(group.get("member_ids", ())) != set(operation.member_ids)]
            groups.append({"member_ids": sorted(operation.member_ids), "allow_share": operation.allow_share})
            if groups != data["party"].get("bed_sharing", []):
                data["party"]["bed_sharing"] = groups
                delta["party"]["bed_sharing"] = groups
                changed = True
        elif isinstance(operation, ClarifyField):
            child_age_field = operation.field.startswith("party.children.") and operation.field.endswith(".age")
            if child_age_field:
                try:
                    UUID(operation.field.split(".")[2])
                except ValueError as exc:
                    raise ValueError("Child clarification must use a stable member ID.") from exc
            if operation.field not in {
                "dates.check_in", "dates.check_out", "party.adults", "party.children.member",
                "room_requirements", "room_requirements.hard_bed_types", "room_requirements.budget_strength",
            } and not child_age_field:
                raise ValueError("The clarification field is outside the guest brief.")
            fields.add(operation.field)
            pending.add(operation.field)
            clarification = True
    if not delta["dates"]:
        delta.pop("dates")
    if not delta["party"]:
        delta.pop("party")
    if not delta["room_requirements"]:
        delta.pop("room_requirements")
    if not delta["local_guide_preferences"]:
        delta.pop("local_guide_preferences")
    if data.get("room_requirements") == {}:
        data.pop("room_requirements")
    if data.get("local_guide_preferences") == {}:
        data.pop("local_guide_preferences")
    requirements = data.get("room_requirements") or {}
    if requirements.get("budget_amount") is not None and requirements.get("budget_strength") not in {"hard", "target"}:
        pending.add("room_requirements.budget_strength")
        clarification = True
    else:
        pending.discard("room_requirements.budget_strength")
    if data["party"].get("guardians") == {}:
        data["party"].pop("guardians")
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
