# Staylead Platform — mandatory working context

Before planning, implementing, reviewing, or modifying AI behavior, read and apply:

1. [Working rules](docs/WORKING_RULES.md).
2. [Mandatory M1–M6 architecture and AI workflow](docs/architecture/AI_ARCHITECTURE.md).
3. [Agent Execution Guide](docs/execution/AGENT_EXECUTION.md).
4. [Focus and no overthinking requirements](docs/execution/Not_Overthinking.md).

These are standing user requirements for all contributors and delegated agents. Preserve module responsibilities and the business workflow even for a small implementation. Do not silently replace them with a different AI pipeline or weaken acceptance criteria. A user-approved architecture change must update the architecture document in the same scope.

Hieu authorized autonomous end-to-end execution of Sprint 1 on 2026-10-22: issues #10, #11, #13, #66–#69, coordinated by #70. This includes relevant local validation, bounded real-model acceptance, review/fix and delivery to main as already permitted. It does not authorize deployment, paid resource creation, other markets, or completion of the original parent stories. Never publish Azure credentials. Default automated tests must not call real LLMs.
