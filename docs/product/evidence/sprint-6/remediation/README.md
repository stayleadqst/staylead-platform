# Sprint 6 resumed acceptance harness

This directory contains a bounded acceptance run harness. Original run
artifacts remain immutable. The harness allows three isolated namespaces:
`remediation-1` (frozen), `remediation-2` (the paused 6/18 run), and
`remediation-3` (prepared only; awaiting explicit incremental-budget approval).
The default remains `remediation-1`; no approval is inferred by adding support
for `remediation-3`. All namespaces use the pinned matrix
`staylead-s6-nine-turn-multilingual-20261026-v1`.

## Frozen run bounds

- 9 semantic guest turns, 18 Codex requests maximum, 2 Codex requests per HTTP turn.
- Provider timeout 25 seconds, full turn timeout 45 seconds, 700 output tokens.
- No automatic retries, automatic answer-only resumes, replay, or hidden reset.
- An answer-only resume is permitted only after C explicitly types `continue`
  while the pinned partial-success receipt and existing Continue control are
  visible, and only when the API was started with
  `STAYLEAD_S6_OPERATOR_RESUME=1`. It reserves a separate resume counter and
  hashed receipt, does not consume a guest-turn slot, and still consumes any
  actual provider request from the unchanged global 18-request cap. Repeating
  a receipt is allowed only after a new explicit `continue` command and gets a
  separate reservation; no automatic retry occurs. The matrix advances only
  after the resumed answer passes the current case's semantic and clipboard
  checks.
- A failed browser turn is recorded with HTTP status, sanitized response metadata,
  and screenshot. The browser stays open for C's explicit recovery decision; the
  driver never submits another turn after a failure. The run remains bounded by
  the same persistent server counters during any operator-led recovery.
- A `partial_success` response with an HTTP error status (including HTTP 502)
  remains resumable when its raw receipt is present in memory. The receipt is
  hashed in evidence; the raw value is never serialized.
- A fresh browser profile creates a new unique guest session. Do not reuse the
  previous run's browser profile, database session, or state file.

## C-owned execution commands

The runtime and browser are prepared only; this helper does not create state,
start a server, or call a model. For the separately authorized new batch, C
must use `remediation-2` on every command. Its private paths are
`/private/tmp/staylead-sprint6-remediation-2-run-state.json`,
`/private/tmp/staylead-sprint6-remediation-2-runtime-events.jsonl`,
`/private/tmp/staylead-sprint6-remediation-2-runtime.json`, and
`/private/tmp/staylead-sprint6-remediation-2-synthetic-output/`. Initialize
that counter file exactly once:

```sh
STAYLEAD_S6_RUN_NAMESPACE=remediation-2 \
apps/api/.venv/bin/python docs/product/evidence/sprint-6/remediation/resumed_acceptance_runtime.py \
  --initialize-state --authority "current-user-resume-issue-95"
```

Then, after C has installed the private configuration at
`/private/tmp/staylead-sprint6-remediation-2-runtime.json` and confirmed the
candidate build is ready, start the production API with the public settings:

```sh
STAYLEAD_S6_RUN_NAMESPACE=remediation-2 STAYLEAD_LIVE_EVAL=1 STAYLEAD_VALIDATION_DIAGNOSTICS=true \
STAYLEAD_S6_OPERATOR_RESUME=1 \
PYTHONPATH=apps/api/src apps/api/.venv/bin/python \
  docs/product/evidence/sprint-6/remediation/resumed_acceptance_runtime.py \
  --host 127.0.0.1 --port 18086
```

The web production server remains C-owned at `http://127.0.0.1:13016`. In a
separate terminal, the visible Chrome driver command is:

```sh
STAYLEAD_S6_RUN_NAMESPACE=remediation-2 STAYLEAD_S6_HEADLESS=0 STAYLEAD_S6_WEB_URL=http://127.0.0.1:13016 \
  node docs/product/evidence/sprint-6/remediation/resumed-live-browser.mjs
```

The browser harness refuses to overwrite its output directory. Each turn is
appended to the namespace output directory (`remediation-2-live-run/` for the
new batch); every turn gets a screenshot,
including transport and HTTP failures. Copy is checked against the exact
rendered `.answer-copy-source` text and the persistent request/turn counters are
compared before and after copy to catch any extra provider call. Error metadata
retains only a safe error code and the allowlisted validation location/type
structure from `error.validation_diagnostics`. The browser does not measure
server-side external network activity; run results label that metric
`unmeasured_by_browser_driver`.

If a turn fails, the driver pauses and keeps Chrome visible. For a
`partial_success` with its receipt, it accepts `continue` to click the existing
answer-only UI control once; it also accepts `snapshot` and `close`. It never
retries a receipt automatically. C decides every continuation explicitly. No
session token is written to evidence.

`remediation-3` is prepared for a possible fixed-candidate batch only after
explicit approval of the incremental request budget. Namespace 2 has 6/18
requests spent, leaving 12; the proposed transfer of those 12 plus 6 newly
approved requests would give namespace 3 a fresh 18-request cap and a combined
maximum of 24 across namespaces 2 and 3. This proposal does not authorize or
initialize namespace 3. Its isolated paths are
`/private/tmp/staylead-sprint6-remediation-3-run-state.json`,
`/private/tmp/staylead-sprint6-remediation-3-runtime-events.jsonl`,
`/private/tmp/staylead-sprint6-remediation-3-runtime.json`,
`/private/tmp/staylead-sprint6-remediation-3-synthetic-output/`, and
`remediation-3-live-run/` under this directory. Do not initialize or use them
until approval and the fixed candidate are confirmed.

## Optional synthetic JSON capture

Default capture is off. For a run explicitly approved to retain synthetic model
JSON for offline schema replay, set both exact opt-in variables on the API
process:

```sh
STAYLEAD_S6_CAPTURE_SYNTHETIC_JSON=1 \
STAYLEAD_S6_SYNTHETIC_MATRIX_ID=staylead-s6-nine-turn-multilingual-20261026-v1
```

Only valid JSON output up to 64 KiB is accepted, and only when that request's
guest utterance exactly matches the corresponding turn in the pinned matrix.
For answer-only resumes, the runtime reads `request.input_text` only in
memory, parses its JSON `question`, and enables capture only on an exact match
to the pinned utterance for the current semantic turn. That input, prompt, and
token are never written. Each provider attempt is written once, with mode 0600,
under the namespace-specific private capture directory. Each file contains the
exact output text, parsed JSON, turn/attempt IDs, byte count/hash, and
request/prompt hashes. These are private scratch artifacts and must not be
copied into public evidence. Oversized, malformed, non-JSON, non-matrix, or
duplicate capture is refused. No prompts, utterances, credentials, signed
tokens, DSNs, or raw configuration are added to normal event logs.

## Offline checks

```sh
python3 docs/product/evidence/sprint-6/remediation/test_resumed_acceptance_runtime.py -v
node --test docs/product/evidence/sprint-6/remediation/test_operator_resume_routing.mjs
node --test docs/product/evidence/sprint-6/remediation/test_safe_answer_trace.mjs
node --check docs/product/evidence/sprint-6/remediation/resumed-live-browser.mjs
```

These are local boundary checks only; they do not start the API, open Chrome,
or make provider calls.
