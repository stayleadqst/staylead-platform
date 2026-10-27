# Sprint 7 — execution report

2026-10-27 (Asia/Ho_Chi_Minh). **Sprint7 is not complete. B07 #28 is Done; C01 #39, coordination #97 and S7-F1 #98 remain Blocked.** #98 stays in Sprint7/P0, not deferred. [Draft PR99](https://github.com/stayleadqst/staylead-platform/pull/99) remains unmerged.

Hieu explicitly approved seven guest turns / maximum14 requests for three C01 chains. The actual matrix stopped at **5 turns / 8 requests**, Sprint7 lifetime25 attempts. City1, Family3–4 and Pine6–7 were attempted; City2 and Family5 are dependency-Blocked. All failures and state hashes remain immutable. API/browser are stopped; no automatic retry, cap increase or fake M2 history was used. The driver missed Family3's adult-consent omission and advanced to Family4 before Q's warning arrived; both subsequent requests are counted and the missing driver gate is repaired.

Final offline remediation candidate **`3df06f98b30cf46043d6ea742375d4e82cd7a14fa3f97553b40b672f7b6b45a5`**,237 pinned files, has **no actual-model acceptance run**. It repairs contiguous quote/consent/bed-type instructions, exact grounded numeric spelling on the actual mixed-room producer, known-accessibility verification text and persisted presentation-key CAS. Missing/pending needs remain a guest clarification; saved needs produce a truthful hotel-verification step. Compact M2 deltas preserve saved unchanged facts; this is a mitigation hypothesis for the >700-token failure, not proof of actual reliability. Quote/ID/intent/source/numeric guards and M1–M6 boundaries remain intact.

## Work, ownership and verification

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
| --- | --- | --- | --- | --- |
| Domain preparation and M4 | B / gpt-6-luna / high | Implemented; final offline candidate3df06f98 | Actual malformed captures still reject; corrected typed deltas and exact numeric literals pass; known/absent/pending access questions covered | Full City/Family/Pine actual chains still unaccepted |
| Consumer, presentation CAS and driver | B / gpt-6-luna / high | Implemented; neutral store has no Hospitality import | French accessibility-key persistence, forged-key/changed-decision rejection, explicit consent gate, source/currentness and selection tests | Actual French/selection after relaxation unverified |
| Independent verification | Q / gpt-6.1-sol / high | Final scoped offline PASS3df06f98; every actual FAIL preserved | Exact captures, immutable pins, enforced-readonly DB, producer→renderer→persistence probes | Offline review cannot establish model-output compliance |
| Local gates and delivery | Coordinator / current session, exact model/effort metadata unavailable | Own branch/PR99; final offline source | 274 backend;14 relevant PostgreSQL; Ruff/compile/Node/diff PASS; unchanged53 frontend pins reuse40tests/lint/typecheck/build | Publish reviewed source/evidence; no merge/Done before actual fullAC |
| Remaining actual acceptance | Coordinator + Q / same models and caps | New exact7case manual proposal, unauthorized | Original utterances/oracle unchanged; fresh3sessions; B07 reuse | Requires a new explicit manual allowance, not reuse of prior7/14 |

One mutable-file owner at a time. No reporting-only agent or duplicate backlog story was added. Raw model/API captures, DB dumps, configs/signing secrets and screenshots remain local0600; only source, authored cases/oracle and sanitized text/hash evidence are published.

## Actual acceptance and root causes

