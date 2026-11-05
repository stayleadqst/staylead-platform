# B09 — bounded security pilot execution

## Authority and baseline — 2026-10-28

Hieu authorized: “Cho phép thực thi pilot #30 theo kế hoạch đã pin, gồm commit/push/PR/merge sau local validation và Q review. Bắt đầu ngay, dừng sau một story; chưa bật tự động toàn backlog hoặc chạy live inference mới.”

Scope is exactly [#30 B09](https://github.com/stayleadqst/staylead-platform/issues/30), all B09-AC1–3. The reviewed preparation package is candidate `23a966343195081e86242be2f4b4c2a496eac2b6aa470f05d0d4fa260cc6aace` in workspace `process/autonomous-agile-v2.0-staylead`. Its earlier pending-implementation notes are superseded by this direct approval; its AC, exclusions and limits remain.

- Verified remote integration: `sprint-5-canonical-brief@d304238a1cb2b427650e03a2de81af92aa6ae255`.
- Actual owner branch: `pilot-b09-security`, created from that exact local commit after clean-checkout, remote-ref and open-PR checks. Its initial tree equals accepted S8 `ea15ea7`.
- Existing PR83/PR89 are outside this delivery; do not merge, close or retarget them. Never substitute `main` or edit the completed S8 owner branch.
- Full M1–M6 architecture and four canonical engineering documents apply. No new production dispatcher, LLM calls, runtime multi-agent system, identity provider, retention/delete policy or business scope.
- D4-B09 preserves versioned token/session/DB binding, 24h token TTL and existing request settings; it does not approve data retention or a hard generation/billing cap.
- S7/S8 remain accepted. Their inference allowances are closed and cannot be reused. Two synthetic properties and controlled malicious provider outputs test server authority, not real-model resistance or real-hotel approval.
- No deployment, resource purchase, external notification, credentials/shared infrastructure changes, manual CI/rerun, workflow/protection changes or required-check bypass. Stop after this story.

## Actual team and file leases

| Work | Owner / model / effort | Scope / lease | Dependency / evidence |
|---|---|---|---|
| Contracts, integration, local resources, publication | C `/root`; actual runtime model/effort unavailable | This execution doc, `AGENTS.md`, `docs/product/B09_ACCEPTANCE.md`, `docs/product/evidence/b09/**`, workspace validation/checkpoint | Full scoped AC, relevant local gates and independent review before delivery |
| Test implementation and reproduced fixes | B `/root/b_consumer`, `gpt-6-luna/high` | `tests/contracts/test_b09_security_contracts.py`, `tests/integration/test_b09_security_api.py`, `tests/e2e/hospitality/b09-security.mjs`, new `tests/b09*` and `tests/e2e/hospitality/b09*` helpers | P1 independent matrix; focused checks early. Product file lease only after concrete reproducer and C assignment |
| Independent expectations and candidate review | Fresh Q `/root/q_b09`, `gpt-6.1-sol/high` | Read-only by behavior; no candidate edits or product model calls | P1 matrix frozen before test results. P4 follows immutable candidate handoff; no enforced per-agent OS read-only sandbox claimed |

Default active team C+B; Q works on independent expectations then fixed-candidate review. Maximum four concurrent agents including C; no reporting-only agent, no silent model fallback. Actual agent-token metrics are unavailable unless runtime supplies them.

## Contracts and verification

P1 expectations are recorded in [independent expectations](../product/evidence/b09/independent-expectations.json). Full original AC remain on #30. Required observations include direct API and real local PostgreSQL state, provider/capability counts, actual browser positives/refusals and relevant negative side effects. Invalid prepared actions must not dispatch capabilities; invalid answer after a valid committed edit may retain only that authorized delta/receipt and must report partial failure truthfully.

The actual execution boundary is entrypoint → `guest_chat.send_message` → orchestrator/schema/domain validators → server-owned capability branches. An empty `platform/conversation/tool_execution` package is not a dispatcher or coverage evidence. Test-only provider injection uses the existing composition seam and must never enable live providers or production bypasses.

| Phase | Owner / model / effort | Gate |
|---|---|---|
| P0/P1 baseline, leases and independent expected cases | C runtime unavailable; Q `gpt-6.1-sol/high` | Scope/base/dirty/PR verified; expected cases frozen before acceptance |
| P2 implement and reproduce | B `gpt-6-luna/high` | Focused contracts + isolated PG; defects require reproduced behavior and precise lease |
| P3 integrate and validate | B `gpt-6-luna/high`; C runtime unavailable | Actual API/PG/browser; relevant pytest, Ruff, compile, web contracts/lint/typecheck/build, whitespace |
| P4 review and affected repair | Q `gpt-6.1-sol/high`; repairs B `gpt-6-luna/high` | Candidate-bound full AC1–3, no actionable acceptance finding; recheck only changed/affected evidence |
| P5 deliver and stop | C runtime unavailable | Commit/push/PR/merge own owner/base after gates/review; truthful issue/evidence status; no second story |

Forecast inherited from readiness: 12–20 active agent-hours total, uncalibrated, not a deadline or human-days; task tables do not add a second budget. No new numeric token/cost/repair budget is invented. Preserve failure/operation history and reassess repeated failures; unknown writes require reconciliation before any retry. Record actual metrics or `unavailable`, never unmeasured savings.

## Local resources and checkpoint

C owns the private local PostgreSQL cluster under workspace `validation/b09-20261028/pgdata`, loopback port55430 and socket directory `/private/tmp/staylead-b09-pg-20261028`, database `staylead_b09_test`. It is separate from prior sprint databases and shared services. Integration tests run serially against this binding; do not reset it while browser/other tests use it. API18530/web13530 are proposed local ports; startup is recorded when it actually happens.

Initial sandbox `initdb` failed before creating a usable cluster because shared-memory IPC was denied; the allowed isolated setup succeeded with scoped execution outside that sandbox and explicit UTF-8. This is an environment setup failure, not a product regression or inference retry. C stops only resources created for this pilot after verification.

Workspace checkpoint: `validation/b09-20261028/checkpoint.json`; it records current candidate, dirty files, ownership, resources, commands, evidence and next action. A checkpoint is not a scheduler, restart recovery, hard-deadline supervisor or proof of unattended automation. None is installed by this pilot.

## P4 evidenced repair — 2026-10-28

Initial Q verdict is **NO_FULL_AC_PASS**, candidate `1e1d507633b26ef3c739e438ba3a18ec36879477b1049fafaf9bee49ac3115e1`; report in `docs/product/evidence/b09/review-p4-initial.json`. Existing quote membership derives its purported authorization from the proposal itself. B reproduced this through actual API/PG: after legitimate hard-needs commit, an informational question causes malicious prepared clear/empty-list replacements to remove room access, guide access and allergy needs, advancing M2. No product edits preceded the reproducer.

Repair lease for B: `domains/hospitality/schemas/guest_brief.py`, `composition/dependencies/guest_chat.py`, `entrypoints/app.py`, new generic `platform/guest_context/sessions/brief_confirmation.py` (backend paths relative to API package), and web `shared/api/client.ts`, `shared/chat/GuestChat.tsx`. Existing B09 tests/helpers remain leased. No database migration, new model call or generic dispatcher is approved by this lease. Exact-delta, session/property/version/expiry-bound confirmation must precede unsafe M2 effects; typed domain meaning remains in Hospitality. Q confirmed that hard-relaxation-only is insufficient: all actual chat/model-proposed M2 data/pending changes require exact-delta trusted confirmation. Reads, noops and identical replay do not. Do not silently replace semantic authorization with natural-language keyword checks.

Private PG restarted for this reproducer; API/web remain stopped. Preserve prior failures and passing evidence. Only affected gates and independent Q finding review are required after repair; no repeated full S7/S8 acceptance. Actual token metrics remain unavailable.

Additional B lease: `infrastructure/persistence/store.py` only for atomic scoped completion of a reserved confirmation response without transcript/session-version effects; existing completion helper always appends messages. No migration or other storage changes. Reuse request idempotency and brief CAS. Original challenge request remains immutable; confirmation has its own explicit request ID. Preserve original source provenance and existing answer-only receipt continuation so M4/M5 consumers run after confirmed commit without a second preparation call.

## Sprint 9 tracking correction — 2026-10-28

C omitted the sprint container while starting the authorized process pilot. After Hieu challenged that omission, C created [Sprint 9 — Pilot quy trình thực thi B09](https://github.com/stayleadqst/staylead-platform/milestone/9) through authenticated GitHub UI (connector has no milestone-create capability), assigned only existing #30 through the connector, added T0–T5 goal/owner/dependency/status/gates/exit table to #30, removed stale `status:draft`, and verified milestone UI contains exactly one Open issue #30. No additional story or changed execution/live-inference permission. This tracking was created after implementation began, not retroactively represented as an earlier artifact. Sprint remains In Progress with P1 repair pending; no full PASS or Done claim.

Further precise B repair leases: web `app/api/guest/[...path]/route.ts` only confirmation allowlist/body binding; `.env.example` only contract2; `composition/domain_registry.ts`, `composition/GuestChatExperience.tsx`, `composition/registration.tsx` only generic formatter registration/types; Hospitality `registration/brief-format.ts`, `registration/index.tsx` for readable review and contract2; `apps/web/tests/api-client.test.mjs`, `apps/web/tests/guest-brief-format.test.mjs`; `tests/integration/test_sprint5_consumer_postgres.py`, `test_sprint7_room_advice_postgres.py`, `test_sprint8_operator_api.py` only affected edit-confirmation setup with downstream assertions preserved. Contract changes require version2 rather than silently accepting legacy client1.

Lease deviation observed: B edited `apps/web/src/app/globals.css` and `tests/integration/test_api_skeleton.py` before obtaining their exact leases. C identified it, granted only confirmation-card styling and contract-version expectation changes, and reminded B to request subsequent paths first. There was no other editor on these files or unrelated work to overwrite. This supervised correction does not prove automated/enforced lease fencing. Cancel remains UI discard with no automatic continuation; no server token revocation/rollback gate was added, as Q clarified against original AC.

## Resumed Sprint 9 execution — 2026-10-28

Hieu explicitly resumed checkpoint repair, local validation, independent review and authorized push/merge; no new live inference. C `/root` owns integration/evidence/resources/delivery (actual model/effort unavailable); resumed builder `/root/b09_repair` is `gpt-6-luna/high` with the existing exact product/test leases. No former agent remains active in this chat. Fresh independent Q starts against the fixed candidate. B owns serial `staylead_b09_test` database checks; C owns browser DB/services and root verification after handoff. The existing T0–T5 plan remains: finish canonical signed mutation/UUID repair, affected API/PG/UI checks, full scoped independent review, then publish/merge only `pilot-b09-security` into `sprint-5-canonical-brief` and stop. Initial passing evidence and P1 failure remain historical and must not be represented as fixed-candidate PASS.

Resumed affected-test lease: `tests/integration/test_sprint6_language_consumer_postgres.py` also consumes model-proposed M2 edits. B may add explicit confirmation setup while preserving language, receipt, freshness and replay assertions; these are affected regressions, not new story scope. Existing isolated PG role was reconciled as `staylead_b09`; failed postgres/ccvn connection attempts made no product or DB changes.

## Resumed review and actual-browser corrections

Canonical signed-mutation/child-ID and selected-fact continuity repairs passed affected API/PG checks. Actual Uvicorn/uvloop browser confirmation initially returned503 before reservation because event-loop and monotonic clocks used different epochs; separate clock-domain deadlines fixed it without increasing limits. Final production-browser confirmation/cancel, FAQ/refusal and HTML-refusal then passed, with private PostgreSQL side effects independently observed. Failures/artifacts remain local. Fresh Q `/root/q_b09_final`, `gpt-6.1-sol/high`, verified the frozen source manifest and original full AC/DoD. Q reproduced an additional P2 same-ID retry500 after canceled-before-commit apply/no receipt; see `evidence/b09/review-p4-recovery.json`. B retains exact existing backend/UI/test leases for mapping positively reconciled no-effect versus unknown outcome and testing explicit retry request identity. C remains sole browser executor. Original review is not represented as final PASS; final pin/delta review follows affected verification.

## Final technical acceptance and delivery handoff

Fresh Q PASS full scoped AC1–3/DoD on `891515af41444208931c671cad0b54dbaa57f18f5cd6e4296fe19c5965f79ce0`/282, no open actionable findings. Initial P1, actual-browser clock-domain defect and final P2 cancellation-replay recovery are closed by reproduced fixes and affected verification; see independent-final-review.json/final-observations.json. Web45/static/build and actual confirm/cancel/FAQ/refusal/HTML/recovery evidence PASS; zero live inference added. All source/test leases are now closed. C owns documentation, stopping only pilot resources and authorized owner/base commit/push/PR/merge. No other story, deployment, workflow/check bypass or further inference.
