# Sprint 6 independent review

Reviewer: fresh review agent; actual runtime model ID/effort unavailable. Review scope: #91–#94 plus current-copy #74 integration. Mandatory AGENTS.md, WORKING_RULES.md, AI_ARCHITECTURE.md, AGENT_EXECUTION.md and Not_Overthinking.md read. Current user execution authority supersedes older planning-only text in issue originals; historical R0/R1/R2 rules are revoked.

## Fixed candidate and pre-live verdict

Initial candidate `d3bfe54b525dd605e33127d3c8968b7deb9a0ba0`, tree `8ac11872e8549971886b19660337a3b5176ce21d`, base `d5d824125867d008f004300899f408aa75245e04` (`origin/sprint-5-canonical-brief`). Product/test/fixture/harness files were not changed by the reviewer. After owners resumed focused repairs, remaining original-candidate reads use immutable `git show d3bfe54:<path>`.

**Pre-live verdict: HOLD for scoped repairs.** No live or provider call was made by this reviewer. The pinned nine-turn matrix and runtime limits are suitable for the authorized batch once the findings below are resolved. Semantic acceptance is pending actual output, not established by fixtures, expected facts, metadata, screenshots or a model self-grade.

## Findings

1. **P1 — L2-AC3, date/time identity lost in numeric guard.** `_NUMBER` in `platform/conversation/orchestrator/grounded_qa.py` includes decimal punctuation but splits colon/hyphen values; `_numeric_forms` then uses unordered component sets. Direct offline calls to `_validate_supported_literals` accept answer `30:06` against source `06:30`, and answer `2026-10-12` against source `2026-12-10`. The explicit date/time punctuation criterion is unmet. Preserve ordered date/time literal identity while retaining positive Unicode-digit equivalence and normal breakfast-range endpoints in prose. Coordinator informed before any live call; A owns repair.

2. **P2 — L3-AC2, explicit RTL script differs between server and current UI.** `language_direction('az-Arab')` and `language_direction('en-Hebr')` return `rtl`; web `directionForLanguageTag` returns `ltr` for both because it ignores script subtags. `GuestChat` main/current brief use the web helper while answer bubbles use server metadata, so a valid open-language preference yields inconsistent direction. Direct Python/Node pure-function probes confirm this. Immutable source also makes `ar-Latn` RTL on both sides because the Arabic primary subtag overrides the explicit Latin script. Explicit script should take precedence. Coordinator informed; bounded client/server parity repair requested.

3. **P2 — L1-AC4/5, committed response language can be overridden by historical request text.** Answer-only resume passes the original source utterance into `answer_committed_turn`, with the current persisted preference. Both the committed prompt and appended orchestrator instruction allow an explicit language request in that utterance to override the preference. After a failed French edit and a later Japanese preference, resuming the French receipt can direct generation into French while the server stamps Japanese metadata. The CAS-loser regeneration has the same authority conflict. This is source-code evidence, not a claim that a real model has exhibited it. Final committed generation should treat its committed preference as authoritative; new explicit changes already pass prepare/commit. Coordinator informed for a focused payload/recovery check.

## Review coverage and evidence limits

Read issue originals #91–#94, pinned `live-cases.json`, normal approved synthetic URL overlay, original-query lexical baseline, runtime caps and browser assertions. The nine pinned turns establish expected brief versions `[1,2,3,3,3,3,4,5,5]`, language revisions `[1,2,3,4,5,6,7,8,8]`, child identity continuity and semantic targets. Actual per-turn semantic output/calls/latency/usage are pending. The lexical baseline uses zero model calls and does not establish semantic retrieval success.

Read the saved current #74 AC and reviewed storage scope/CAS/revision no-op/restart, replay metadata/staleness, partial receipt flow, answer-only resume, source freshness/authority use, bounded label producer/cache/fallback, historical answer presentation, current-answer copy eligibility and browser race assertions. The coordinator's focused preference-only failure question is safe on the initial candidate: a failed same-ID request without a brief receipt is rejected by `reserve_request` and mapped to HTTP 409 before prepare/commit, so it cannot reapply an old preference over a newer one. Existing unaffected M1 source approval/revoke/scope filters and S5 brief validation are reused. Backend integrated `114 pass/1 fail` evidence and subsequent test-only freshness seam repair with focused passes are recorded by C/A; they are not represented as a fresh reviewer full-suite run. Web builder gates and real Chrome consumer prefix/race evidence are reused with their documented limits. Race-only overclaimed full-matrix boolean summaries are not counted as observed assertions.

Independent commands (offline only): immutable `git diff d5d8241 d3bfe54 -- <changed files>`; targeted `git show d3bfe54:<path>`; direct Python `_validate_supported_literals` / `_numeric_forms` calls; Node `--experimental-strip-types` direction helper calls; Python server direction helper calls. Probe outputs are retained under `review-probes/`.

## Final evidence verdict

