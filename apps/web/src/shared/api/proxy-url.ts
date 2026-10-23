/** Append an allowlisted path without allowing a root base to become `//path`. */
export function buildUpstreamUrl(base: URL, backendPath: string): URL {
  const target = new URL(base);
  const queryStart = backendPath.indexOf("?");
  const path = queryStart < 0 ? backendPath : backendPath.slice(0, queryStart);
  const query = queryStart < 0 ? "" : backendPath.slice(queryStart + 1);
  const basePath = target.pathname.replace(/\/+$/, "");
  target.pathname = `${basePath}${path}`;
  target.search = query;
  return target;
}