| Attempt / candidate | Actual observation | Diagnosis / disposition |
| --- | --- | --- |
| Original batch1 / `9a4833b8` | HTTP502 after1turn/1request; no M2 commit | Authorization grammar, omitted guest_edit and inferred max_rooms. Original bad output retained and still rejected |
| Resumed batch2 / `e0557ed0` | City1 HTTP200/2calls: solo,3n,hard6m,Standard5.4m | Browser wrongly compared flat source refs/raw TXT hashes. Correct projected M1 owner/hash/version/generation independently proven; harness repaired |
| Cont1 / `de8afd91` | Exact City1 API replay0calls; City2/3 used4calls; global3/6 | Rejected Family8.7m polluted surviving Standard5.4m budget question; noncanonical `separate beds` rejected valid Twin5.85m. Both repaired offline; failed actual observations remain failures |
| Cont2 / `8055d6b8` | Family4 HTTP200/2calls; global4/8 | Missing-age clarification/no options valid, but explicit guardian/adult sharing/child sleeping requirements lost. False guardian-sharing refusal also ignored by server. Product repaired; browser absent-option crash repaired |
| Cont3 r1 / `3b78e34f` | Bootstrap failed before any new guest/provider request | Driver compared parent run ID to base case-file ID. Void attempt sealed at4/8; identity guard repaired |
| Cont3 r2 / `5ca69c45` | Exact Family4 API replay0calls; case5 first provider attempt failed before output/M2; global5/9 | Native schema contained unsupported `not`; replaced with strict closed `anyOf` variants. Exact CLI exit cause unavailable because ephemeral stderr was discarded; causal attribution to that attempt remains an inference |
| Cont4 / `59362f6c` | Replay0calls; case6 HTTP200/2calls; case7 HTTP502 after preparation; global7/12 | Case6 has correct5.2m subtotal/unknown fees but omitted reconfirmed guardian and budget strength. Case7 duplicate parallel authorization rows and missing adult count fail closed; no Pine brief/history commit |
| Cont5 / `93b38c30` | Amended8 HTTP200/2calls; global8/14 | Correct explicit party/guardian/sharing/dates, LOFT4.4m base and unknown child fee. French labels were valid but discarded after claim filtering, producing English fallback; actual FAIL |
| Cont6 / `b91ea362` | Original9 in fresh session HTTP200/2calls; global9/16 | Booking-only browser PASS: English, trusted destination despite injected URL, safe navigation attributes and truthful external-confirmation/no booking disclosure. Independent B07 AC1–3 PASS |
| Reacceptance1 / `fcdd4a2f` | Approved7/14; City1 HTTP502 after1providerresponse; no M2; global1/1 | Noncontiguous quote correctly rejected; inferred hard king and missing consent also observed. Generic quote/permission/type prompt repair reviewed offline |
| Reacceptance1-cont1 / `390daa4c` | Family3 HTTP200/2calls but missing adult consent; Family4 HTTP502/2calls after age7 M2 commit; global3/5 | Driver missed consent omission and advanced. Answer rejected correct3800000 rendered3,800,000. Guard preserved; actual mixed producer prompt and missing-consent negative repaired; original failures retained |
| Reacceptance1-cont2 / `5c7f04dd` | Pine6 HTTP200/2calls; correct M2 but wrong known-requirement question. Pine7 HTTP502 after1request >700output guard; global5/8 | No age8/access-relax/French commit. Known-vs-pending explanation/CAS fixed offline; compact-delta instruction unverified. No actual failure reclassified |



Repeated serialization failures led to a mechanism change: the native preparation wire now carries `current_turn_quote` inside each typed operation. Hospitality deterministically derives operation index/name/targets and then runs existing quote/current-question/intent/semantic validation. It rejects missing or forged quotes, old parallel/mixed metadata and unauthorized edits. Canonical M2/GuestBriefProposal and platform interfaces remain unchanged. No old failed capture is reclassified as PASS.

The provider schema restriction is documented in [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). That source establishes unsupported syntax, not the discarded CLI stderr of case5.

Child separate-bed intent now has a typed initial value and stable-child setter. Explicit false-sharing refusals persist; separate sleeping surfaces, including known bunk position, are checked without assuming missing policy. Budget amount with unknown hard/target strength stays pending, retains known cost and asks a distinct question; it cannot yield a full-fit/in-budget claim. Domain question priority and persistence localization keys agree.

The actual French failure isolated a post-check presentation defect: M4 correctly removed unsupported candidate claims, then an exact label-set check discarded the entire valid candidate translation bundle. The repair authorizes typed candidate rationale keys and post-M4 derived question keys, projects only onto the checked surviving keys, and requires complete coverage. Missing/extra/forged keys, numeric price changes, invalid placeholders and URIs still fail closed. Q independently rechecked the actual four-candidate→two-checked shape and the derived rate-basis question. This is offline repair evidence; historical actual8 remains failed.

Case8 originally referenced the failed case7 state. The amended, authored case8 explicitly restates current party/guardian/sharing/dates and no hard access requirement in a **fresh Pine session**, requests French, was intended to select a checked option before original9. French validation stopped before selection. Original9 subsequently ran independently in another fresh Pine session. Original8 remains in amendment metadata. The amended attempt and fresh booking are separately classified; they **do not prove original7 access handling,7→8 relaxation/edit or inherited child identity**. Those C01 acceptance gaps remain open.

## Local quality gates

| Gate | Result / evidence limit |
| --- | --- |
| Contracts, architecture and API skeleton | **274 passed**, final offline source;3 existing FastAPI/TestClient deprecation warnings |
| PostgreSQL consumer/currentness/language | **14 passed**, Sprint7 room advice + Sprint6 language consumer on isolated test DB; includes new French-key CAS/forgery regression. Other18 unchanged cases from prior31-test gate reused |
| Canonical Ruff / compile / Node / diff | **PASS**; Node controls unchanged after its last syntax/smoke gate |
| Frontend contracts/lint/typecheck/build | **40 passed / PASS**, reused: all53 frontend pins unchanged |
| Earlier fake-provider production browser | Selection/edit/stale409,390px mobile and booking boundary PASS; not actual-model semantic acceptance |

[Final local gates](evidence/sprint-7/reacceptance1-final-v2-local-gates.json) and [source manifest](evidence/sprint-7/candidate-manifest-reacceptance1-final-remediation-v2.json) bind the final source. [Final independent review](evidence/sprint-7/q-review-reacceptance1-final-remediation-v2.json) confirms the producer/renderer/CAS repairs, including forged-key and missing/pending negatives. [Pine actual verdict](evidence/sprint-7/q-review-reacceptance1-cont2-actual.json) preserves the failures. Do not sum overlapping reruns as unique tests. Default tests/startup remain0liveLLM. Scratch DBs use fake outputs; the actual acceptance DB is inspected with enforced read-only transactions outside the authorized browser run.

