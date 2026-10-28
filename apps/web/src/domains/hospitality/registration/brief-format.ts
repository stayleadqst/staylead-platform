import type { GuestBriefConfirmationChange, GuestBriefConfirmationLine } from "@/composition/domain_registry";

export type HospitalityBriefDelta = Readonly<{
  dates?: Readonly<{ check_in?: string | null; check_out?: string | null; nights?: number | null }>;
  party?: Readonly<{
    adults?: number;
    children_added?: readonly { age: number | null }[];
    children_updated?: readonly { age: number | null }[];
    children_removed?: readonly unknown[];
  }>;
}>;

export function formatHospitalityBriefDelta(changes: HospitalityBriefDelta): string {
  const lines: string[] = [];
  const dates = changes.dates;
  if (dates) {
    if (Object.hasOwn(dates, "check_in")) {
      lines.push(`Check-in changed to ${dates.check_in ?? "not set"}.`);
    }
    if (Object.hasOwn(dates, "check_out")) {
      lines.push(`Check-out changed to ${dates.check_out ?? "not set"}.`);
    }
    if (Object.hasOwn(dates, "nights") && dates.nights !== null) {
      lines.push(`Stay length is ${dates.nights} ${dates.nights === 1 ? "night" : "nights"}.`);
    }
  }
  if (changes.party?.adults !== undefined) {
    lines.push(`Adults: ${changes.party.adults}.`);
  }
  for (const child of changes.party?.children_added ?? []) {
    lines.push(child.age === null ? "Added a child; their age is still needed." : `Added a child, age ${child.age}.`);
  }
  for (const child of changes.party?.children_updated ?? []) {
    lines.push(`Updated a child's age to ${child.age}.`);
  }
  const removed = changes.party?.children_removed?.length ?? 0;
  if (removed) lines.push(`Removed ${removed === 1 ? "a child" : `${removed} children`} from the trip.`);
  return lines.length ? lines.join(" ") : "No trip details changed.";
}


const CONFIRMATION_FIELDS: Readonly<Record<string, string>> = {
  "dates.check_in": "Check-in date",
  "dates.check_out": "Check-out date",
  "dates.nights": "Stay length",
  "party.adults": "Adults",
  "party.children": "Children",
  "party.guardians": "Guardians",
  "party.bed_sharing": "Bed sharing",
  "room_requirements.hard_accessibility_needs": "Required room accessibility",
  "room_requirements.preferred_accessibility_needs": "Preferred room accessibility",
  "room_requirements.hard_bed_types": "Required bed types",
  "room_requirements.preferred_bed_types": "Preferred bed types",
  "room_requirements.avoided_bed_types": "Bed types to avoid",
  "room_requirements.max_rooms": "Maximum rooms",
  "local_guide_preferences.venue_kinds": "Venue types",
  "local_guide_preferences.interests": "Interests",
  "local_guide_preferences.pace": "Pace",
  "local_guide_preferences.budget_amount": "Budget amount",
  "local_guide_preferences.budget_currency": "Budget currency",
  "local_guide_preferences.budget_basis": "Budget basis",
  "local_guide_preferences.budget_strength": "Budget requirement",
  "local_guide_preferences.hard_accessibility_needs": "Required venue accessibility",
  "local_guide_preferences.allergy_requirements": "Allergy requirements",
  "local_guide_preferences.child_safety_required": "Child-safety requirements",
  pending_fields: "Details still needed",
};

function readableValue(value: unknown, present: boolean | undefined): string {
  if (present === false || value === null || value === undefined) return "Not set";
  if (Array.isArray(value)) return value.map((item) => readableValue(item, true)).join(", ") || "None";
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if ("age" in record) return record.age === null ? "Age not set" : `Age ${String(record.age)}`;
    return Object.entries(record)
      .filter(([key]) => key !== "member_id")
      .map(([key, item]) => `${humanize(key)}: ${readableValue(item, true)}`).join("; ") || "None";
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function flatten(path: string, value: unknown): Array<{ field: string; value: unknown }> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) => flatten(`${path}.${key}`, child));
  }
  return [{ field: path, value }];
}

export function formatHospitalityBriefConfirmationChanges(
  changes: readonly GuestBriefConfirmationChange[],
): readonly GuestBriefConfirmationLine[] {
  const lines: GuestBriefConfirmationLine[] = [];
  for (const change of changes) {
    if (change.field === "pending_fields") {
      lines.push({
        field: CONFIRMATION_FIELDS.pending_fields,
        before: readableValue(change.before, true),
        after: readableValue(change.after, true),
      });
      continue;
    }
    const before = change.before_present === false ? [] : flatten(change.field, change.before);
    const after = change.after_present === false ? [] : flatten(change.field, change.after);
    const beforeByField = new Map(before.map((item) => [item.field, item.value]));
    const afterByField = new Map(after.map((item) => [item.field, item.value]));
    const fields = new Set([...beforeByField.keys(), ...afterByField.keys()]);
    for (const field of [...fields].sort()) {
      const beforeExists = beforeByField.has(field);
      const afterExists = afterByField.has(field);
      const beforeValue = beforeByField.get(field);
      const afterValue = afterByField.get(field);
      if (beforeExists && afterExists && JSON.stringify(beforeValue) === JSON.stringify(afterValue)) continue;
      lines.push({
        field: CONFIRMATION_FIELDS[field] ?? humanize(field.split(".").at(-1) ?? field),
        before: readableValue(beforeValue, beforeExists),
        after: readableValue(afterValue, afterExists),
      });
    }
  }
  return lines;
}
