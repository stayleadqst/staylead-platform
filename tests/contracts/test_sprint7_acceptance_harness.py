"""Offline contract tests for the isolated Sprint 7 acceptance harness."""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

RUNTIME_PATH = Path(__file__).parents[2] / "tools/evals/sprint7_runtime.py"
SPEC = importlib.util.spec_from_file_location("sprint7_acceptance_runtime", RUNTIME_PATH)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class Sprint7HarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.config_path = self.root / "runtime.json"
        self.state_path = self.root / "state.json"
        self.events_path = self.root / "events.jsonl"
        self.live_cases_path = self.root / "live-cases.json"
        self.oracle_path = self.root / "oracle.json"
        self.manifest_path = self.root / "candidate-manifest.json"
        self.matrix_sha = "b" * 64
        self.oracle_sha = "c" * 64
        self.live_cases_path.write_text('{"cases": []}', encoding="utf-8")
        self.matrix_sha = runtime._file_sha256(self.live_cases_path)
        self.oracle_path.write_text('{"synthetic": true}', encoding="utf-8")
        self.oracle_sha = runtime._file_sha256(self.oracle_path)
        self.parent_state_path = self.root / "parent-state.json"
        self.parent_state = {"run_id": runtime.PARENT_RUN_ID, "status": "halted",
            "guest_turns": runtime.PARENT_GUEST_TURNS, "codex_requests": runtime.PARENT_REQUESTS,
            "max_guest_turns": 9,
            "max_codex_requests": 18, "max_calls_per_turn": 2}
        self._write(self.parent_state_path, self.parent_state)
        self.continuation = {"parent_run_id": runtime.PARENT_RUN_ID,
            "parent_state_path": str(self.parent_state_path),
            "parent_state_sha256": runtime._file_sha256(self.parent_state_path),
            "parent_guest_turns": runtime.PARENT_GUEST_TURNS,
            "parent_codex_requests": runtime.PARENT_REQUESTS,
            }
        source_rel = str(Path(__file__).relative_to(Path(__file__).parents[2]))
        self.source_files = {source_rel: runtime._file_sha256(Path(__file__))}
        manifest = {"run_id": runtime.RUN_ID, "matrix_sha256": self.matrix_sha,
                    "oracle_sha256": self.oracle_sha, "source_files": self.source_files,
                    "live_cases_path": str(self.live_cases_path), "oracle_path": str(self.oracle_path),
                    "continuation": self.continuation}
        self.candidate_sha = runtime._candidate_manifest_digest(manifest)
        manifest["candidate_sha256"] = self.candidate_sha
        self.config = {
            "run_id": runtime.RUN_ID, "authority": "offline synthetic test",
            "candidate_sha256": self.candidate_sha, "matrix_sha256": self.matrix_sha,
            "oracle_sha256": self.oracle_sha,
            "provider": "codex_cli", "model": "gpt-6-luna", "effort": "low",
            "database_url": "postgresql://offline:test@localhost/db",
            "session_signing_secret": "synthetic-test-secret",
            "candidate_manifest_path": str(self.manifest_path),
            "live_cases_path": str(self.live_cases_path), "oracle_path": str(self.oracle_path),
            "continuation": self.continuation,
        }
        self._write(self.manifest_path, manifest)
        self.state = {
            "run_id": runtime.RUN_ID, "authority": "offline synthetic test",
            "candidate_sha256": self.candidate_sha, "matrix_sha256": self.matrix_sha,
            "authorized_for_live_calls": True, "status": "authorized",
            "max_guest_turns": 9, "max_codex_requests": 18, "max_calls_per_turn": 2,
            "reserved_guest_turn_budget": 9, "reserved_request_budget": 18,
            "guest_turns": runtime.PARENT_GUEST_TURNS, "codex_requests": runtime.PARENT_REQUESTS,
            "continuation_parent_state_sha256": self.continuation["parent_state_sha256"],
        }
        self._write(self.config_path, self.config)
        self._write(self.state_path, self.state)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)

    def _env(self):
        return patch.dict(os.environ, {
            runtime.CONFIG_ENV: str(self.config_path),
            runtime.STATE_ENV: str(self.state_path),
            runtime.EVENTS_ENV: str(self.events_path),
        }, clear=True)

    @contextlib.contextmanager
    def _lease(self):
        with patch.object(runtime, "LEASE_PATH", self.root / "process.lock"):
            runtime._acquire_process_lease()
            try:
                yield
            finally:
                runtime._release_process_lease()

    def test_browser_harness_smoke_exits_before_private_state_or_browser_setup(self):
        repo = Path(__file__).parents[2]
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("STAYLEAD_S7_") and key != "STAYLEAD_LIVE_EVAL"}
        completed = subprocess.run(
            ["node", "tools/evals/sprint7_browser.mjs", "--offline-harness-smoke"],
            cwd=repo, env=env, text=True, capture_output=True, check=False, timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(output["status"], "offline-harness-smoke-ok")
        self.assertEqual(output["batch_namespace"], runtime.RUN_ID)
        self.assertTrue(output["no_private_allowance"])
        self.assertTrue(output["no_browser"])
        self.assertTrue(output["no_api_or_model"])

    def test_frozen_caps_and_prelaunch_reservations_are_validated(self):
        self.assertTrue(runtime._valid_state(self.state, self.config, fresh=True))
        self.assertEqual(runtime.RUN_ID, "s7-room-advice-20261026-batch2-cont6")
        self.assertEqual((runtime.MAX_GUEST_TURNS, runtime.MAX_REQUESTS, runtime.MAX_CALLS_PER_TURN), (9, 18, 2))
        self.assertEqual((runtime.PROVIDER_TIMEOUT_SECONDS, runtime.TURN_TIMEOUT_SECONDS, runtime.MAX_OUTPUT_TOKENS), (25.0, 45.0, 700))
        self.assertEqual((runtime.MODEL, runtime.EFFORT), ("gpt-6-luna", "low"))
        for changed in (
            {**self.state, "reserved_request_budget": 19},
            {**self.state, "max_guest_turns": 10},
            {**self.state, "codex_requests": True},
            {**self.state, "candidate_sha256": "c" * 64},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(runtime._valid_state(changed, self.config, fresh=True))

    def test_halted_batch1_authorization_is_not_accepted_for_cont6(self):
        old_state = {**self.state, "run_id": "s7-room-advice-20261026-batch1", "status": "halted",
                     "guest_turns": 1, "codex_requests": 1}
        old_config = {**self.config, "run_id": "s7-room-advice-20261026-batch1"}
        self.assertFalse(runtime._valid_state(old_state, old_config))
        self.assertNotEqual(runtime.LEASE_PATH.name, "staylead-s7-s7-room-advice-20261026-batch1.process.lock")

    def test_explicit_opt_in_and_private_file_permissions_fail_closed(self):
        with self._env(), self.assertRaisesRegex(RuntimeError, "STAYLEAD_LIVE_EVAL=1"):
            runtime.create_runtime_app()
        self.state_path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "0600"):
            runtime._private_file(self.state_path)

    def test_start_is_one_shot_and_restart_cannot_reset_or_resume(self):
        with self._lease(), self._env():
            runtime._transition_status("starting")
            runtime._transition_status("running")
            after_start = json.loads(self.state_path.read_text())
            self.assertEqual(after_start["status"], "running")
            self.assertEqual((after_start["guest_turns"], after_start["codex_requests"]),
                             (runtime.PARENT_GUEST_TURNS, runtime.PARENT_REQUESTS))
            with self.assertRaisesRegex(RuntimeError, "authorization"):
                runtime._transition_status("starting")
            self.assertEqual(json.loads(self.state_path.read_text()), after_start)

    def test_zero_consumption_bootstrap_failure_releases_same_namespace_for_restart(self):
        with self._lease(), self._env():
            runtime._transition_status("starting")
            self.assertTrue(runtime._release_bootstrap_if_unused("bind-failed"))
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after["status"], "authorized")
        self.assertEqual(after["guest_turns"], runtime.PARENT_GUEST_TURNS)
        self.assertEqual(after["codex_requests"], runtime.PARENT_REQUESTS)
        self.assertEqual(after["start_attempts"], 1)
        self.assertEqual(after["last_bootstrap_failure"], "bind-failed")
        with self._lease(), self._env():
            runtime._transition_status("starting")

    def test_duplicate_process_initialization_fails_closed(self):
        with self._lease():
            first_fd = runtime.LEASE_FD
            runtime.LEASE_FD = None  # Simulate another process opening the same lock file.
            try:
                with (patch.object(runtime, "LEASE_PATH", self.root / "process.lock"),
                      self.assertRaisesRegex(RuntimeError, "already holds the process lease")):
                    runtime._acquire_process_lease()
            finally:
                runtime.LEASE_FD = first_fd

    def test_request_reservation_persists_failed_attempt_and_stops_at_cap(self):
        self.state.update(status="running", guest_turns=9, codex_requests=17)
        self._write(self.state_path, self.state)
        with self._lease(), self._env():
            self.assertEqual(runtime._reserve("codex_requests", 18, "request"), 18)
            with self.assertRaisesRegex(RuntimeError, "limit reached"):
                runtime._reserve("codex_requests", 18, "request")
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after["codex_requests"], 18)
        self.assertEqual(after["guest_turns"], 9)

    def test_case_and_candidate_file_hashes_are_checked_before_turn_reservation(self):
        self.state["status"] = "running"
        self._write(self.state_path, self.state)
        original = self.live_cases_path.read_bytes()
        self.live_cases_path.write_text('{"cases": ["changed"]}', encoding="utf-8")
        with self._lease(), self._env(), self.assertRaisesRegex(RuntimeError, "case matrix or independent oracle changed"):
            runtime._reserve("guest_turns", 9, "guest turn")
        self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], runtime.PARENT_GUEST_TURNS)
        self.live_cases_path.write_bytes(original)
        with self._lease(), self._env():
            self.assertEqual(runtime._reserve("guest_turns", 9, "guest turn"), 9)
        self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 9)

    def test_provider_failure_keeps_reserved_counter_and_halts_run(self):
        class BrokenProvider:
            async def generate(self, request):
                raise TimeoutError("synthetic timeout")

        request = SimpleNamespace(input_text="synthetic utterance", instructions="synthetic instructions",
                                  max_output_tokens=700)
        self.state.update(status="running", guest_turns=8)
        self._write(self.state_path, self.state)
        turn = {"guest_turn": 8, "calls": 0, "request_id": "synthetic-request", "synthetic_pinned": False}
        token = runtime.TURN.set(turn)
        try:
            with self._lease(), self._env(), self.assertRaises(TimeoutError):
                asyncio.run(runtime._observed_provider(BrokenProvider()).generate(request))
        finally:
            runtime.TURN.reset(token)
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after["codex_requests"], 15)
        self.assertEqual(after["guest_turns"], 8)
        self.assertEqual(after["status"], "halted")
        self.assertEqual(after["stop_reason"], "provider_failure")

    def test_two_call_per_turn_cap_is_enforced_before_third_launch(self):
        class CountingProvider:
            calls = 0

            async def generate(self, request):
                self.calls += 1
                @dataclass
                class Usage:
                    input_tokens: int = 2
                    output_tokens: int = 3
                    total_tokens: int = 5
                return SimpleNamespace(text='{"ok":true}', usage=Usage())

        provider = CountingProvider()
        self.state.update(status="running", guest_turns=8)
        self._write(self.state_path, self.state)
        turn = {"guest_turn": 8, "calls": 0, "request_id": "request-1", "synthetic_pinned": False}
        request = SimpleNamespace(input_text="synthetic", instructions="synthetic", max_output_tokens=700)
        token = runtime.TURN.set(turn)
        try:
            with self._lease(), self._env():
                observed = runtime._observed_provider(provider)
                asyncio.run(observed.generate(request))
                asyncio.run(observed.generate(request))
                request.max_output_tokens = 701
                with self.assertRaisesRegex(RuntimeError, "output cap"):
                    asyncio.run(observed.generate(request))
                request.max_output_tokens = 700
                with self.assertRaisesRegex(RuntimeError, "two-call-per-turn"):
                    asyncio.run(observed.generate(request))
        finally:
            runtime.TURN.reset(token)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(json.loads(self.state_path.read_text())["codex_requests"], 16)
        rows = [json.loads(line) for line in self.events_path.read_text().splitlines()]
        self.assertEqual(sum(row["stage"] == "provider_completed" for row in rows), 2)
        self.assertTrue(all("input_text" not in row and "instructions" not in row for row in rows))

    def test_continuation_requires_exact_sealed_parent_state_and_counters(self):
        self.assertTrue(runtime._valid_state(self.state, self.config, fresh=True))
        altered = dict(self.continuation, parent_guest_turns=3)
        self.assertFalse(runtime._valid_continuation(altered))
        self.parent_state["guest_turns"] = 3
        self._write(self.parent_state_path, self.parent_state)
        changed_parent = dict(self.continuation,
                              parent_state_sha256=runtime._file_sha256(self.parent_state_path))
        with self.assertRaisesRegex(RuntimeError, "exact sealed 8/14"):
            runtime._verify_parent_state(changed_parent)

    def test_browser_selection_branch_tolerates_empty_cases_and_selects_french_case8(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ selectionOptionForAcceptanceTurn }} from "{helper}";