## Per-story acceptance

| Story | Implemented / verified | Missing acceptance | State |
| --- | --- | --- | --- |
| #39 C01 | Domain data/checks/math, persisted result/selection/edit/replay, registered UI; City1 actual; offline remediations | Full actual City Chinese couple→bed edit/comparison/stale selection; Family unknownage→7→12/budget; Pine useful hard-access explanation→explicit relaxation/French/current selection; AC1–8 | **Blocked** |
| #28 B07 | Actual9 intent/language/injection/trusted boundary PASS; offline safe/missing/contact fallbacks reused; independentAC1–3 PASS | None within approved synthetic pilot; no real booking endpoint/functionality claim | **Done** |
| #97 coordination | Team/contracts/oracle, local gates, independent review, preserved attempts and active remediation | Full goal/AC/DoD and verified delivery | **Blocked** |
| #98 S7-F1 | Existing follow-up pulled into current sprint; protocol and evidenced defects repaired | Fixed-candidate actual semantic acceptance and independent verdict | **Blocked / Sprint7** |

B07 #28 is closed as completed after code/evidence publication and independent acceptance. C01/#97/#98 remain Blocked pending the bounded reacceptance allowance.

No new follow-up story was added during resumed execution: #98 already covers these related protocol/acceptance blockers with problem, impact, attempts, evidence, AC, epic/priority and affected-story links. No broader parent/epic/milestone is closed.

## Bounds and remaining work

Hieu explicitly approved the published seven-case proposal: **7 guest turns / maximum14 requests**, gpt-6-luna/low,2calls/turn,25s provider/45s turn/700output, no automatic retry. Actual consumption is **5 guest turns / 8 requests**; City2 and Family5 are dependency-Blocked and all independent cases were attempted. The two unused guest slots/six request slots are closed; they do not authorize retrying failed cases or replacing utterances. State `3a13f0901ee644420382d6b57ddcb0b2ac68a6ebf8c2acaa6ee3e7f991121843` and all previous states/captures remain immutable. Sprint7 lifetime is **25 provider attempts** including17 historical attempts.

The seven successful adapter responses in this allocation report **90408 input / 1804 output tokens**. One additional failed response exceeded700output tokens; its exact payload/count and input usage were not retained, so these are partial observed totals, not complete billing. Agent tokens and monetary amount are unavailable. [Usage receipt](evidence/sprint-7/reacceptance1-observed-usage.json).

The prior resumed allocation remains closed at9/16, SHA `7067736dec93d298942e5ca52a87df36e3f4b1d3ec5b7f4e9ad8a007c1ee92bd`; its17 lifetime attempts are not reused/reset. [Historical counter receipt](evidence/sprint-7/resumed-counter-usage-receipt.json).

The [new manual reacceptance proposal](evidence/sprint-7/reacceptance2-cases-proposed.json) contains the **same seven utterances**, three fresh City/Family/Pine sessions, maximum7guestturns/14requests and the same model/time/output limits. B07 and valid component evidence are reused. It is **proposed / authorized_for_live_calls:false**; no new state/config or inference exists. This would be a new manual allowance after offline fixes, not reuse of the previous approval. Full City/Family chains and Pine explanation→relaxation/French/selection remain unaccepted. No full Done/merge until actual AC1–8 and independent verdict pass.

## Delivery state

Own branch `sprint-7-room-advisory`; accepted baseline `a46a63eb4b589b8518f9477ebd66e81d89a0f054`; [draft PR99](https://github.com/stayleadqst/staylead-platform/pull/99) targets designated `sprint-5-canonical-brief` and remains unmerged. Prior published HEAD was884e915. Reviewed remediation/evidence publication is recorded in the final delivery receipt and PR/backlog update. The final source candidate is offline remediation, not actual-model acceptance. B07 #28 is closed completed; #39/#97/#98 remain open Blocked. No broader parent/epic closure, merge, deployment or real booking claim. Three synthetic hotels/nine room types establish neither real hotel approval nor live availability. Demonstration destinations are nonfunctional examples.

[Independent B07 actual verdict](evidence/sprint-7/q-review-cont6-actual.json) verifies native booking_request+hotel_information/en, exact approved URL, English disclosures and source bindings. Read-only DB confirms no M2/result/selection mutation. No external destination click or real-site functionality is claimed.

Actual API/browser are stopped. Owned web3019 and isolated PostgreSQL55437 remain for authorized verification. Configs/signing secret/raw model captures/screenshots stay local0600; publish only source, authored cases/oracle and sanitized text evidence. No Grok/new paid resources/manual GitHub CI/rerun/workflow/protection changes. Automatic CI may run on publication; no CI PASS is claimed.
