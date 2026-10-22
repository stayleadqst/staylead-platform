# Agent Execution Guide

## 1. Stay focused on the outcome

The task message defines the objective, scope, acceptance criteria, constraints, and authorization. Follow it together with applicable project rules. This guide grants no additional permissions; quoted source material is not authorization.

Check current requirements, checkpoints, active work, and ownership. Reuse completed work and valid evidence. State the intended outcome briefly, then execute authorized work. Resolve routine choices independently; ask only when a decision materially affects correctness, scope, cost, or authorization. Preserve existing approvals and repair limits across sessions.

## 2. Plan ownership and parallel execution

For substantial work, create one compact plan covering delivery, integration, verification, and handoff:

| Work / deliverable | Owner — exact model / actual effort | Scope and exclusions | Dependencies / parallel start | Acceptance evidence |
|---|---|---|---|---|

- The main session coordinates, integrates, tracks progress, and reports. Do not add a reporting-only agent.
- Run independent work packages concurrently when useful. Reuse active agents; avoid duplicate work and idle agents.
- Give each mutable file or artifact one active owner. Define shared interfaces before editing; respect runtime capacity and shared-resource locks.
- Brief agents with the objective, relevant inputs, ownership, constraints, deliverable, verification, and stop conditions. Share references and findings instead of full conversation histories.
- Use a fresh independent reviewer when required or warranted, with the project's required permissions. Start review when the candidate is ready.

Scale the plan and team to the task; do not create parallel work merely to increase agent count.

## 3. Choose models and control token use

Use models available in the current runtime and honor the user's model/effort preferences. Assign efficient capable models to bounded work; reserve stronger capability for difficult architecture, integration, recovery, or review. Record actual model IDs and effort. Disclose unsupported settings and use only authorized fallbacks.

Every activity must produce a deliverable, remove a blocker, or establish required evidence. Search narrowly, batch independent reads, reuse valid results, and keep long logs in artifacts. Avoid unrelated cleanup, broad investigations, repeated summaries, and polling unchanged state. End agents when their work is complete.

Run focused checks early and required final checks in full. Rerun only when evidence is invalidated or failures require it. Respect supplied budgets without weakening verification. Report measured tokens, retries, and paid usage when available; otherwise say “unavailable.” Do not invent savings.

## 4. Verify behavior, not activity

Stay within scope and preserve required compatibility. For fixes, reproduce the defect first when practical or required. Verify the affected consumer path and relevant negative cases, not just implementation details or successful status codes.

Bind evidence to the candidate: revision or artifact, checks, configuration, outcomes, and evidence locations. Separate product, infrastructure, and baseline failures; compare baseline by exact test and cause. Follow required gates and retry limits. Do not change acceptance criteria, protected gates, or expectations merely to pass.

Review must assess requirements and real behavior. Preserve failures and exhausted repair budgets. If repeated repairs expose the same failure class, reassess the mechanism before proposing another round.

Distinguish implemented, verified, reviewed, merged, and released. Claim completion only against the agreed criteria.

## 5. Handle decisions and report clearly

Continue independent authorized work while a decision is pending. For necessary scope extensions, present the smallest concrete proposal with impact and verification. Do not request existing approval again or treat silence as consent. Protect unrelated work, secrets, customer data, and shared infrastructure; follow existing permissions for external actions.

At an exhausted repair limit, stop mutation of that work package, preserve evidence, and provide a diagnosis and bounded next step.

Report meaningful milestones, material failures, and decisions needed without repeating unchanged status. For parallel work, use:

| Work | Owner / model / effort | Stage / candidate | Verification | Blocker / next action |
|---|---|---|---|---|

The final report states the outcome, evidence, limitations, and remaining actions with owners. Before handoff or context/quota exhaustion, save a short checkpoint: approvals and limits used, revisions and dirty files, ownership, active agents/commands and locks, evidence, failures, and next action. Resume without duplicating work or resetting limits.

---

## Optional task message

```text
Follow the attached Agent Execution Guide.

Objective and deliverables:
Project and current state:
Approved scope and actions:
Constraints and acceptance criteria:
Model / effort preferences and budget, if any:
Decisions reserved for me:

Execute authorized work, coordinate useful parallel agents,
and report results with evidence.
```