Pending repaired fixed candidate and the coordinator's single authorized nine-turn actual-model batch. No all-AC PASS, story completion, delivery, push, merge or deployment verdict is assigned yet.

## First repair recheck

Candidate `14b484a41bdd93e47dc4ddcb605d2f900f6e3adf`, tree `46e39644b028cb90361bb10a66ddf27a1ec521e3`; product code identical to `60dab3c5cbad95fa95bcbecb5a83653c5dd9d112`. Narrow review only; unaffected review reused.

- Original reversed time and ISO-date probes now reject; ordinary breakfast range endpoints and equivalent Arabic decimal digits are covered by passing focused tests. **Finding 1 remains open:** direct calls still accept `10/12/2026` → `12/10/2026` and `10-12-2026` → `12-10-2026` because only YYYY-first date spans are protected. This is the same lexical-component collision, not a request for date parsing/conversion.
- Finding 2 code repair passes: server/client explicit-script priority aligns (`az-Arab`, `en-Hebr` RTL; `ar-Latn` LTR). Coordinator owns focused actual-browser check; its result is not assumed here.
- Finding 3 code repair passes: committed generation appends an authoritative-language instruction expressly covering current/historical requests, and forbids a different explicit tag. The historical-French/current-Japanese request regression passes. No actual model output is inferred from that test.
- Independent commands: `PYTHONPATH=apps/api/src apps/api/.venv/bin/python -m pytest -q tests/contracts/test_sprint6_language.py tests/contracts/test_grounded_qa.py` → **28 passed**; `node --experimental-strip-types --test apps/web/tests/presentation.test.mjs` → **3 passed**. Direct numeric guard probes retained in `review-probes/first-repair.json`.

Pre-live verdict remains HOLD only for the unresolved date-literal form of finding 1. Provider calls by reviewer: **0**.

## Final pre-live narrow recheck

Fixed candidate `d5561c2f9641de833a9d8624dfbc97c471521a20`, tree `cc5ee1624b6bf28f5b5f2e197fe798bdd4dc1509`. Changed guard uses an ordered three-component lexical date token with slash/hyphen punctuation preserved, then clock tokens; no calendar parsing or conversion was introduced.

**All three initial review findings are closed in code. Pre-live readiness: READY**, subject to C recording its focused actual-browser RTL-script result. Final semantic/DoD acceptance remains pending the authorized actual-model batch.

Independent direct guard probes: **10/10 expected outcomes**. Reversed `06:30` / `30:06`, ISO date order, slash day/month order and hyphen day/month order reject. Unchanged day-first dates, ordinary breakfast range endpoints, equivalent Arabic decimal digits and decimal value equivalence pass; unequal decimals reject. Independent focused language contract suite: **4 passed**. Previous unaffected checks reused. Reviewer provider/live calls remain **0**.

Before the first inference, recommended T4 wording `日本語で回答してください。その朝食は何時からで、どこで提供されますか？` makes the intended contextual reference explicit without changing its semantic target or adding a call. Coordinator owns pin/hash refresh and the single actual batch.

## Actual batch and final evidence verdict

Executed candidate `e66647a24d5c81b60b3496a74ef7f4217c85a4c4` (product identical to repaired `d5561c2`); product fingerprint `391b09ae203ef3922c1ec54cac54373e52ee200d0690a3a7df4f868699c197c9`. `live-boundary.json` pins the matrix/runtime/browser hashes. Coordinator's actual Chrome `browser-rtl-script-corrected.log` records PASS for `az-Arab` main/brief/answer direction consistency, closing the browser portion of finding 2.

**Final scoped DoD verdict: BLOCKED.** The single authorized actual-model batch stopped at turn 1, HTTP 502 / `partial_success`, after two normally returned Codex results. No current answer, citations, semantic output or clipboard observation was produced. Turns 2–9 did not execute. The pre-live code repairs remain verified; this does not establish the missing actual-model acceptance. No retry, resume, replay, additional model call or deployment was performed by this reviewer. Remaining counters do not authorize a replacement batch.

Verified actual effects: Vietnamese explicit preference revision 1 and canonical brief version 1 persisted, with check-in `2026-12-10`, checkout `2026-12-13`, 3 nights, 2 adults, no children and no pending fields. The durable receipt identifies a saved trip edit with failed answer; answer eligibility is `pending`, avoiding false current-answer success. `failed-request-diagnosis.json` confirms `invalid_model_output` / `The model returned an invalid answer.` The candidate raises that exact message at `response_schema.model_validate_json`, so the observed failure is structured-answer JSON/schema validation. The rejected field/value is **unknown**: telemetry retained output hashes and lengths, not model bodies or validation details. Numeric-guard failure, malformed labels or a specific prompt misunderstanding cannot be asserted as the actual cause.

