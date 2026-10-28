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
  const source = ref.source ?? {};
  const fields = [
    source.source_id,
    source.source_version,
    source.localized_status ?? source.status,
    typeof source.source_generation === "number" ? `generation ${source.source_generation}` : undefined,
    typeof source.valid_from === "string" ? `from ${source.valid_from}` : undefined,
    typeof source.valid_to === "string" ? `through ${source.valid_to}` : undefined,
    typeof source.source_hash === "string" ? source.source_hash.slice(0, 12) : undefined,
    ref.fact_ids?.length ? ref.fact_ids.join(", ") : undefined,
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
