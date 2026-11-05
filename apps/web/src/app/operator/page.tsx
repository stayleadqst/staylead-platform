"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const PROPERTY_ID = "HTL-S8-DEMO";
type SourceRef = Readonly<{
  source_id: string;
  version?: string;
  source_version?: string;
  hash?: string;
  source_hash?: string;
  generation?: number;
  source_generation?: number;
  guest_approved?: boolean;
  status?: string;
}>;
type Preview = Readonly<{
  hotel_id: string;
  lifecycle_status: string;
  snapshot_generation: number | null;
  venues: readonly Record<string, unknown>[];
  providers: readonly Record<string, unknown>[];
  directional_routes: readonly Record<string, unknown>[];
  gaps: readonly string[];
  conflicts: readonly Record<string, unknown>[];
  source_refs: readonly SourceRef[];
}>;
type Action = "preview" | "import" | "activate" | "refresh" | "delete" | "revoke";

async function api(action: Action, token: string, body?: Record<string, unknown>) {
  const response = await fetch(`/api/operator/properties/${PROPERTY_ID}/guide/${action}`, {
    method: action === "preview" ? "GET" : "POST",
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(action === "preview" ? {} : { "content-type": "application/json" }),
    },
    ...(action === "preview" ? {} : { body: JSON.stringify(body ?? {}) }),
    cache: "no-store", credentials: "same-origin",
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = value?.error;
    const failure = new Error(typeof error?.message === "string" ? error.message : `Request failed (${response.status}).`);
    (failure as Error & { status?: number }).status = response.status;
    throw failure;
  }
  return value;
}

