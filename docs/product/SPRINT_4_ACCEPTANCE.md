# Sprint 4 — current source lifecycle and FAQ/media freshness

**Outcome:** scoped stories S4-L1 #79, S4-L2 #80, S4-L3 #81 and coordination #82 meet their AC/DoD. No unresolved scoped blocker; no follow-on backlog story was needed. This is local synthetic-source acceptance, reviewed independently. Delivery branch: `sprint-4-source-lifecycle`; delivery revision is the commit containing this report. No main merge or deployment is included; parents, epics and milestone remain open.

Baseline `1e020d0e344dde898c9c37aef7568cffe630a471`. Final source/test/fixture fingerprint **`a358cfef3ccfbd354fcf2b1ad6ea71ef79db7a413f9b20c06ac78d3225f2b7a4`**, 192 files, unchanged after final review/live acceptance. [Manifest](evidence/sprint-4/candidate-manifest.json), [independent review](evidence/sprint-4/review-findings.md), [independent probe results](evidence/sprint-4/review-probes/results.json). Documentation/evidence are outside this product fingerprint. Four import-only lint fixes followed the 68-test run; no product behavior changed afterward.

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
| --- | --- | --- | --- | --- |
| #79 refresh/delete | A `/root/lifecycle`, gpt-6-luna/high | Implemented; final fingerprint above | Real PostgreSQL, injected rollback, CAS/retry, A/B isolation and receipt replay | None |
| #80 revoke/expiry | A, gpt-6-luna/high | Implemented; same candidate | Controlled UTC clock, PNG/MP4/VTT denial, failure policy | None |
| #81 consumer | B `/root/consumer`, gpt-6-luna/high | Implemented; same candidate | Actual API/production browser, late fetch/Blob cleanup, three real-Grok turns | None |
| #82 integration/handoff | Coordinator, exact model/effort unavailable | Locally verified and documented | AC map, local gates and review; branch delivery recorded on GitHub | No scoped blocker |
| Independent review | Fresh Q `/root/reviewer`, gpt-6.1-sol/high | PASS on same fingerprint | Independent PostgreSQL/upgrade probes and semantic evidence review; no product edits | No unresolved reproduced finding |

W0 fixed typed contracts and file leases before parallel implementation. A owned neutral contracts, schema/migration, persistence/repositories/store completion, validation/CLI and producer tests. B owned API/composition, web and consumer tests. Coordinator owned integration, acceptance runtime, evidence and delivery. No shared-file editor collision or completion dependency cycle. Review findings returned to the responsible builder for targeted repair. Coding-agent token usage is unavailable.

## Behavior and versions

- Database schema **4**, explicitly migrated from schema 3. Startup/test/build remain offline and do not migrate/import or call a model. Pack schema1 and guest contract1 are preserved.
- Trusted local CLI replaces one selected source snapshot, or revokes/deletes that source. Expected hotel generation plus selected-source version/hash and operation identity protect publication. Hotel config, other sources and other hotels remain scoped. Source-owned omitted facts/media cease eligibility. No public mutation endpoint/operator UI was added.
- First-import receipt stays immutable and separate from active source state. Identical original import reports current lifecycle state without mutation/resurrection. Refresh hashes bind source metadata, facts and verified media content identities.
- FAQ remains M6→M3→M1→M3→M6. Generation serializes completion with lifecycle mutations; current approval/date/source identity is checked at read/replay/commit. History filters obsolete assistant evidence even when IDs are reused. Version-bound media cannot deliver replacement bytes beneath old metadata.
- Existing schema3 synthetic bootstrap data and complete-pack sessions upgrade without reseeding/reset. Trusted provenance is conservatively backfilled; unresolved/unapproved sources fail closed. Existing saved response/history bindings are migrated. Independent upgrade probes preserve 109 legacy facts and session state1, valid replay200 with zero provider calls, then exclude revoked assistant prose.
- Existing media/pack limits remain PNG≤5MiB, MP4≤20MiB, VTT≤256KiB, complete pack≤64MiB and aggregate currently eligible guest facts≤400. Source permission and UTC-inclusive dates apply without grace fallback.

## Quality gates