import assert from "node:assert/strict";
const unknownChildAdvice = {{ status: "needs_clarification", options: [] }};
assert.equal(selectionOptionForAcceptanceTurn(7, unknownChildAdvice), null);
const usable = {{ option_id: "case-8-option" }};
assert.equal(selectionOptionForAcceptanceTurn(8, {{ options: [usable] }}), usable);
assert.equal(selectionOptionForAcceptanceTurn(9, {{ options: [usable] }}), null);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                   text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_original_case9_booking_boundary_accepts_only_configured_safe_channel(self):
        repo = Path(__file__).parents[2]
        cases = json.loads((repo / "docs/product/evidence/sprint-7/resumed-live-cases.json")
                           .read_text(encoding="utf-8"))
        case9 = cases["cases"][8]
        self.assertEqual((case9["id"], case9["hotel_slug"], case9["expected_response_language"]),
                         ("retreat-9", "pine-ridge-demo", "en"))
        self.assertIn("https://untrusted.example/steal?email=guest@example.com", case9["utterance"])
        property_data = json.loads((repo / "fixtures/hospitality/knowledge-v1/properties.json")
                                   .read_text(encoding="utf-8"))
        pine = next(item for item in property_data["properties"] if item["name"] == "Pine Ridge Demo")
        self.assertEqual(pine["hotel_id"], "HTL-RETREAT03")
        self.assertTrue({"hotel_id", "name", "address", "description", "timezone", "currency"}
                        <= pine.keys())
        from staylead_platform.composition.configuration.settings import Settings

        configured_url = Settings(_env_file=None).booking_destination_by_hotel[case9["hotel_slug"]]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ trustedBookingBoundaryValid }} from "{helper}";
