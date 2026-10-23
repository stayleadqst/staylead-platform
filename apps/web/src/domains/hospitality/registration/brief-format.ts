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