export default function OperatorPage() {
  const [token, setToken] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [sourceId, setSourceId] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [oidc, setOidc] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const requestEpoch = useRef(0);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("auth") === "error") {
      window.history.replaceState({}, "", "/operator");
      window.setTimeout(() => setMessage("Sign-in was rejected or expired. Please try again."), 0);
    }
    const sessionEpoch = requestEpoch.current;
    void fetch("/api/operator/auth/session", { cache: "no-store", credentials: "same-origin" }).then((response) => {
      if (requestEpoch.current !== sessionEpoch) return;
      setOidc(response.status !== 404);
      setAuthenticated(response.ok);
    }).catch(() => {
      if (requestEpoch.current === sessionEpoch) setOidc(true);
    });
  }, []);
  const protectedPreview = oidc && !authenticated ? null : preview;
  const sources = useMemo(() => protectedPreview?.source_refs ?? [], [protectedPreview]);
  const selectedSource = sources.find((source) => source.source_id === sourceId) ?? sources[0];

  async function loadPreview(activeToken = token, isCurrent: () => boolean = () => true) {
    if (!activeToken && !authenticated) throw new Error("Sign in before opening the protected guide.");
    const result = await api("preview", activeToken) as Preview;
    if (!isCurrent()) return null;
    setPreview(result);
    const firstSource = result.source_refs?.find((source) => source.source_id.startsWith("S8-GUIDE-"));
    setSourceId(firstSource?.source_id ?? "");
    return result;
  }

  async function perform(action: Action) {
    if (busy || logoutPending || (oidc && !authenticated)) return;
    const requestEpochAtStart = requestEpoch.current;
    const isCurrent = () => requestEpoch.current === requestEpochAtStart;
    setBusy(true);
    setMessage("");
    try {
      if (action === "preview") {
        await loadPreview(token, isCurrent);
        if (!isCurrent()) return;
        setMessage("Protected preview loaded.");
      } else if (action === "import") {
        const imported = await api(action, token) as { preview?: Preview };
        if (!isCurrent()) return;
        if (imported.preview) {
          setPreview(imported.preview);
          const firstSource = imported.preview.source_refs?.find((source) => source.source_id.startsWith("S8-GUIDE-"));
          setSourceId(firstSource?.source_id ?? "");
        } else await loadPreview(token, isCurrent);
        if (!isCurrent()) return;
        setMessage("Synthetic guide imported in staged state.");
      } else {
        if (!selectedSource) throw new Error("Import the guide and select a source first.");
        const generation = selectedSource.generation ?? selectedSource.source_generation ?? preview?.snapshot_generation;
        const version = selectedSource.version ?? selectedSource.source_version;
        const hash = selectedSource.hash ?? selectedSource.source_hash;
        if (generation === undefined || generation === null || !version || !hash)
          throw new Error("The selected source is missing its current version binding. Refresh the preview.");
        await api(action, token, {
          source_id: selectedSource.source_id,
          expected_generation: generation,
          expected_version: version,
          expected_source_hash: hash,
          operation_id: crypto.randomUUID(),
          ...(action === "refresh" ? { revision: selectedSource.source_id === "S8-GUIDE-PRIMARY"
            ? "primary-price-110000" : "secondary-hours-confirmed" } : {}),
        });
        if (!isCurrent()) return;
        await loadPreview(token, isCurrent);
        if (!isCurrent()) return;
        setMessage(`Source ${action} completed; preview refreshed.`);
      }
    } catch (error) {
      if (!isCurrent()) return;
      if ((error as Error & { status?: number }).status === 401) {
        requestEpoch.current += 1;
        setAuthenticated(false); setPreview(null); setSourceId("");
        setBusy(false);
      }
      setMessage(error instanceof Error ? error.message : "The operator action failed.");
    } finally {
      if (isCurrent()) setBusy(false);
    }
  }

  return <main className="operator-page" data-testid="operator-page">
    <p className="operator-kicker">StayLead · Development operator</p>
    <h1>Local guide controls</h1>
    <p className="status-note">Synthetic local operator pilot for Lotus Demo.</p>
    {oidc && !authenticated ? <p role="status">Guest session. Sign in to access the protected guide.</p> : null}
    {oidc ? <div className="operator-actions">
      {!authenticated ? <form action="/api/operator/auth/login" method="get"><button type="submit" disabled={logoutPending}>Sign in with local OIDC</button></form> : <button type="button" disabled={logoutPending} onClick={async () => {
        const logoutEpoch = ++requestEpoch.current;
        setLogoutPending(true); setAuthenticated(false); setPreview(null); setSourceId(""); setBusy(false); setMessage("Signing out…");
        try {
          const response = await fetch("/api/operator/auth/logout", { method: "POST", credentials: "same-origin" });
          if (requestEpoch.current === logoutEpoch)
            setMessage(response.status === 204 ? "Signed out." : "Sign-out could not be confirmed. Please sign in again.");
        } catch {
          if (requestEpoch.current === logoutEpoch)
            setMessage("Sign-out could not be confirmed. Please sign in again.");
        } finally {
          if (requestEpoch.current === logoutEpoch) setLogoutPending(false);
        }
      }}>Sign out</button>}
    </div> : <label className="operator-field">Dev operator credential
      <input type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} aria-label="Dev operator credential" />
    </label>}
    <div className="operator-actions">
      <button type="button" disabled={busy || (!token && !authenticated)} onClick={() => void perform("import")}>Import synthetic guide</button>
      <button type="button" disabled={busy || (!token && !authenticated)} onClick={() => void perform("preview")}>Refresh preview</button>
    </div>
    <section aria-label="Protected guide preview">
      <h2>Protected preview</h2>
      {protectedPreview ? <>
        <p>Property {protectedPreview.hotel_id} · generation {protectedPreview.snapshot_generation ?? "—"} · {protectedPreview.lifecycle_status}</p>
        <p>Venues: {protectedPreview.venues.length} · Providers: {protectedPreview.providers.length} · Directional routes: {protectedPreview.directional_routes.length}</p>
        {protectedPreview.gaps.length > 0 && <ul className="status-note">{protectedPreview.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>}
        {protectedPreview.conflicts.length > 0 && <p className="status-note">Conflicts to review: {protectedPreview.conflicts.length}</p>}
        <label className="operator-field">Guide source
          <select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
            {sources.filter((source) => source.source_id.startsWith("S8-GUIDE-")).map((source) => <option key={source.source_id} value={source.source_id}>
              {source.source_id} · {source.status ?? "unknown"} · {source.guest_approved ? "guest approved" : "staged"}
            </option>)}
          </select>
        </label>
        <div className="operator-actions">
          <button type="button" disabled={busy || (!token && !authenticated) || !selectedSource} onClick={() => void perform("activate")}>Activate</button>
          <button type="button" disabled={busy || (!token && !authenticated) || !selectedSource} onClick={() => void perform("refresh")}>
            {selectedSource?.source_id === "S8-GUIDE-PRIMARY" ? "Refresh price to 110,000 VND" : "Resolve hours conflict"}
          </button>
          <button type="button" disabled={busy || (!token && !authenticated) || !selectedSource} onClick={() => void perform("revoke")}>Revoke</button>
          <button type="button" disabled={busy || (!token && !authenticated) || !selectedSource} onClick={() => void perform("delete")}>Delete</button>
        </div>
        <details><summary>Source and record details</summary><pre>{JSON.stringify(preview, null, 2)}</pre></details>
      </> : <p>No protected preview loaded yet.</p>}
    </section>
    <p role="status" aria-live="polite">{busy ? "Working…" : message}</p>
    {!oidc && <button type="button" className="operator-clear" onClick={() => { setToken(""); setPreview(null); setSourceId(""); setMessage("Credential cleared from page memory."); }}>Clear credential</button>}
  </main>;
}
