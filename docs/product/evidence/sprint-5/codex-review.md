# Sprint 5 Codex replacement — independent review

**Final review: PASS for affected code, original four-turn real Codex semantics and local Sprint 5 acceptance.** No remaining blocking finding in the reviewed scope. The coordinator still owns final evidence/status publication and authorized branch delivery. This report does not establish Grok recovery, production readiness or authorize additional calls. Preflight observations below are retained as history; the final section records actual acceptance.

Reviewer `/root/sprint5_codex_review` read `AGENTS.md`, working rules, the M1–M6 architecture, execution/focus guides, the provider amendment and the candidate diff against `d41fff456a3321219ee7cab53a02af6bd9045387`. Product, runtime and private configuration were read-only by instruction; this restriction is not technically enforced. The reviewer changed only this review artifact, read no private runtime/authentication data, made no model calls, started no services and performed no Git/GitHub mutations. Unaffected brief/source/storage/CAS/receipt/recovery evidence from `review-findings.md` and `remediation-review.md` is reused.

## Affected implementation

`CodexCLIProvider` remains an infrastructure implementation of the existing neutral generation port. Trusted composition selects it only when explicitly configured and rejects environments other than development/test. The default provider remains disabled. No domain/orchestrator or M1–M6 state path is replaced.

The subprocess uses a private temporary working directory, ephemeral execution, ignored user configuration, read-only sandbox and explicit disabled execution/app/plugin/hook/agent/browser capabilities. Request instructions/input travel as one bounded JSON envelope through stdin; argv contains only a fixed instruction and trusted configuration. Installed CLI help independently confirms that piped stdin is appended as a `<stdin>` block when a prompt argument is also provided. The child environment allowlist excludes application/Azure credentials. Authentication remains the existing local ChatGPT login; the custom `staylead_codex` provider uses native CLI routing/authentication with `name="OpenAI"`, `requires_openai_auth=true`, Responses wire format and zero configured request/stream retries. No API key export or application call to an internal endpoint is added.

The adapter bounds input, event/error streams and final response bytes, requires a JSON object plus a successful tool-free `turn.completed`, rejects failed/tool events and reported output usage above the requested cap, and safely maps errors. Timeout/cancellation terminates the process group and reaps the parent; the offline contracts include descendants surviving the initial parent exit. The configured requested profile is `gpt-6-luna`/`low`; `GenerationResult.model=None` correctly avoids claiming a served-model identity absent from CLI telemetry.

**Native pre-generation output-token limiting is unsupported in this invocation and explicitly reported false.** The byte bounds and post-generation usage check do not prevent generation/billing beyond a token budget. Unknown usage remains unknown. This limitation is preserved in the approved provider amendment rather than hidden behind the existing `max_output_tokens` contract.

The acceptance harness binds through `build_provider(settings)`, reserves persisted counters before invoking, caps the run at eight Codex requests/four new semantic turns/two calls per turn, preserves prior Grok attempts at eight and keeps receipt-linked answer resumes separately observable. Counters use a process-local lock and atomic file replacement; this is suitable for the intended single acceptance runtime, not a distributed quota service. Sanitized telemetry records requested profile, shapes/hashes, call timing/outcomes and reported usage; startup makes no inference request. Original semantic expectations are unchanged.

## Independently reproduced checks

- Final adapter contracts: **9 passed**; no model invocation. They exercise opt-in/default/production binding, exact subprocess profile/stdin/environment, truthful model/usage fields, reported token-cap rejection, successful/tool-free completion, timeout/cancellation and descendant-group cleanup.
- Configured Ruff on adapter, its contracts and acceptance harness: **passed**. All affected Python sources compiled in memory.
- Isolated harness probes with temporary state: missing state refused; reservations 1–8 persisted and ninth refused after reload; semantic turns 1–4 persisted and fifth refused; separate resume preserved four-turn count; third call in one turn refused before another reservation; prior Grok count stayed eight; unsafe IDs and sample secret fields were rejected/redacted. **Zero real provider requests and zero services.** Coordinator-owned state/events were unchanged by these probes.
- Inspected `codex-config-preflight.json`: local CLI profile/features probe exit zero, all requested features reported false and zero model requests. This is configuration evidence, not inference-readiness proof. `codex-harness-check.json` records a separate offline middleware response/redaction probe.
- Inspected coordinator `codex-backend-tests.log`: 110 backend tests passed before the final provider-alias adjustment; subsequent targeted adapter checks cover that adjustment. This is reported builder evidence, distinct from the independent nine-test run above.

