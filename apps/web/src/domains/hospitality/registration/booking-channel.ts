/** Reject non-HTTPS, credentialed, parameterized, or fragment destinations. */
export function safeBookingDestination(value: unknown): string | undefined {
  if (typeof value !== "string" || value.length > 2048 || value !== value.trim()
      || /[\\\s\u0000-\u001f\u007f]/u.test(value)) return undefined;
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) return undefined;
    return value;
  } catch {
    return undefined;
  }
}
