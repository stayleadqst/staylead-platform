# Sprint 5 S5-R2 #90 independent remediation review

**Final disposition: PASS for the repaired code and offline mechanics; S5-R2 #90 and Sprint 5 DoD remain BLOCKED because the final four-turn real-model acceptance has not passed.** The preflight sections below retain the review progression; the final section records the reviewed delivery candidate and actual evidence.

Reviewer `/root/sprint5_r2_review` inspected current issue #90, `AGENTS.md`, working rules, architecture and execution guides, the diff against local `94515af`, and original `review-findings.md`/live failure evidence. Product and runtime were read-only by instruction; this capability restriction is not technically enforced. The reviewer owns only this report, made no live calls, read no private runtime/credentials, started no services, and performed no Git/GitHub mutations.

## Affected-code findings

No blocking preflight finding. The adapter changes only `max_tokens` to `max_completion_tokens` with the same `request.max_output_tokens` value. Deployment, endpoint, authentication, messages, JSON response mode, temperature, default 25-second provider timeout and error handling are unchanged. No reasoning setting or retry layer is added. This preserves the provider-neutral contract and M1–M6 boundaries.

[Microsoft's Foundry Grok protocol](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-grok) documents `max_completion_tokens` for Chat Completions as a generated-token bound including reasoning. The corrected key follows that documented protocol. This establishes the wire/bound correction; it does not prove that the incorrect key caused the original timeout. The original provider timeout cause remains unknown until independently supported by further observations.

The live harness now validates an explicitly initialized run ID, prior attempt count 1 and additional-attempt limit 8; it reserves and atomically replaces persisted state before calling the provider. It checks the two-calls-per-turn bound before reserving. Restarting the same single runtime cannot reset the persisted additional count. The thread lock is process-local: the coordinator must retain one live runtime process, as intended by this acceptance harness. It is not a distributed budget service or Azure billing cap.

Diagnostics separate start/completion/failure with latency, shape sizes, requested cap, usage when returned and sanitized identifiers/error codes. No raw request headers, exception text or private config is added. Original failure/evidence files remain preserved, and remediation events use their own file. Unknown provider status/request ID remain absent when the existing adapter does not expose them. Initial read-only model-list success is correctly described as insufficient to prove inference readiness.

## Independently reproduced offline checks

- New adapter wire-contract test: **1 passed**. It verifies the exact completion cap, absence of `max_tokens`, target route, unchanged 25-second timeout, JSON mode, messages and response/request-ID parsing using an in-process fake transport.
- Configured Ruff on adapter, new contract test and harness: **passed**.
- Compiled the three changed Python files in memory: **passed**.
- Isolated harness function probes using temporary state: missing/mismatched state rejected; reservations 1–8 persisted; ninth rejected before call; reloaded state still rejected a ninth; unsafe request-ID strings rejected. No runtime module execution, credential retrieval or provider invocation occurred.

The adapter's existing error-handling branch is unchanged. The focused new test establishes the wire correction, not a reproduced causal timeout fix. Previously reviewed state/receipt/recovery/source/CAS behavior is unaffected by this diff, so the original independently verified Q1–Q5 fixes and actual PostgreSQL/API/browser evidence are reused rather than broadly audited again.

## Candidate and acceptance pin

| File | SHA-256 at preflight |
| --- | --- |
| `apps/api/src/staylead_platform/infrastructure/ai_provider.py` | `1b1842c7edf0996d0d6c351056abce478311896a0b314ee3cc24b4a8087165db` |
| `tests/contracts/test_foundry_grok_provider.py` | `11e1a314e5188c6c70f15251c76a757634f63d35a52dadfcd3156cefc088baae` |
| `docs/product/evidence/sprint-5/acceptance_runtime.py` | `8cbda9bd8c95dd85c74b24902ffd34ac560f90fc389e5bc210e84722f826e7b9` |
| `docs/product/evidence/sprint-5/semantic-expectations.json` | `9eaac0e1eea0762063e4a44e3865b701d54fc4c298dae4f2d0feec51cfb801bd` |

The original four semantic expectations remain unchanged: initial dates/adults plus grounded FAQ; one child with unknown age and targeted clarification; existing child's age/checkout correction with stable ID and code-computed nights; child removal with explicit no-add negation plus grounded FAQ. Final review requires real production UI → API → PostgreSQL → Grok results, bounded usage/failures and candidate binding. Prior failure consumed 1 attempt; the inspected initialized remediation state records 0 of 8 additional attempts. This is a preflight observation, not the final run total.

## Requirements disposition

| Requirement | Preflight disposition |
| --- | --- |
| R2-AC1 diagnostics and accurate uncertainty | Code ready; initial root cause explicitly unknown; inspect final live latency/results next |
| R2-AC2 smallest evidenced fix and preserved guards/bounds | PASS for affected code and offline checks, without causal timeout claim |
| R2-AC3 four original actual model semantics | Pending real outcomes |
| R2-AC4 recovery/replay/unknown completion | Unchanged product paths; prior independent passing evidence reused |
| R2-AC5 local checks, fresh review, bound evidence and publication | Local affected checks/preflight pass; final requirements review/publication pending coordinator evidence |

Coordinator owns the authorized bounded run and delivery. No dependent story should be marked Done from preflight alone. No main/PR83 merge, deployment, parent/epic/milestone closure, limit increase or further paid call is authorized by this report.

## Second preflight after observed partial answer timeout

Coordinator reported actual first-turn success and a second-turn committed child addition followed by a 25-second answer timeout. Four additional attempts were consumed; the process was stopped and the mechanism reassessed. Full raw evidence and final outcomes remain for final review. These observations do not prove the original wire key caused the first timeout, nor that prompt length caused the later timeout.

The builder's targeted follow-up provides domain-owned `COMMITTED_GROUNDED_QA_INSTRUCTIONS` through composition as a provider-neutral string. `extract_guest_patch=true` retains the original selector/full-answer grammar; `false` uses the concise answer-only prompt without edit operations. The prompt retains scoped supplied hotel evidence, untrusted-input treatment, supported/unknown/conflict separation, canonical guest refs and pending clarification, approved URLs/media handling and JSON shape. Existing server schema/literal/source/scope/version checks remain unchanged. This reduces irrelevant patch instructions on an already committed answer without bypassing semantic extraction or hardcoding guest outcomes. The concise prompt is also used for ordinary non-extraction answers, so affected Q&A contracts were rerun.

Independent targeted contracts: **23 passed** (grounded Q&A and adapter). Configured Ruff for all affected prompt/composition/orchestrator/test/harness files: **passed**. Independent updated harness probes additionally verified a receipt resume remains separate from semantic turns, turns 3–4 persist, turn 5 is refused, attempts 5–8 persist, a reloaded count refuses attempt 9, and prior 1 remains recorded. All probes were offline and used temporary state.

**Second preflight: PASS for the targeted changed code.** Final requirements disposition remains open. At this check, the real run state was additional 4/8, semantic turns 2/4, resumes 0. A proposed ninth additional attempt would require explicit user authorization before changing the cap; this review grants none.

| Additional changed file | SHA-256 at second preflight |
| --- | --- |
| `composition/dependencies/guest_chat.py` | `542c3a78a3da0ff6ca308f23784328d61cf23f03fd6bab99c96a9f169e65ee76` |
| `domains/hospitality/prompts/grounded_qa.py` | `93f02b62906233b32f0a291e09202663d1c8425fc9c2d40199d5df79e595f5ac` |
| `platform/conversation/orchestrator/grounded_qa.py` | `e940a70fa07a83556405dbfd5f51dca083fda5ba6cdccc5cce810c487b9639b0` |
| `tests/contracts/test_grounded_qa.py` | `c89a006a5c03c7561a702432991fe1cc257d5ca773e88f7db9d81c602cd17970` |
| `tests/integration/test_sprint5_consumer_postgres.py` | `d9b6d0aa71a893c8f98c27d7f237d412c8426d0026d0e3c3f638e92d9f73aed1` |
| `docs/product/evidence/sprint-5/acceptance_runtime.py` | `cdeaf1120cb6bc5f233df749d09e638e2187925651f22cf264f589dd9d81fb6e` |

The first three paths in this table are relative to `apps/api/src/staylead_platform/`. The full candidate manifest and final live observations must bind these revisions before final PASS.

## Final affected-code review and evidence

Reviewed final source/test/fixture candidate: `0b00a3ce05f908fdf974e8e5df91d190e86a121ccdd82555e2782c70a5d7d4ba` in `remediation-candidate-manifest.json`. The reviewer independently verified all **190 current file hashes** and the aggregate SHA-256 of sorted compact JSON file rows. This explicit-path manifest method differs from the original Sprint 5 198-file method; the hashes are not interchangeable. Final acceptance harness SHA-256: `aed5caee94ef6ef684c9d7f48e9c7af764c181f123a4bf2a1526b5c99e0239f7`. Original semantic expectations still match `9eaac0e1eea0762063e4a44e3865b701d54fc4c298dae4f2d0feec51cfb801bd`.

The final orchestrator fix clears preliminary retrieval facts when semantic selection returns no IDs. Previously, an empty selection left those preliminary facts in the final answer context. This is a verified evidence-binding defect; there is no evidence that it caused either timeout. A separate domain-owned selection-only prompt is injected for `extract_guest_patch=false`; the extraction-enabled preparation path still receives the full exact edit grammar. Both committed prompts retain fact scoping and clarification rules, and all existing server validation, source freshness, CAS, idempotency, receipt handling and two-call bounds remain intact.

The reviewer identified one test-quality finding: the first regression fixture had a nonempty candidate index but no preliminary facts, so it passed even with the clear-empty-selection fix removed. The builder repaired the fixture to explicitly provide one preliminary fact, a nonempty index and low coverage. The reviewer independently replaced only the fixed method in memory with its previous behavior: the corrected regression failed. Restoring the current method passed. No product source was changed by the reviewer. Builder before/after logs are retained in `empty-selection-prefixed-regression.log` and `empty-selection-fixed-regression.log`. This finding is resolved. The reviewer inspected the final isolated PostgreSQL consumer log `empty-selection-consumer-postgres.log`: **8 passed**, with an existing Starlette/httpx deprecation warning; these offline checks exercise the actual API/PG consumer and receipt/recovery mechanics without provider inference.

Optional HTTPX trace wiring adds no extension to default requests. The acceptance callback discards trace information and records only bounded sanitized event names/elapsed offsets. Explicit `CancelledError` recording rethrows cancellation and retains unknown usage; it cannot recover missing timing for already observed failed calls. One-call diagnostic mode uses the same persisted attempt reservation and 25-second provider default, with no retry or semantic-turn increment. Reviewer reran both final wire tests (**2 passed**) and configured Ruff. Earlier focused prompt/API/adapter checks independently passed (**26 tests**); the final fixture was separately reproduced as described above. The coordinator's pre-instrumentation backend log records **99 passed**, configured lint/compile/diff checks passed; later focused checks cover subsequent changes. Unaffected prior independent consumer/recovery evidence is reused.

### Actual run and limitations

The reviewer inspected `remediation-runtime-events.jsonl`, phase boundaries/manifests, `remediation-post-timeout-db.json`, `remediation-phase2-failure-summary.json`, `remediation-observations.json`, and the partial-success/resume-timeout screenshots. Stored phase-manifest aggregates independently match their declared fingerprints. Real results belong to their phase candidates, not the final delivery pin:

| Phase / evidence | Observed outcome |
| --- | --- |
| Phase 1 `5dd0b527…bb6211`, attempts 1–2 | Actual first turn completed. Stored brief v1 has 2026-12-10 to 2026-12-13, 3 nights, 2 adults, no children. Breakfast answer cites `F-HTL-CITY01-040`; its 06:30–09:30, location and closed-day claims match the authored selected source. Guest values use canonical guest refs. Calls returned in 12.7/19.9 seconds. |
| Same phase, attempts 3–4 | Actual second turn committed exactly one stable child with age null, retained dates/adults, and marked that age pending at brief v2. Final answer timed out after 25.8 seconds. HTTP504 includes `partial_success`, durable receipt and delta. The screenshot shows saved child/age-needed state and unfinished answer. Targeted model clarification did not complete. |
| Phase 2 `6df800a3…7f7d9`, attempts 5–6 | Explicit receipt-linked answer resume used two calls: selector returned in 19.4 seconds, then answer was interrupted by the 45-second turn deadline. HTTP504 and screenshot show unknown completion with same-ID retry. No new mutation is recorded; brief remains v2 with one age-null child. Call 6 has a start but no terminal provider event in that earlier harness. The preserved summary identifies this gap; no completion or usage is invented. |
| Diagnostic `a9cb6fb3…4be228`, attempt 7 | A synthetic minimal request returned in 4.27 seconds: TCP complete 0.387 seconds, TLS complete 0.916 seconds, response headers 4.270 seconds. This demonstrates one successful request; it does not prove latency phases or root cause of the earlier failed application calls. |
| Final pin `0b00a3ce…7d4ba` | Fresh four-turn actual acceptance **not run**. Neither earlier first-turn success nor a tiny diagnostic establishes all four outcomes on this pin. |

Exactly **7 additional provider attempts** are recorded as started, with **5 returned results**; the original **1 prior attempt** remains separate. The persisted approved cap is still **8 additional attempts**, with 2 original semantic guest turns and 1 explicit resume retained. No automatic paid retry or cap reset is evidenced. Known successful-result usage sums to input **13,106**, output **277**, total **18,196**, exactly as returned. The provider totals do not equal the two exposed component fields; their explanation is unknown. Failed/cancelled usage and complete billing remain unavailable. The numeric requested completion cap is verified; provider/billing enforcement is not established by these metrics.

Initial timeout root cause remains unknown. Evidence establishes the documented request-key correction, irrelevant edit grammar on committed paths, the empty-selection defect, and missing cancellation diagnostics. It does not establish that one caused the observed timeouts or that a sustained provider outage occurred.

### Final requirements disposition

| Requirement | Final disposition |
| --- | --- |
| R2-AC1 | PASS for bounded diagnosis and exact remaining uncertainty, with sanitized events/latency/request IDs where available; missing earlier phase timing explicitly retained |
| R2-AC2 | PASS for affected implementation/offline regression: documented key correction, reduced answer-only instructions, empty-selection fix and preserved architecture/limits/guards; no causal timeout recovery claim |
| R2-AC3 | **BLOCKED**: first turn passed an earlier candidate; second turn's answer and receipt resume failed; stable-ID age/checkout correction and removal/negation/FAQ were not run on the final candidate |
| R2-AC4 | PASS for preserved recovery mechanics, prior independent probes plus affected offline consumer checks; actual partial receipt and failed resume remain accurately recorded. No additional paid failure-injection/resume call is required by this AC |
| R2-AC5 | Code review PASS and affected local checks pass; complete story/DoD and final semantic evidence remain **BLOCKED**. Coordinator owns updated draft PR/report/status publication |

**No remaining blocking code finding in this reviewed scope; no final semantic acceptance PASS.** Keep #90 in Sprint 5 and dependent #84–#87 Blocked. Hieu explicitly declined the proposed 9/10-call caps and confirmed **KEEP 8**. The final state therefore remains 7/8 additional attempts plus the original 1, with no cap change or further paid call. The unused one attempt cannot establish the full fresh four-turn acceptance on the fixed candidate; this is the remaining gate under the confirmed bound. Do not request another extension. Coordinator may publish these reviewed fixes on the authorized draft branch with the blocked outcome. The reviewer authorizes no calls, main merge, deployment or parent/epic/milestone closure.