## Candidate pin and remaining acceptance

| File | SHA-256 at code preflight |
| --- | --- |
| `infrastructure/codex_provider.py` | `c7b219cfebaf6a8f9a54e7614c8bcf46e3c68e0bd0766034c021ea43d8108615` |
| `composition/configuration/settings.py` | `c1bfff558c279eaff6097bbfc8e828fd64d8345e0fe72f9cbe3be74e43bee5b5` |
| `composition/dependencies/guest_chat.py` | `4ad67c12a3cc740e5b62b7f3bfd5bbb0d7038d1998a0c45f8a3f1c7c8ebc9369` |
| `tests/contracts/test_codex_cli_provider.py` | `6d2b27732dad295c85a3b33a5f34c16b59b62f5628f573ff8a13fa7624b02eb5` |
| `codex_acceptance_runtime.py` | `7c212edbf3ead43fe3a35ca9d692036ea2931d78c25cb9001c681df763100300` |
| `semantic-expectations.json` | `9eaac0e1eea0762063e4a44e3865b701d54fc4c298dae4f2d0feec51cfb801bd` |

The first three paths are under `apps/api/src/staylead_platform/`; the harness/expectations paths are in this evidence directory. At inspection, Codex state was 0/8 requests, 0/4 semantic turns and zero resumes, with prior Grok eight frozen. This is a preflight observation, not final run usage.

Final review requires the original four sequential questions through production UI → API → actual Codex JSON → canonical PostgreSQL brief and rendered answer: initial dates/adults plus grounded breakfast; add one stable child with unknown age and targeted clarification; update that child's age/checkout without duplication; remove it while preserving dates/adults and answering breakfast despite explicit no-add negation. Candidate binding, latency, failures, usage availability and counters must match the actual run. Prior offline recovery/source evidence remains valid for unchanged code. Keep final semantic/DoD status pending until those observations are reviewed. No main/PR83 merge, deployment or parent/epic/milestone closure is authorized by this report.

## Final actual consumer evidence and requirements disposition

The reviewer independently verified all **192 current source/test/fixture hashes**, both before and after the run, and recomputed the sorted compact JSON aggregate: **`511babeb7c0a3312ab24350d18381a087eaf8d4ec3153ba794b65bc946d2b5b4`**. It exactly matches `codex-candidate-manifest.json`, `codex-live-boundary.json` and `codex-observations.json`. Harness and semantic-expectations hashes match the table above. The final Grok state SHA-256 still matches the frozen boundary. No product change between this pin and the observed run is evidenced.

Inspected actual `codex-runtime-events.jsonl`, final persisted `codex-run-state.json`, `codex-observations.json`, `codex-db-observation.json` and the four browser state screenshots plus `codex-final-answer.jpg`, `codex-age-clarification.jpg` and `codex-correction-answer.jpg`. Original question wording and rendered clarification/correction/final answer match the predeclared expectations; additional viewport captures made no inference request. There are eight provider starts, eight successful completions, no provider failure/cancellation and four message HTTP200 completions, each with two calls. Runtime reports installed `codex-cli 0.153.4`; all successful trace results use `provider="codex_cli"`, requested deployment `gpt-6-luna` and `model=null`. This is a real backend CLI response run; the actual served model remains unreported.

| Original semantic turn | Independently observed result |
| --- | --- |
| Capture dates/adults plus breakfast | PASS: briefv1 is Dec10→13 2026, three code-computed nights, two adults/no children. Breakfast06:30–09:30 at Bến Gió/tầng1 matches approved authored fact040 and its conditions. Hotel citation and canonical guest refs remain separate. |
| Add child without age | PASS: briefv2 retains dates/adults and adds exactly one child `3bc810f7-0c29-4402-8c1f-53d22383427b`, age null, with that age pending. Actual answer asks “Bé bao nhiêu tuổi?” without inventing an age; supplementary child-policy claims match approved facts018/064/066. Receipt `partial_success` denotes the still-missing field; the answer itself completed. |
| Supply age/correct checkout | PASS: briefv3 changes checkout to Dec14/nights4 and updates the same child to age7. Check-in/adults remain unchanged, no duplicate child exists, pending flags clear, and guest claims cite canonical refs without hotel evidence. |
| Remove child plus negated add/FAQ | PASS: briefv4 removes that exact age7 child; zero children remain, Dec10→14/four nights/two adults are preserved. The answer includes supported breakfast fact040 and saved-stay claims. Final lower-viewport screenshot shows the exact no-add-negation question, completed answer and current summary. |

