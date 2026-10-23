# Sprint 4 independent review

Reviewer: fresh `/root/reviewer`, `gpt-6.1-sol/high`. Product files were not edited. Initial candidate: source/test/fixture manifest SHA `e4e7dd4923f38832b425f405b4e42bd878abd9527122ceff0da06ce2dc9a3577`, baseline `1e020d0`. Final reviewed candidate: `a358cfef3ccfbd354fcf2b1ad6ea71ef79db7a413f9b20c06ac78d3225f2b7a4`; independently compared all 192 manifest files with disk: zero deltas. Read root/repo instructions, four mandatory architecture/execution documents, and exact #79–#82 acceptance criteria.

## Findings

No unresolved reproduced product finding on the final reviewed candidate. The following findings were repaired and affected checks rerun:

1. **P2 — L1-AC3: revoked facts incorrectly consumed the active hotel limit.** Import A=1 and B=396 facts; revoke B; eligible consumer facts=1; refresh A with 400 valid approved facts. Initially rejected with `ValueError: aggregate active hotel facts exceed the 400 fact limit`. After repair: publication applied and actual eligible consumer facts=400. **Closed.**
2. **P1 — schema-3 upgrade failed while hashing persisted fact timestamps.** Baseline-created schema-3 fixture database failed migration 4 with `TypeError` serializing `imported_at`. After repair, UTC timestamp serialization and trusted legacy source backfill allow migration without reimport. **Closed.**
3. **P1 — existing saved replay/history lacked lifecycle bindings after upgrade.** Intermediate migration preserved 109 facts/session state but a still-current saved request returned `409 stale_source`, and old assistant prose remained in projected history after revoke. After response/history backfill: original replay `200` with zero provider calls; new turn `200`; old assistant prose excluded after revoke. Session version and all 109 facts were preserved during migration. Existing S3 pack media replay also returned a bound descriptor and authenticated PNG `200`; first-import receipt remained no-op. **Closed.**

## Independent behavior evidence

Ran targeted offline probes against local PostgreSQL 18 through the dedicated Unix socket, using separate reviewer databases; no root/builder databases were mutated. Sanitized probe scripts and observed results are preserved in [`review-probes`](review-probes/README.md). Atomic/isolation probes checked:

| AC/path | Observed |
| --- | --- |
| L1-AC1/AC3 scope/config | Foreign B-owned fact ID and changed authoritative public config rejected before publication. |
| L1-AC2 interrupted publication | Injected failure after source deletes and before new fact insertion; original facts, approved media, source hash, last-success metadata and generation preserved. |
| L1-AC2 retry/race | Two concurrent retries of the same operation after rollback produced exactly `applied` and `noop`. |
| L1-AC4/AC5 delete/isolation | Actual delete removed A facts/media eligibility; B facts preserved; retry was no-op. |
| L1-AC6 receipt replay | Identical original import after deletion returned no-op with current deleted state/generation and did not restore A. |
| L3-AC4 media identity/scope | Wrong hotel and pre-refresh descriptor fetched no bytes after same-ID refresh. |

Source review traced typed lifecycle bindings from M1 through API completion/replay/history and authenticated version-bound PNG/MP4/VTT reads into web freshness handling. Commit acquires the shared hotel lock and rechecks expiry after scope locks; operation replay is checked again under the hotel lock. Final snapshot reads hold `FOR SHARE` on the hotel while reading generation and sources. Final repository joins fail closed without a matching approved source. Existing builder/relevant-suite evidence is reused, not represented as independent reruns.

## Consumer acceptance and limitations

Reviewer inspected `backend-repaired-final-tests.log` (68 passed), `backend-final-lint.log` (all checks passed), `web-final-contracts.log` (26 passed), and production build evidence. Coordinator also reports relevant compile/diff checks passing. The earlier failing `backend-final-tests.log` remains preserved. Reviewer inspected saved browser screenshots showing stale labels and old media absent. Coordinator reports actual browser late-fetch cleanup: after delayed fetch resolved, zero image/video elements and two Blob URLs created/two revoked; current v2 breakfast response displayed. These are coordinator-owned runtime observations, not independent browser actions by this reviewer.

Independently reviewed `semantic-expectations.json`, `live-observations.json`, `live-browser.txt`, `live-v1-v2-revoked.png`, `live-remaining-bound.json`, and both `http-identity-*.json` files. The three planned live guest turns meet L3-AC6: source A version 3/generation 4 answered `07:00-10:00`; trusted refresh to version 4/generation 5 answered `08:00-11:00` without reusing old hours; known revoke at generation 6 answered only `Breakfast hours need confirmation.` with empty evidence/media. Same browser/session was retained, and browser accessibility evidence shows both old answers marked stale. Duplicate wording in the v2 answer adds no unsupported claim and is not an AC blocker.

The live evidence records `grok-4-1-fast-reasoning`, three guest turns, six provider calls, zero paid retries. The saved limiter correction preserves the remaining one-turn/two-call bound after a cached replay was incorrectly counted as a guest turn; that cached replay made zero provider calls. Provider-reported usage: input 3544, output 142, total 5448 tokens; monetary cost unknown. These counts describe recorded runtime calls, not reviewer-issued live calls.

Actual HTTP identity observations also establish positive identical replay, authenticated media `200` (4899 bytes), missing authorization `401`, wrong session `403`, then post-refresh replay `409 stale_source`, old media `404`, and freshness `200`/stale. No remaining scoped AC blocker was identified from the combined source, independent PG/API, local-check, browser and bounded live evidence. Synthetic sources do not establish real operator/hotel acceptance or parent-story completion. No deployment, live model call, manual CI action, push or merge was performed by this reviewer.