- Full backend: **68 passed** on dedicated real PostgreSQL18, fake/disabled provider. [Final output](evidence/sprint-4/backend-repaired-final-tests.log). First full run64pass/3fail is preserved, with cause and repair below.
- Web: **26 contract tests passed**, ESLint, typecheck and Next16.4.2 production build passed. [Contracts](evidence/sprint-4/web-final-contracts.log), [consumer checks](evidence/sprint-4/consumer-api-checks.log), [build](evidence/sprint-4/consumer-web-build.log).
- Modified/new Python Ruff, compileall and diff whitespace checks passed. [Lint](evidence/sprint-4/backend-final-lint.log). Existing Starlette/httpx deprecation and Node TypeScript-stripping messages remain warnings.
- Fresh independent review PASS, with zero deltas across all192 manifest hashes. Reviewer ran separate PostgreSQL probes and inspected source, actual browser artifacts and live semantic results. Review was constrained read-only by instruction, not an enforced permission profile.
- Secret scan covers staged files and public build assets; credentials/private DSNs/Bearer tokens are not delivery artifacts. No manual GitHub CI invocation/rerun or CI-wait gate; automatic workflows may run on branch/PR updates. No CI success is asserted.

## AC evidence

| AC | Expected → observed / evidence |
| --- | --- |
| L1-AC1 scoped refresh | A v1→v2 facts/media atomically switch; omissions stop serving; B/config remain unchanged. Foreign B-owned IDs/config changes reject. Builder PG tests, independent atomic probe, [CLI refresh](evidence/sprint-4/lifecycle-refresh-5.json). |
| L1-AC2 failure/retry | Injected interruption after deletes rolls back facts/media/hash/generation/last-success. Same-operation concurrent retries yield applied+noop; changed payload rejects. [Independent probes](evidence/sprint-4/review-probes/results.json), lifecycle PG tests. |
| L1-AC3 CAS/bounds | Concurrent stale CAS rejected; validator limits retained; active400 boundary passes and revoked rows do not consume the cap. Scope/config/ID negatives reject before partial publication. PG tests and independent cap repair probe. |
| L1-AC4 delete | Actual delete makes A facts/media unavailable, preserves B, changes generation; retry no-op. Independent atomic/delete probe. |
| L1-AC5 A/B isolation | Actual scoped retrieval sees changed A, omitted A fact/media absent, B content/version/hash/config unchanged. Builder PG plus CLI receipt observations and independent delete/isolation probe. |
| L1-AC6 first-import replay | After refresh/revoke/delete, identical original receipt returns no-op/current generation/state, never restores old data; differing first import rejects. Controlled expiry replay does not extend date. PG tests, independent delete probe, [refresh replay](evidence/sprint-4/lifecycle-replay-2.json), [revoke replay](evidence/sprint-4/lifecycle-replay-3.json). |
| L2-AC1 known revoke | Revoke advances hotel generation; new retrieval/media/replay deny A; wrong scope/CAS reject, retry idempotent. PG tests, [revoke](evidence/sprint-4/lifecycle-revoke-6.json), HTTP and real-Grok unknown. |
| L2-AC2 time expiry | Controlled clock crosses end UTC date with unchanged generation; fact, PNG/MP4/VTT, freshness and completion checks deny. Completion waiting on hotel lock across expiry rolls back. Lifecycle PG clock/lock tests. |
| L2-AC3 failure policy | Failed refresh leaves approved/unexpired previous snapshot and last-success intact; revoked/expired/deleted state cannot gain permission or an extended expiry. PG failure/clock tests and source review. |
| L2-AC4 states/isolation | Revoked/deleted/expired/refresh-failure metadata remain distinct; all media kinds and facts check eligibility; other source/hotel unchanged. PG tests and independent scoped reads. |
| L3-AC1 in-flight | Snapshot precedes history/retrieval; hotel lock serializes completion with mutation, exact generation and actual source evidence checked, expiry checked again after lock waits. Stale returns deterministic409 without model retry. PG CAS/expiry/commit tests and independent source review. |
| L3-AC2 replay | Current saved replay has identical public payload; after refresh old replay409 stale_source, no recompute; current upgraded legacy/pack replay200 with zero provider calls. [Current HTTP](evidence/sprint-4/http-identity-current.json), [stale HTTP](evidence/sprint-4/http-identity-stale.json), independent upgrade probes. |
| L3-AC3 history | Saved assistant bindings filter obsolete versions/hashes even reused IDs; user/context/session remain intact. Upgrade-revoke probe removes old assistant prose, real same-session v2 uses only new hours. |
| L3-AC4 media binding | Actual authenticated PNG returns4899bytes; missing auth401/wrong session403. Old descriptor after same-ID refresh404; wrong hotel no bytes. PNG/MP4/VTT source/version/hash/digest/approval/expiry checks share the read boundary. HTTP identity artifacts, builder PG and independent probes. |
| L3-AC5 browser | Explicit recheck and before-next-turn mark old answers stale and unmount media. With45s delayed clip read, later DOM has0images/0videos; two Blob URLs created/two revoked, late media does not return. [Refresh screenshot](evidence/sprint-4/browser-refresh-stale.png), runtime events and browser observations. Focus/pageshow/visibility handlers cover existing-view re-entry; no polling/persistent transcript. |
| L3-AC6 semantics | Actual production browser and Grok: sourceA3/gen4 gives07:00-10:00; trusted CLI A4/gen5 gives08:00-11:00; revoke/gen6 gives only unknown, empty evidence/media. Same session; old answers stale. [Live observations](evidence/sprint-4/live-observations.json), [browser proof](evidence/sprint-4/live-v1-v2-revoked.png), independent semantic review. |
| C-AC1 | Actual owners/models/contracts/leases fixed before execution and recorded on #79–#82; bounded parallel A/B start; one writer/file, no completion cycle. |
| C-AC2 | Concrete defects had an owner, retained failure/reproducer and targeted repair/review. No unresolved blocker; no follow-on story needed. |
| C-AC3 | This report links all AC, fixed fingerprint, versions, gates, actual browser/model usage and retained failures. Branch delivery only; parent/epic/milestone obligations preserved. |

