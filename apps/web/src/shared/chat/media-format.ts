export function formatMediaTime(seconds: number): string {
  const milliseconds = Math.max(0, Math.round(seconds * 1000));
  const wholeSeconds = Math.floor(milliseconds / 1000);
  const fraction = milliseconds % 1000;
  const time = `${Math.floor(wholeSeconds / 60)}:${String(wholeSeconds % 60).padStart(2, "0")}`;
  if (!fraction) return time;
  const decimal = String(fraction).padStart(3, "0").replace(/0+$/, "");
  return `${time}.${decimal}`;
}
