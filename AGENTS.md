# Staylead Platform — mandatory working context

Before planning, implementing, reviewing, or modifying AI behavior, read and apply:

1. [Working rules](docs/WORKING_RULES.md).
2. [Mandatory M1–M6 architecture and AI workflow](docs/architecture/AI_ARCHITECTURE.md).
3. [Agent Execution Guide](docs/execution/AGENT_EXECUTION.md).
4. [Focus and no overthinking requirements](docs/execution/Not_Overthinking.md).

These are standing user requirements for all contributors and delegated agents. Preserve module responsibilities and the business workflow even for a small implementation. Do not silently replace them with a different AI pipeline or weaken acceptance criteria. A user-approved architecture change must update the architecture document in the same scope.

Hieu authorized autonomous end-to-end execution of Sprint 1 on 2026-10-22: issues #10, #11, #13, #66–#69, coordinated by #70. This includes relevant local validation, bounded real-model acceptance, review/fix and delivery to main as already permitted. It does not authorize deployment, paid resource creation, other markets, or completion of the original parent stories. Never publish Azure credentials. Default automated tests must not call real LLMs.

Hieu approved autonomous end-to-end execution of Sprint 2 on 2026-10-23: F06 #14, B01b #72, B02b #73 and coordination #71. Follow the approved milestone 2 scope, including local production-build browser integration, bounded real-Grok acceptance, independent review/fix and delivery to main. B12a #74 remains optional and must not start automatically. Preserve parent/epic obligations; no deployment, paid-resource creation or changes to the old repositories. Reuse valid Sprint 1 evidence and keep all credentials out of GitHub and artifacts.

Hieu authorized autonomous end-to-end Sprint 3 on 2026-10-23: S3-K1 #75, S3-K2 #76, S3-K3 #77 and coordination #78. This includes isolated local PostgreSQL/production-browser checks, minimal opt-in Grok acceptance, independent review/fix and commit/push directly to main after local validation. Do not close milestone 3, parents or epics. Stretch #74, deployment, paid resources, existing-pack lifecycle changes and old-repository changes remain excluded. Synthetic authored media evidence does not establish real-hotel/operator acceptance. Keep default tests/build/startup offline and preserve all secret controls.
