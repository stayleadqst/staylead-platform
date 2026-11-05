# Sprint 20 · B15 claim consistency

[B15 #26](https://github.com/stayleadqst/staylead-platform/issues/26) · [Sprint #123](https://github.com/stayleadqst/staylead-platform/issues/123)

B15 checks source-bound hotel facts in ordinary guest Q&A and in the FAQ portion of room advice. When an in-scope amount or assertion is unsafe, the guest still receives supported parts of the answer and uncertainty grounded in eligible records. A confirmed trip change retains its answer's private source bindings, so GuestChat can mark the answer stale after source changes.

| Acceptance | Expected and observed |
| --- | --- |
| AC1 | Claims retain their exact source IDs and current source bindings. F069 uncertainty stays explicit in both Q&A and room advice. Unrelated sources do not appear in the checked fallback. Invalid IDs and unsupported URLs remain rejected. |
| AC2 | All six combinations of Q&A/room advice and supported/unknown/conflict output keep the valid covered-parking statement, suppress the incorrect 120000 VND and preserve a source-backed correction. The guest-facing flow keeps the confirmed trip change, returns the grounded parking answer and disables copying after source version change and revocation. |
| AC3 | Independent expected facts distinguish unsupported certainty from valid helpful answers. The scoped evaluation retained 14/15 expected properties and was complete in 8/9 valid cases. One valid Japanese example was downgraded to uncertainty. These figures describe the tested fixtures and finite profiles. |

The pinned final independent component run passed 19/19. Final configured Ruff and Python compilation passed on the changed source and consumer tests. Browser5 used the production GuestChat, API and private PostgreSQL with an offline controlled provider and labeled synthetic sources. The same answer reported stale after both source transitions. A fresh turn after revoke returned uncertainty and zero evidence. Exact earlier API/PostgreSQL (5 focused tests), unchanged web build/typecheck and helper results remain supporting evidence on their recorded pins. The prior 194-test regression run deselected one unchanged fixture expiry reproduced on the baseline.

The independent review accepted the full story and U1 DoD for this candidate. This is evidence for the checked product behavior; synthetic sources and the offline provider do not establish live hotel or model quality. [Candidate and verification pins](evidence/sprint-20/verification.json)