Runtime evidence: requested `gpt-6-luna`, low effort, Codex CLI `0.153.4`; actual served model unreported. Request 1: 5,038.4 ms, 9,278 input / 75 output tokens. Request 2: 5,567.3 ms, 6,357 input / 184 output tokens. HTTP turn: 10,759.5 ms. Known aggregate input/output: 15,635 / 259; provider total tokens unavailable. Both requests returned below the 700 output-token postcheck and 25-second provider timeout, and the turn stayed below 45 seconds; these bounds did not cause the observed failure. Run used 1/9 guest turns and 2/18 requests, max 2/turn. No new Grok call or automatic paid retry is evidenced.

| Turn / expected language | Independent semantic verdict and uncertainty | State / presentation / copy evidence |
| --- | --- | --- |
| 1 Vietnamese | Acceptance failed: no answer delivered; breakfast completeness, usefulness, unknown/conflict handling and semantic correctness unassessable. Reviewer can assess Vietnamese, but no answer text exists to assess. | Dates/adults/nights/preference persisted correctly; answer pending. No rendered answer or copy check. |
| 2 English | Not executed; child-age clarification unverified. | Missing actual state/presentation/copy evidence. |
| 3 French | Not executed; same-child age/date correction unverified. | Missing actual identity/revision/copy evidence. |
| 4 Japanese | Not executed; contextual breakfast facts unverified. | Missing actual preference/grounding/render/copy evidence. |
| 5 Chinese | Not executed; Wi-Fi availability/credentials facts unverified. | Missing actual unchanged-brief/render/copy evidence. |
| 6 Arabic | Not executed; 40 spaces, 100000 VND, no guarantee and exact approved URL unverified. | Offline RTL/copy probes are valid, but actual Arabic semantics/numbers/URL unverified. |
| 7 Hindi | Not executed; ambiguity clarification and no silent checkout change unverified. | Missing actual pending-field/revision/render evidence. |
| 8 Korean | Not executed; explicit checkout resolution/child preservation unverified. | Missing actual state/presentation/copy evidence. |
| 9 mixed, retain Korean | Not executed; preference precedence unverified with actual model. | Missing actual no-op/revision/copy evidence. |

There is no per-language fluency verdict for unexecuted output and no claim of native-speaker certification. The retained lexical baseline is only an offline comparison: expected-fact candidate coverage is 1.0 for turns 1/4/5, 0.5 for turn 6 (parking fact absent); other turns have no expected hotel fact. Actual semantic selection completeness, false-rejection rate, usefulness and conflict/unknown quality are unknown. Successful transport/schema return is not semantic success.

**Additional confirmed open L3-AC3 gap, separate from the unknown live cause:** otherwise-valid `HospitalityGroundedAnswer` payloads containing non-string label values (e.g. `{'copy': 123}`) or a non-object bundle (e.g. `['Copy']`) fail typed schema validation before the atomic label resolver can apply the required fallback. An unsafe string bundle such as `{'copy': '<b>Copy</b>'}` reaches the resolver and can fall back. Direct offline schema probes confirm the boundary gap; these probes do not establish that labels caused turn 1. No product change was made during this diagnosis.

Offline capabilities already verified remain valid: scope/revision contracts, guard negatives and Unicode equivalence, recovery-language prompt authority, direction parity, relevant local checks, PostgreSQL producer/consumer checks, and real Chrome mocked-consumer clipboard/keyboard/fallback/pending/stale/scope/race evidence with recorded limits. Those facts do not close #91/#92/#93/#74 shared actual-model DoD or #94 integrated goal. Parent/epic obligations and synthetic-source limitations remain.

## Final offline repair review

Final product candidate `5ac41db7646c49d2fc2acce5387781f4fa67ee9e`, tree `70d31d88b360abac8843a0511330acad8ae68e27`. Narrow changes from the actual failed candidate are optional-label schema normalization, safe bundle extraction, and focused regression tests. The known L3-AC3 malformed-label boundary gap is **closed offline**. Invalid optional structures/non-string values/oversized bundles or labels become an empty bundle; existing atomic resolver returns the last validated locale or approved English fallback. Unsafe strings still fail resolver validation. Core answer schema/citation authority remain strict.

Independent focused tests: `PYTHONPATH=apps/api/src apps/api/.venv/bin/python -m pytest -q tests/contracts/test_sprint6_language.py tests/contracts/test_grounded_qa.py` → **37 passed**. Additional direct schema→resolver probes cover null/list/non-string/overlength/too-many-key/HTML bundles: all **6 preserve the last validated cache**, and malformed core claims remain rejected. No model request was made.

**Final review conclusion:** no remaining identified scoped code-review finding after these narrow repairs. Shared actual-model DoD remains **BLOCKED**: no live run exists on this final product candidate, and the preserved first-turn failure on `e66647a` remains an unknown specific JSON/schema defect. The label repair is not evidence that it caused or fixes the historical failure. Do not claim multilingual semantic PASS, full story completion, or final-candidate actual-model verification. Next work is a linked bounded remediation/diagnostic acceptance task with explicit fresh model-run authority; unused request counters are not approval for automatic retry.