## Repairs and retained failures

The initial full backend result64pass/3fail revealed legacy bootstrap facts lacking persisted source metadata; valid answers incorrectly returned409 before positive/replay/deadline behavior. Persisting validated sources and safe schema3 backfill repaired this without dropping freshness guards. Public first response/replay now both omit internal binding/check metadata, preserving idempotent payloads. Final68 tests pass.

Independent review found and verified repairs for: counting revoked physical rows against the active400 cap; datetime serialization during hash backfill; and old saved responses/history lacking lifecycle bindings after upgrade. Earlier failed upgrade databases/probes are preserved in reviewer evidence. Coherent snapshot reads now hold the hotel shared lock across generation/source reads.

Production browser exposed a query URL bug: `?` was encoded into the media path, yielding422. Query/path separation plus a regression test and rebuild repaired it; actual640×360PNG decoded. Initial failure screenshot is retained. The fake acceptance provider initially fell back to an unrelated parking record after revocation; the harness was corrected and that output is not claimed as semantic acceptance.

The live harness counted one deterministic cached replay as a guest HTTP request although it made no model call. After the first two planned model turns consumed4calls, the live process was restarted with only **1 remaining turn / 2 remaining calls**. [Remaining-bound record](evidence/sprint-4/live-remaining-bound.json) preserves this accounting; no paid retry or budget increase occurred. A browser locator wait timed out while the second result completed; rereading the page confirmed success, without resubmission/model retry.

## Model usage and limits

Exactly **3 guest turns / 6 observed provider calls**, `grok-4-1-fast-reasoning`, existing Foundry deployment. Provider-reported **3544 input / 142 output / 5448 total tokens**; total is retained as reported, not recomputed. Monetary cost unknown; coding-agent token usage unavailable. No LLM judge, broad eval dataset or default live call. Lifecycle/freshness/media binding adds **zero model calls**. The bounded live API was stopped after acceptance; the local gateway returned to fake/offline mode.

All sources/media are synthetic/authored. This does not close real hotel/operator approval or full #35/#36, #18/#22, E1/E2 obligations. No M2/planner lifecycle, OCR/ASR/vision, push/polling, persistent transcript, stretch #74, deployment, paid resources or budget increase. Old visible content may remain until revalidation, and already downloaded bytes cannot be recalled.