The PostgreSQL artifact was produced by a separately reviewed read-only snapshot command, not by the reviewer. Its actual final session is `2ae411dd-30ae-4eec-a37a-3c8effd8141d`/`HTL-CITY01`, statev4/briefv4, with the expected final dates/party and no pending fields. All four stored request IDs, durable utterance IDs, source field refs, applied deltas, before/after versions and completed answer versions exactly match HTTP receipts. Thus this evidence goes beyond transient response/UI state. The helper's first sandbox network probe failed before a transaction; the successful authorized local snapshot is the delivered proof. No database mutation is used to satisfy semantics.

The coordinator initially compared removal IDs against strings although the public delta contains removed member objects. The reviewer flagged the false turn4/aggregate failure, independently checked `applied_delta.party.children_removed[0].member_id` and prior age against the actual events/PG receipt, and verified the corrected observation now reports PASS with an explicit correction note. No product code, expected semantics or additional model call changed for this correction.

Reported successful usage sums to **62,798 input tokens / 988 output tokens**. Provider total tokens and monetary billing are unavailable; no total or cost is invented. Each output is below the requested700-token post-check. Provider calls took **4.257–5.071seconds**; complete turns took **9.015, 9.361, 9.760 and 8.749seconds**, within25s/45s limits. Final counters are **8/8 Codex requests, 4/4 semantic turns, zero resumes**, plus the unchanged prior Grok eight. No remaining inference attempt is available in this batch. Native output-token limiting remains unsupported, and these observations do not establish a hard billing cap.

| Requirement | Final disposition |
| --- | --- |
| R2-AC1 diagnosis/uncertainty | PASS: historical failures preserved; original Grok timeout cause remains unknown; actual Codex timing/usage/identifiers are recorded without a Grok-recovery or served-model claim. |
| R2-AC2 implementation and bounds | PASS under explicit user-authorized provider amendment: local/test opt-in adapter, native login, preserved neutral contracts/M1–M6 validators and offline/scope/source/recovery guards; no production/shared-account deployment. |
| R2-AC3 original four real-provider semantics | PASS on the same pinned candidate through production browser/API, actual Codex responses and PostgreSQL receipts/brief. |
| R2-AC4 recovery/replay/unknown completion | PASS by unchanged prior independently reviewed consumer/PG/browser evidence plus affected offline checks; this success run made no new failure-injection/resume inference. |
| R2-AC5 local gates/review/binding | PASS for implementation/local verification/fresh independent review and bound acceptance evidence. Coordinator owns final report/status publication and authorized branch delivery; publication is not claimed here. |
| #84 canonical brief | Local AC PASS: actual capture, clarification, stable-ID correction and removal now supplement prior ambiguity/scope/persistence/CAS evidence. |
| #85 safe edits/recovery | Local AC PASS: actual exact deltas/atomic durable refs/receipts supplement prior rollback, concurrency, idempotency, partial/replay/resume evidence. |
| #86 mixed FAQ/web | Local AC PASS: actual grounded mixed turns and current UI summary supplement unchanged authority, desktop/mobile, freshness/in-flight/replay evidence. |
| #87 integration | Local technical acceptance PASS; final evidence/status publication and branch delivery remain coordinator-owned. |

**No remaining blocking code or semantic finding.** The prior real-provider gate is satisfied by the explicitly authorized Codex replacement, not by reclassifying any failed Grok run. This acceptance remains synthetic/authored-hotel evidence and local/development operation; it does not establish real hotel/operator acceptance, production service suitability, full parent/epic/milestone completion or deployment. No main/PR83 merge, deployment, paid-resource creation or parent/epic/milestone closure is authorized by this review.
