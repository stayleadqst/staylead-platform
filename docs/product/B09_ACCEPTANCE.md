# Sprint 9 / B09 — session/property and AI-action boundaries

**Stage: repaired candidate locally verified and independently Q PASS; authorized publication/merge delivery follows this acceptance commit.** Scope is exactly [#30 B09](https://github.com/stayleadqst/staylead-platform/issues/30), full AC1–3. Owner branch `pilot-b09-security`; base `sprint-5-canonical-brief@d304238a1cb2b427650e03a2de81af92aa6ae255`. No deployment or new live inference.

## Result and mechanism

Initial Q review returned `NO_FULL_AC_PASS`: a proposal could use an informational question as authority to clear committed allergy/accessibility needs. Actual API/PostgreSQL reproduction confirmed the defect. The earlier tests that passed did not establish AC2; their evidence and failure report remain under `evidence/b09`.

Every actual model-proposed M2 data/pending change now stops at a signed review challenge before M2 commit or dependent M4/M5 execution. Guest confirmation authorizes only the displayed validated mutation, bound to session/property, expected brief version, purpose and a five-minute expiry. The signed canonical mutation preserves generated child IDs rather than regenerating them at confirmation. Reads and noops do not require confirmation. Cancel discards the proposal without committing or automatically continuing. Contract2 fails mismatched clients safely.

Confirmation has its own idempotency identity. M2 commits before receipt-based answer/capability continuation, preserving the original source utterance, turn scope and selected fact IDs. Valid edits, source currentness, room selection, local-guide hard constraints, partial failure and answer-only recovery retain their downstream checks. A committed answer cannot introduce another patch or change the prepared turn intents.

Actual browser verification exposed a second defect: the confirmation handler mixed `asyncio` loop time with `time.monotonic()`. These clocks have different epochs in this macOS uvloop runtime. The handler now keeps separate deadlines for event-loop operations and persistence; no timeout was increased. The regression runs standard asyncio and optional uvloop with the same state/replay assertions.

## AC evidence

| AC | Final observations |
|---|---|
| AC1 — identity/scope/forged results/replay | Composed API and isolated PostgreSQL cases reject missing, forged, expired or foreign session/property identities before dispatch. Receipt/result/selection scope and freshness checks remain. Signed confirmation rejects tampering, foreign scope and stale versions; same-ID replay preserves child IDs and avoids duplicate provider/capability/mutation effects. |
| AC2 — untrusted text/actions | Typed validators reject invented operations/fields and invalid current-turn proposals. The reproduced hard-need clearing proposal stops for exact review with authoritative state unchanged. Explicit confirmation alone commits that delta. Controlled source/tool injections cannot supply a new committed-answer patch or change prepared intent. Literal HTML/unsafe URL guest/proposal content creates no injected markup or active attacker link. |
| AC3 — allowed/refused consumer paths | Actual production Next browser → proxy → offline test API → PostgreSQL completes FAQ200 and confirmed edit200, rejects malformed proposal502, and keeps adults2/briefVersion1/one receipt after canceling an adults3/accessibility proposal. Refused sessions retain stateVersion0/no brief/no receipt. Relevant S5/S6/S7/S8 API/PG consumer assertions remain; no live acceptance batch was rerun. |

## Local validation

- Builder final affected suite: 46 passed across B09 contracts/API, S5/S6/S7/S8 consumers and API skeleton before the test-only asyncio/uvloop parameterization. Both parameterized P1 cases subsequently passed. Counts overlap other reported runs.
- Coordinator final B09/API/schema checks: 23 passed on the fixed product; 17 relevant inherited contracts passed. Earlier coordinator19 checks are retained, not added as unique coverage.
- Final P2 recovery: B09 contracts/API16 and cancellation case1 passed; Q independently reran the affected PG case. Browser transport simulation returned no-effect503 first; explicit retry used a new ID and actually committed through API/PG200. No automatic retry.
- Web contracts45, lint, typecheck and production build with guest contract2 passed. Canonical Ruff, Python compileall, Node syntax and whitespace checks passed.
- Actual browser final confirmation/cancel, FAQ/refusal and mobile390 HTML-refusal scenarios passed; screenshots were visually inspected. The earlier three confirmation failures remain in workspace artifacts and are not claimed as passes.
- Exact source/config/test pins: [final manifest](evidence/b09/candidate-manifest-final.json). Original manifest/review/observations remain historical; they do not claim the repaired product was unchanged from Sprint8.

Workspace artifacts: `validation/b09-20261028/resumed-*.log`, `resumed-browser-final/*.png`, and `resumed-browser-final-db.json`. Screenshots and transient session material remain local; published evidence is sanitized text and hashes. The test API always injects controlled offline provider outputs, never a live provider. Product-model calls added: **zero**. Agent token metrics are unavailable. Synthetic hotel/provider cases prove server boundaries, not real-model resistance or real-hotel approval.

## Review and delivery

Fresh Q `/root/q_b09_final`, `gpt-6.1-sol/high`, returned **PASS full scoped AC1–3/technical DoD**, no open actionable finding, for candidate `891515af41444208931c671cad0b54dbaa57f18f5cd6e4296fe19c5965f79ce0` (282 files). All hashes were independently verified. Q ran six contracts and the reproduced P2 PostgreSQL cancellation/replay regression, inspected browser/PG/web evidence, and accepted documented expiry limits. See [independent final review](evidence/b09/independent-final-review.json) and [final observations/hashes](evidence/b09/final-observations.json). Initial P1 and final P2 are closed. C may commit/push/own PR/merge into `sprint-5-canonical-brief`. GitHub required checks remain enforced; no manual CI run/rerun or CI wait gate. No other PR/base, parent/epic, new story, scheduler, infrastructure, credential or deployment change is included.

A confirmation token is valid for five minutes; an expired token is refused even when retrying a previously completed confirmation. No fresh mutation or provider action is allowed by expiry. Existing receipt-based answer recovery remains separate; this is not a new data-retention policy.
