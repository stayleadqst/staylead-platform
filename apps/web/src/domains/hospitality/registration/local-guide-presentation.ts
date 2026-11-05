export type LocalGuideSourceReference = Readonly<{
  source?: Readonly<Record<string, unknown>>;
  fact_ids?: readonly string[];
}>;

export function visibleLocalGuideClaims<T>(claims: readonly T[], stale: boolean, freshnessError: boolean): readonly T[] {
  return stale || freshnessError ? [] : claims;
}

export function localGuideVerificationText(
  claim: Readonly<{ localized_unknowns?: readonly string[]; unknown_codes?: readonly string[] }>,
  fallback: string,
): readonly string[] {
  if (claim.localized_unknowns?.length) return claim.localized_unknowns;
  if (claim.unknown_codes?.length) return [fallback];
  return [];
}

export function localGuideSourceLine(ref: LocalGuideSourceReference): string {
  const source = ref.source ?? ref as Readonly<Record<string, unknown>>;
  const factIds = ref.fact_ids ?? (typeof source.fact_id === "string" ? [source.fact_id] : []);
  const fields = [
    source.source_id,
    source.source_version,
    source.localized_status ?? source.status,
    typeof source.source_generation === "number" ? `generation ${source.source_generation}` : undefined,
    typeof source.valid_from === "string" ? `from ${source.valid_from}` : undefined,
    typeof source.valid_to === "string" ? `through ${source.valid_to}` : undefined,
    typeof source.source_hash === "string" ? source.source_hash.slice(0, 12) : undefined,
    factIds.length ? factIds.join(", ") : undefined,
  ];
  return fields.filter((field): field is string => typeof field === "string" && field.length > 0).join(" · ");
}

export function formatLocalGuidePrice(
  value: unknown,
  languageTag: string,
  unknownLabel: string,
  perPersonLabel: string,
): string {
  if (!value || typeof value !== "object") return unknownLabel;
  const price = value as { amount?: unknown; currency?: unknown; basis?: unknown; status?: unknown };
  if (typeof price.amount !== "number" || !Number.isFinite(price.amount)
    || typeof price.currency !== "string" || typeof price.basis !== "string") return unknownLabel;
  let amount: string;
  try { amount = new Intl.NumberFormat(languageTag).format(price.amount); }
  catch { amount = String(price.amount); }
  return `${amount} ${price.currency} / ${price.basis === "per_person" ? perPersonLabel : price.basis}`;
}

export function formatTransportPrice(value: Readonly<{
  amount: number | null; total_amount: number | null; currency: string | null;
  basis: "per_vehicle_one_way" | "per_person_one_way" | null; status: string;
}>, languageTag: string): string {
  if (value.status !== "known" || !value.currency || !value.basis) return "Price unknown or not comparable";
  const amount = value.total_amount ?? value.amount;
  if (amount === null || !Number.isSafeInteger(amount) || amount < 0) return "Price unknown or not comparable";
  let formatted: string;
  try { formatted = new Intl.NumberFormat(languageTag).format(amount); }
  catch { formatted = String(amount); }
  const basis = value.total_amount !== null ? "total, one way"
    : value.basis === "per_vehicle_one_way" ? "per vehicle, one way" : "per person, one way";
  return `${formatted} ${value.currency} · ${basis}`;
}

export function approvedSyntheticTransportUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  if (value === "https://www.grab.com/vn/transport/car/"
    || value === "https://www.greensm.com/vn-vi/greensm-car") return value;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.hostname !== "example.com" || url.username || url.password
      || url.search || url.hash || url.pathname === "/") return null;
    return url.toString();
  } catch { return null; }
}

export function transportCheckLabel(status: string): string {
  if (status === "fit") return "Fits the supplied requirement";
  if (status === "not_fit") return "Does not fit the supplied requirement";
  if (status === "not_required") return "No requirement supplied";
  return "Could not confirm";
}