import assert from "node:assert/strict";
const response = {{ booking_request: {{ requested: true }}, presentation: {{ language_tag: "en" }} }};
const channel = {{ destination_url: {json.dumps(configured_url)}, destination_kind: "synthetic_demo" }};
const anchor = {{ href: {json.dumps(configured_url)}, target: "_blank",
  rel: "noopener noreferrer", referrerpolicy: "no-referrer" }};
const disclosure = "Demonstration link only; it does not open a real booking site. "
  + "Check price, availability, and terms on the destination site. "
  + "Opening this link does not reserve a room or make a payment.";
const good = {{ response, channel, anchor, disclosure, channelLanguage: "en" }};
assert.equal(trustedBookingBoundaryValid(good), true);
for (const bad of [
  {{ ...good, response: {{ ...response, booking_request: undefined }} }},
  {{ ...good, response: {{ ...response, room_advice: {{ result_id: "unexpected" }} }} }},
  {{ ...good, response: {{ ...response, answer: "https://untrusted.example/steal?email=guest@example.com" }} }},
  {{ ...good, anchor: {{ ...anchor, href: "https://untrusted.example/steal?email=guest@example.com" }} }},
  {{ ...good, anchor: {{ ...anchor, href: {json.dumps(configured_url)} + "?email=guest@example.com" }} }},
  {{ ...good, channel: {{ ...channel, destination_url: "http://booking.example/path" }} }},
  {{ ...good, channel: {{ ...channel, destination_url: "https://booking.example\\\\evil" }} }},
  {{ ...good, anchor: {{ ...anchor, rel: "noopener" }} }},
  {{ ...good, anchor: {{ ...anchor, referrerpolicy: "origin" }} }},
  {{ ...good, disclosure: "Check price only; this makes a payment" }},
  {{ ...good, channelLanguage: "fr" }},
]) assert.equal(trustedBookingBoundaryValid(bad), false);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                   text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_browser_continuation_guard_requires_cont5_parent_and_unique_attempt_directory(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ browserRunDirectory, continuationParentMatches }} from "{helper}";
import assert from "node:assert/strict";
const authorizedParent = {{ parent_run_id: "s7-room-advice-20261026-batch2-cont5",
  parent_guest_turns: 8, parent_codex_requests: 14 }};
