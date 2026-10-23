/** Append an allowlisted path without allowing a root base to become `//path`. */
export function buildUpstreamUrl(base: URL, backendPath: string): URL {
  const target = new URL(base);
  const basePath = target.pathname.replace(/\/+$/, "");
  target.pathname = `${basePath}${backendPath}`;
  return target;
}
