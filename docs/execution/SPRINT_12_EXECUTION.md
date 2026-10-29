# Sprint 12 — execution evidence

Official Goal, user story table, priority, AC, dependencies, capacity, scope decisions and phase: [Sprint record #110](https://github.com/stayleadqst/staylead-platform/issues/110). Core: [B11 #34](https://github.com/stayleadqst/staylead-platform/issues/34), full AC1–3. This file is a checkpoint/evidence index, not a second backlog.

Planning was shown in chat and saved/read back on GitHub before coding. No Sprint 12 milestone was created. D02 was evaluated and excluded; no stretch selected. Owner branch `sprint-12-retention-transport` starts at verified integration `be3f738aa7ba7231b3ff556dbb8bbcf29f9c71bf`, tree `89712f1e55b8d97a44439710ef5b5dd197431d7a`.

Timebox 29 October 2026: observed planning clock09:32:09+07, fixed end11:40, Review11:15, Retro11:30. Worker run deadline conservatively10:33, at most60minutes including checkpoint. C checks progress every15minutes and upon worker/failure events. Requested A/B builders `gpt-6-luna/high`; fresh Q `gpt-6.1-sol/high` after fixed candidate. Actual coordinator model/effort and usage unavailable. Runtime hard deadline, restart supervisor and enforced reviewer read-only permissions unavailable; explicit ownership and fresh context are used.

Policy `pilot-retention-24h-ops7d-v1` is Hieu's approved24-hour-from-creation content/session maximum, immediate guest deletion, no old-token/cache restoration, content and derived deletion, only redacted operational metadata up to7days. B10 quota remains unchanged across deletion. No new inference/deployment, shared infrastructure/credentials, paid resources, manual CI/rerun or check bypass.

C owns this record, acceptance/evidence and private test services. A owns backend retention/store/app/composition/signing/delete tests. B owns web delete/client/proxy/state and AbortSignal wiring to room selection. Q does not edit candidate. Exact leases and contract were recorded in #110 before dispatch.

Independent expected cases were written before observations: [expected-results.json](../product/evidence/sprint-12/expected-results.json). Preserve inherited S10/S11 counters at [S11 ledger](../product/evidence/sprint-11/counters.json); no exhausted-class reset/relabel. New repair reservations and raw command logs remain in workspace `validation/sprint-12-20261029/` until a redacted delivery summary is published.

Private PostgreSQL loopback55442, data `/private/tmp/staylead-s12-pg`, C owner; isolated databases A `staylead_s12_a`, B `staylead_s12_b`, C gates `staylead_s12_verify` and browser `staylead_s12_browser`. API18542/web13542 đã chạy cho kiểm chứng local offline; C tiếp tục sở hữu và phải dừng trước handoff. No scheduler installed. C must stop/adopt each service explicitly before handoff.

Current phase: DELIVERING. B11 implemented/locally verified; independent Q PASS full AC1–3/technical DoD. [Acceptance/evidence](../product/SPRINT_12_ACCEPTANCE.md), [Q final](../product/evidence/sprint-12/q-final-review.json), [validation](../product/evidence/sprint-12/validation-final.json), [counters](../product/evidence/sprint-12/counters.json). Source writers A/B and Q hold released. Publication/merge not claimed until GitHub readback. Review11:15/Retro11:30 NOT_RUN at this snapshot; real asynchronous Hieu feedback requested, not inferred. Product remains incomplete.
