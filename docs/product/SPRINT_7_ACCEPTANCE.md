# Sprint 7 — execution report

2026-10-27 (Asia/Ho_Chi_Minh). **BLOCKED: sprint goal and full DoD are not achieved.**

[#39](https://github.com/stayleadqst/staylead-platform/issues/39), [#28](https://github.com/stayleadqst/staylead-platform/issues/28) and [#97](https://github.com/stayleadqst/staylead-platform/issues/97) remain open with `status:blocked`. No scoped story is marked Done. New [S7-F1 #98](https://github.com/stayleadqst/staylead-platform/issues/98) is in product backlog U1, epic E3/P0, related to E2, for a later sprint/explicit model allowance.

## Work, ownership and verification

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
| --- | --- | --- | --- | --- |
| M1 projection, M2 requirements, mixed FAQ, M4 checks/math | A / gpt-6-luna / high | Implemented; offline remediation reviewed | Party/bed/guardian/age/access, known/unknown fees, hard budget lower bounds, rate windows and source controls; native/Pydantic authorization parity | Actual-model behavior on corrected protocol is unverified; #98 |
| Result/selection persistence, API, registered domain UI, booking config | B / gpt-6-luna / high | Implemented and independently reviewed | Exact-result currentness, scoped/idempotent selection, edit/replay, pure language reuse, trusted link/fallback and UI stale propagation | C01 actual journey and B07 actual AI intent remain unverified; #98 |
| Bounded runtime and browser driver | H / gpt-6-luna / high | Offline verified; actual run halted | 12 harness tests, persistent prelaunch counters, flock, source/case/oracle pins, production-browser fake-provider proof | Do not reset or resume failed namespace |
| Independent code/consumer/actual review | Q / gpt-6.1-sol / high | Offline code-review PASS; actual acceptance FAIL | 235-file hashes, source-derived probes, original output, readonly PG and protocol counterfactuals | Independent real-observation review after authorized future batch |
| Integration, backlog and delivery | Coordinator / current session; exact model/effort metadata unavailable | Local gates complete; draft delivery being prepared | 216 backend +42 PostgreSQL tests, frontend40, lint/typecheck/build/compile and reviewed evidence | Keep #39/#28/#97 Blocked; no merge/deploy claim |

One mutable-file owner at a time. Shared platform and guest shell use registered domain ports/views; no Hospitality business imports in platform. M1–M6 boundaries remain applicable.

## Candidates and evidence

- Branch `sprint-7-room-advisory`; accepted baseline `a46a63eb4b589b8518f9477ebd66e81d89a0f054`. Delivery target is a draft PR to `sprint-5-canonical-brief`; no main or historical baseline PR merge.
- Actual failed candidate: [235-file pin](evidence/sprint-7/actual-failed-candidate.json), fingerprint `9a4833b8b69108fb3fdfbf7f8ca6e8f72e5d6c305036c71f7597d1004afc1512`.
- Offline corrected candidate: [235-file pin](evidence/sprint-7/offline-remediation-candidate.json), fingerprint `396cc7f3dec2fb619961ce9a83e8549bdca2485b0da555df4eaf41b5ed47b8f5`. **No actual-model PASS for this candidate.**
- [Source delta](evidence/sprint-7/failed-candidate-to-remediation.patch.json) contains a lossless JSON-wrapped unified diff for reconstruction of the failed source from the corrected source; the original local snapshot and captures are retained.
- [Independent source oracle](evidence/sprint-7/independent-expected-facts.json), [nine-turn matrix](evidence/sprint-7/live-cases.json), [integrated review](evidence/sprint-7/q-review-integrated.json), [supplement](evidence/sprint-7/q-review-integrated-supplement.json), [final offline review](evidence/sprint-7/q-review-offline-remediation-final.json).

Synthetic technical pilot only: three authored hotels, nine room types/rates. No real hotel approval, live availability, booking, payment or deployment is established.

## Local gates and independent work completed

| Gate / observation | Result | Evidence / limit |
| --- | --- | --- |
| Backend contracts, architecture, API skeleton | **216 passed** | [Log](evidence/sprint-7/backend-tests.log) |
| Relevant PostgreSQL suites S1/S3/S4/S5/S6/S7 | **42 passed** | [Log](evidence/sprint-7/postgres-tests.log); fake provider and dedicated test DB |
| Final authorization/clarification focused tests | **126 passed** | Includes exact original-shape rejection, corrected initial-details path, eleven/clear targets and clarification regression |
| Canonical backend Ruff and Python compile | **PASS** | [Ruff log](evidence/sprint-7/backend-ruff.log); old17 I001 test imports cleaned; no application change from formatting |
| Frontend contracts/lint/typecheck/production build | **40 passed / PASS** | Frozen web source unchanged by backend-only remediation |
| Production browser with fake model | **PASS** | [Sanitized summary](evidence/sprint-7/offline-browser-summary.json); real API/domain/PG |
| UI selection/edit/currentness | Passed | 3 nights5.4m VND →4 nights7.2m; old card stale+disabled; new card current+selectable; old selection HTTP409 |
| Mobile and booking boundary | Passed | 390px no overflow; trusted synthetic HTTPS link, `_blank`, `noopener noreferrer`, `no-referrer`; missing/unsafe config tested |

The single existing Starlette/httpx deprecation warning is recorded in test logs. Default tests/build/startup make zero model calls. [Gate summary](evidence/sprint-7/local-gates-summary.json). Valid frontend/browser evidence was reused because remediation changes only backend protocol and tests.

## Actual acceptance outcome and diagnosis

**One guest turn attempted; one Codex request; zero successful turns; no call2.** HTTP502 `invalid_model_output`. Reported usage:10979 input tokens,396 output tokens; total-token report and monetary/agent usage unavailable. Provider7.42s and HTTP7.58s were within25s/45s; output below700. [Events](evidence/sprint-7/runtime-events.jsonl), [halted counters](evidence/sprint-7/halted-run-state.json), [Q diagnosis](evidence/sprint-7/q-review-actual.json), [readonly DB proof](evidence/sprint-7/q-review-actual-db-readonly.json).

The model emitted granular/comma-packed room-requirement authorization paths although the then-current server required the aggregate `room_requirements` target. It omitted required `guest_edit` while proposing three operations and inferred `max_rooms=1` from solo travel. Validation rejected the response before M2 mutation. Readonly PostgreSQL confirmed session state0 and zero saved briefs, receipts, messages, results, selections or language rows.

The initial hypothesis that max3 targets made any budget serialization impossible was disproved: the previous aggregate grammar needed one target. The source/semantic protocol was underspecified. [Independent counterfactuals](evidence/sprint-7/q-review-actual-protocol-results.json) distinguish these causes.

Offline repair now uses exact granular requirement targets with native/Pydantic parity (up to11), keeps the aggregate target for clarification only, requires `guest_edit` whenever a patch is proposed, and explicitly forbids inferred room limits. Original malformed output still fails closed; the corrected counterfactual validates. Q found and the builder fixed the clarification regression introduced by the whitelist. [Initial offline review](evidence/sprint-7/q-review-offline-remediation-initial.json), [final review](evidence/sprint-7/q-review-offline-remediation-final.json). These are offline proofs, not a replacement actual run.

## Per-story acceptance and remaining work

| Story | Completed implementation / offline evidence | Remaining blocker | State |
| --- | --- | --- | --- |
| #39 C01 | Requirements, current scoped facts, deterministic checks/math, explanations, persisted selection/edit/replay and registered UI | Actual website/API/model journey and full C01-AC8/DoD on corrected protocol; full nine-turn sample not reached | **Blocked** |
| #28 B07 | Trusted config, safe navigation, contact fallback, disclosures and actual offline UI behavior; strong AC2/3 technical evidence | B07-AC1 requires actual AI booking-intent/language proof; fake intent injection does not establish it | **Blocked** |
| #97 Sprint7 coordination | Owners/contracts/oracle, local gates, independent review/fix, evidence and backlog follow-up | Sprint goal and actual acceptance incomplete | **Blocked** |
| #98 S7-F1 | New follow-up contains problem, impact, attempts, evidence, AC, epic, priority and affected links; added to U1 | Future sprint allocation and explicit bounded model authorization, then actual verification/fix | **Draft / future backlog** |

No AC was waived, no story was split by guest type, and no broader parent/epic/milestone was closed. Offline independent work continued after the failed batch. Code is reviewable but full story completion is not claimed.

## Bounds, bootstrap and delivery state

The current execution request authorized the planned single fresh9-turn/max18-request batch as a scope interpretation; it was not authority from backlog creation or a separate numeric approval reply. Existing caps stayed2calls/turn,25s/provider,45s/turn and700output (post-usage guard, not a billing hard cap). The run stopped at its first blocking failure. Seventeen slots were not used; they do not authorize resetting/resuming this namespace or opening another batch. Sprint6's115 requests and closed allowances remain unchanged.

Initial auto-review rejected runtime start for suspected sensitive egress; a read-only check proved a fresh empty guest DB and all three hotels synthetic, after which the same command was allowed. No workaround was used. A missing headless-browser dependency also failed before launch at0turns/0requests; exact compatible Chromium was installed, the original failure preserved, and the unchanged candidate retried before any inference. [Synthetic-data proof](evidence/sprint-7/synthetic-data-verification.json), [zero-consumption bootstrap proof](evidence/sprint-7/zero-consumption-bootstrap.json).

Actual runtime/web and all Sprint7 mock HTTP services are stopped. Private configs, raw captures and screenshots remain local0600; none are in Git. No new paid resources, Grok, manual GitHub CI/rerun, workflow/protection changes, deployment or external booking/send. Automatic CI may run on publication; no CI PASS is claimed. Source/evidence delivery is prepared for an **unmerged draft PR** while actual AC remains blocked.