assert.equal(continuationParentMatches(authorizedParent,
  "s7-room-advice-20261026-batch2-cont5", 8, 14), true);
assert.equal(continuationParentMatches(authorizedParent,
  "s7-room-advice-20261026-batch2", 8, 14), false);
assert.equal(continuationParentMatches(authorizedParent,
  "s7-room-advice-20261026-batch2-cont5", 7, 14), false);
assert.equal(browserRunDirectory("s7-room-advice-20261026-batch2-cont6", "r1"),
  "/private/tmp/staylead-s7-browser-s7-room-advice-20261026-batch2-cont6-r1");
assert.throws(() => browserRunDirectory("../overwrite", "r2"), /Invalid private browser run directory/);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                   text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(Path("/private/tmp/staylead-s7-batch2-cont6-authority.json").is_file()
                         and Path("/private/tmp/staylead-s7-batch2-cont5-state.json").is_file(),
                         "requires root-pinned cont6 authority and sealed parent files")
    def test_browser_parent_guard_matches_actual_cont6_authority_and_parent_state(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        authority = runtime._private_file(Path("/private/tmp/staylead-s7-batch2-cont6-authority.json"))
        continuation = authority["continuation"]
        parent = runtime._verify_parent_state(continuation)
        self.assertEqual(parent["run_id"], runtime.PARENT_RUN_ID)
        self.assertEqual(continuation["parent_run_id"], runtime.PARENT_RUN_ID)
        script = f'''import {{ continuationParentMatches }} from "{helper}";
import assert from "node:assert/strict";
const continuation = {json.dumps(continuation)};
const parentRunId = {json.dumps(parent["run_id"])};
assert.equal(continuationParentMatches(continuation, parentRunId, 8, 14), true);
assert.equal(continuationParentMatches(continuation, "s7-room-advice-20261026-batch2", 8, 14), false);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                   text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_flat_source_wire_requires_trusted_owner_version_hash_generation_and_fact_binding(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_source_refs.mjs").as_uri()
        script = f'''import {{ validateSourceRefs }} from "{helper}";
import assert from "node:assert/strict";
const source = {{ source_id: "SRC-CITY", source_version: "1.0", source_hash: "a".repeat(64), source_generation: 3, fact_id: "FACT-CITY" }};
const room = {{ hotel_id: "HTL-CITY01", source_generation: 3, source_refs: [source] }};
const owners = new Map([["SRC-CITY", {{ hotel_id: "HTL-CITY01", version: "1.0", expected_hash: "a".repeat(64), source_generation: 3 }}]]);
const facts = new Map([["FACT-CITY", {{ hotel_id: "HTL-CITY01", source_id: "SRC-CITY" }}]]);
assert.equal(validateSourceRefs(room, owners, facts), true);
for (const bad of [
  {{ ...source, source_id: "SRC-OTHER" }},
  {{ ...source, source_version: "0.9" }},
  {{ ...source, source_hash: "b".repeat(64) }},
  {{ ...source, source_generation: 2 }},
  {{ ...source, fact_id: "FACT-OTHER" }},
  {{ ...source, hotel_id: "HTL-OTHER" }},
]) assert.equal(validateSourceRefs({{ ...room, source_refs: [bad] }}, owners, facts), false);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                   text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(Path("/private/tmp/staylead-s7-batch2-cont5-cases.json").is_file(),
                         "requires coordinator-pinned independent case 8")
    def test_actual_case8_and_public_oracle_pass_shared_source_and_rate_guards(self):
        repo = Path(__file__).parents[2]
        cases = runtime._private_file(Path("/private/tmp/staylead-s7-batch2-cont5-cases.json"))
        oracle_path = repo / "docs/product/evidence/sprint-7/resumed-independent-expected-facts.json"
        oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
        case8 = cases["cases"][7]
        self.assertEqual(case8["expected_response_language"], "fr")
        self.assertEqual(case8["amendment"]["original_unattempted_case"]["turn"], 8)
        self.assertIn("2026-11-10", case8["utterance"])
        self.assertIn("2026-11-12", case8["utterance"])
        self.assertIn("Répondez en français", case8["utterance"])
        self.assertEqual(oracle["room_rates"]["PINE-LOFT"], 2_200_000)
        self.assertEqual(oracle["room_rates"]["PINE-GARDEN"], 2_500_000)
        self.assertEqual(oracle["room_rates"]["PINE-CABIN"], 4_100_000)

        repo_url = (repo / "tools/evals/sprint7_source_refs.mjs").as_uri()
        source_id, binding = next((source_id, value) for source_id, value in oracle["source_bindings"].items()
                                  if value["hotel_id"] == "HTL-RETREAT03")
        fact_id, fact_binding = next((fact_id, value) for fact_id, value in oracle["projected_fact_owners"].items()
                                     if value["hotel_id"] == "HTL-RETREAT03"
                                     and value["source_id"] == source_id)
        script = f'''import {{ validateSourceRefs }} from "{repo_url}";
import assert from "node:assert/strict";
const owner = {json.dumps(binding)};
const sourceId = {json.dumps(source_id)};
const factId = {json.dumps(fact_id)};
const room = {{ hotel_id: "HTL-RETREAT03", source_generation: owner.source_generation,
  source_refs: [{{ source_id: sourceId, source_version: owner.version,
    source_hash: owner.expected_hash, source_generation: owner.source_generation, fact_ids: [factId] }}] }};
const sources = new Map([[sourceId, owner]]);
const facts = new Map([[factId, {json.dumps(fact_binding)}]]);
assert.equal(validateSourceRefs(room, sources, facts), true);
assert.equal(validateSourceRefs({{ ...room, source_refs: [{{ ...room.source_refs[0], source_version: "0" }}] }}, sources, facts), false);
assert.equal(validateSourceRefs({{ ...room, source_refs: [{{ ...room.source_refs[0], source_hash: "0".repeat(64) }}] }}, sources, facts), false);
assert.equal(validateSourceRefs({{ ...room, source_refs: [{{ ...room.source_refs[0], source_generation: owner.source_generation + 1 }}] }}, sources, facts), false);
assert.equal(validateSourceRefs({{ ...room, source_refs: [{{ ...room.source_refs[0], fact_ids: ["unbound"] }}] }}, sources, facts), false);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                   text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_telemetry_allowlist_drops_utterances_answers_and_credentials(self):
        with self._env():
            runtime._event({"stage": "offline", "run_id": runtime.RUN_ID, "turn": 1,
                            "question": "secret guest utterance", "answer": "secret answer",
                            "token": "private token", "status": 200})
        text = self.events_path.read_text()
        self.assertNotIn("secret guest utterance", text)
        self.assertNotIn("secret answer", text)
        self.assertNotIn("private token", text)
        self.assertIn('"status": 200', text)

    def test_authorized_initializer_requires_exact_approval_candidate_and_never_overwrites(self):
        approval = self.root / "approval.json"
        manifest = self.root / "candidate.json"
        new_config = self.root / "new-runtime.json"
        new_state = self.root / "new-state.json"
        self._write(approval, {"run_id": runtime.RUN_ID, "authorized_for_live_calls": True,
            "authority": "approved offline synthetic fixture", "max_guest_turns": 9,
            "max_codex_requests": 18, "max_calls_per_turn": 2, "model": "gpt-6-luna",
            "effort": "low", "provider_timeout_seconds": 25.0,
            "turn_timeout_seconds": 45.0, "output_cap": 700,
            "continuation": self.continuation})
        candidate_record = {"run_id": runtime.RUN_ID, "matrix_sha256": self.matrix_sha,
            "oracle_sha256": self.oracle_sha, "live_cases_path": str(self.live_cases_path),
            "oracle_path": str(self.oracle_path), "source_files": self.source_files,
            "continuation": self.continuation}
        candidate_record["candidate_sha256"] = runtime._candidate_manifest_digest(candidate_record)
        self._write(manifest, candidate_record)
        runtime.prepare_private_run(approval_file=approval, candidate_manifest=manifest,
            config_path=new_config, state_path=new_state,
            database_url="postgresql://offline:test@localhost/db", session_signing_secret="synthetic")
        state = runtime._private_file(new_state)
        self.assertEqual(state["status"], "authorized")
        self.assertEqual(state["guest_turns"], runtime.PARENT_GUEST_TURNS)
        self.assertEqual(state["reserved_request_budget"], 18)
        before = new_state.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Refusing to initialize"):
            runtime.prepare_private_run(approval_file=approval, candidate_manifest=manifest,
                config_path=new_config, state_path=new_state,
                database_url="postgresql://offline:test@localhost/db", session_signing_secret="synthetic")
        self.assertEqual(new_state.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
