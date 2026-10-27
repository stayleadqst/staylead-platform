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
        self._write(self.live_cases_path, {"run_id": runtime.CASE_RUN_ID, "cases": []})
        self.matrix_sha = runtime._file_sha256(self.live_cases_path)
        self._write(self.oracle_path, {"synthetic": True})
        self.oracle_sha = runtime._file_sha256(self.oracle_path)
        self.prior_allocation = runtime._prior_allocation_record()
        source_rel = str(Path(__file__).relative_to(Path(__file__).parents[2]))
        self.source_files = {source_rel: runtime._file_sha256(Path(__file__))}
        manifest = {"run_id": runtime.RUN_ID, "matrix_sha256": self.matrix_sha,
                    "oracle_sha256": self.oracle_sha, "source_files": self.source_files,
                    "live_cases_path": str(self.live_cases_path), "oracle_path": str(self.oracle_path),
                    "prior_allocation": self.prior_allocation, "continuation": None}
        self.candidate_sha = runtime._candidate_manifest_digest(manifest)
        manifest["candidate_sha256"] = self.candidate_sha
        self.config = {
            "run_id": runtime.RUN_ID, "authority": "offline synthetic test",
            "candidate_sha256": self.candidate_sha, "matrix_sha256": self.matrix_sha,
            "oracle_sha256": self.oracle_sha, "provider": "codex_cli", "model": runtime.MODEL,
            "effort": runtime.EFFORT, "database_url": "postgresql://offline:test@localhost/db",
            "session_signing_secret": "synthetic-test-secret",
            "candidate_manifest_path": str(self.manifest_path),
            "live_cases_path": str(self.live_cases_path), "oracle_path": str(self.oracle_path),
            "prior_allocation": self.prior_allocation, "continuation": None,
        }
        self._write(self.manifest_path, manifest)
        self.state = {
            "run_id": runtime.RUN_ID, "authority": "offline synthetic test",
            "candidate_sha256": self.candidate_sha, "matrix_sha256": self.matrix_sha,
            "authorized_for_live_calls": True, "status": "authorized",
            "max_guest_turns": runtime.MAX_GUEST_TURNS, "max_codex_requests": runtime.MAX_REQUESTS,
            "max_calls_per_turn": runtime.MAX_CALLS_PER_TURN,
            "reserved_guest_turn_budget": runtime.MAX_GUEST_TURNS, "reserved_request_budget": runtime.MAX_REQUESTS,
            "guest_turns": 0, "codex_requests": 0, "approved_case_turn": 0,
            "prior_allocation_state_sha256": runtime.PRIOR_STATE_SHA256,
        }
        self._write(self.config_path, self.config)
        self._write(self.state_path, self.state)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        path.chmod(0o600)

    @contextlib.contextmanager
    def _env(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                runtime.CONFIG_ENV: str(self.config_path), runtime.STATE_ENV: str(self.state_path),
                runtime.EVENTS_ENV: str(self.events_path),
            }, clear=True))
            stack.enter_context(patch.object(runtime, "_verify_closed_prior_allocation", return_value={}))
            yield

    def _replace_cases(self, utterances: list[str]) -> None:
        matrix = {"run_id": runtime.CASE_RUN_ID, "cases": [
            {"turn": index, "utterance": text} for index, text in enumerate(utterances, start=1)
        ]}
        self._write(self.live_cases_path, matrix)
        self.matrix_sha = runtime._file_sha256(self.live_cases_path)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["matrix_sha256"] = self.matrix_sha
        manifest["candidate_sha256"] = runtime._candidate_manifest_digest(manifest)
        self._write(self.manifest_path, manifest)
        self.config.update(matrix_sha256=self.matrix_sha, candidate_sha256=manifest["candidate_sha256"])
        self.state.update(matrix_sha256=self.matrix_sha, candidate_sha256=manifest["candidate_sha256"])
        self._write(self.config_path, self.config)
        self._write(self.state_path, self.state)

    @contextlib.contextmanager
    def _lease(self):
        with patch.object(runtime, "LEASE_PATH", self.root / "process.lock"):
            runtime._acquire_process_lease()
            try:
                yield
            finally:
                runtime._release_process_lease()

    def test_offline_smoke_exits_without_private_state_browser_or_api(self):
        repo = Path(__file__).parents[2]
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("STAYLEAD_S7_") and key != "STAYLEAD_LIVE_EVAL"}
        result = subprocess.run(["node", "tools/evals/sprint7_browser.mjs", "--offline-harness-smoke"],
            cwd=repo, env=env, text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["batch_namespace"], runtime.RUN_ID)
        self.assertEqual((report["guest_turn_cap"], report["request_cap"]), (2, 4))
        self.assertEqual(report["fresh_counters"], {"guest_turns": 0, "codex_requests": 0})
        self.assertTrue(report["no_browser"] and report["no_api_or_model"])

    def test_fresh_caps_and_closed_prior_receipt_are_exact(self):
        self.assertTrue(runtime._valid_state(self.state, self.config, fresh=True))
        self.assertEqual(runtime.RUN_ID, "s7-room-advice-20261027-reacceptance4")
        self.assertEqual(runtime.CASE_RUN_ID, runtime.RUN_ID)
        self.assertEqual((runtime.MAX_GUEST_TURNS, runtime.MAX_REQUESTS, runtime.MAX_CALLS_PER_TURN), (2, 4, 2))
        self.assertEqual((runtime.PROVIDER_TIMEOUT_SECONDS, runtime.TURN_TIMEOUT_SECONDS,
                          runtime.MAX_OUTPUT_TOKENS, runtime.MODEL, runtime.EFFORT),
                         (25.0, 45.0, 700, "gpt-6-luna", "low"))
        prior = runtime._prior_allocation_record()
        self.assertEqual((prior["guest_turns"], prior["codex_requests"], prior["lifetime_requests"]), (4, 8, 44))
        self.assertEqual(prior["state_sha256"], runtime.PRIOR_STATE_SHA256)
        for changed in (
            {**self.state, "max_guest_turns": 3},
            {**self.state, "max_codex_requests": 5},
            {**self.state, "guest_turns": 1, "approved_case_turn": 1},
            {**self.state, "codex_requests": True},
            {**self.state, "prior_allocation_state_sha256": "0" * 64},
            {**self.state, "candidate_sha256": "d" * 64},
        ):
            self.assertFalse(runtime._valid_state(changed, self.config, fresh=True))
        self.assertFalse(runtime._valid_state(self.state, {**self.config, "continuation": {}}))
        altered = dict(prior, codex_requests=12)
        with self.assertRaisesRegex(RuntimeError, "exact closed immutable receipt"):
            runtime._verify_closed_prior_allocation(altered)

    def test_old_authorization_cannot_be_reused_for_new_namespace(self):
        old_state = {**self.state, "run_id": runtime.PRIOR_RUN_ID}
        old_config = {**self.config, "run_id": runtime.PRIOR_RUN_ID}
        self.assertFalse(runtime._valid_state(old_state, old_config))
        self.assertNotEqual(runtime.LEASE_PATH.name, f"staylead-s7-{runtime.PRIOR_RUN_ID}.process.lock")

    def test_explicit_live_opt_in_and_0600_private_file_are_required(self):
        with self._env(), self.assertRaisesRegex(RuntimeError, "STAYLEAD_LIVE_EVAL=1"):
            runtime.create_runtime_app()
        self.state_path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "0600"):
            runtime._private_file(self.state_path)

    def test_fresh_start_is_one_shot_and_restart_cannot_reset_or_resume(self):
        with self._lease(), self._env():
            runtime._transition_status("starting")
            runtime._transition_status("running")
            started = json.loads(self.state_path.read_text())
            self.assertEqual(started["status"], "running")
            self.assertEqual((started["guest_turns"], started["codex_requests"]), (0, 0))
            with self.assertRaisesRegex(RuntimeError, "authorization"):
                runtime._transition_status("starting")
            self.assertEqual(json.loads(self.state_path.read_text()), started)

    def test_zero_consumption_bootstrap_failure_can_only_retry_same_fresh_namespace(self):
        with self._lease(), self._env():
            runtime._transition_status("starting")
            self.assertTrue(runtime._release_bootstrap_if_unused("bind-failed"))
        after = json.loads(self.state_path.read_text())
        self.assertEqual((after["status"], after["guest_turns"], after["codex_requests"]), ("authorized", 0, 0))
        self.assertEqual(after["start_attempts"], 1)
        with self._lease(), self._env():
            runtime._transition_status("starting")

    def test_duplicate_process_lease_fails_closed(self):
        with self._lease():
            first_fd = runtime.LEASE_FD
            runtime.LEASE_FD = None
            try:
                with (patch.object(runtime, "LEASE_PATH", self.root / "process.lock"),
                      self.assertRaisesRegex(RuntimeError, "already holds the process lease")):
                    runtime._acquire_process_lease()
            finally:
                runtime.LEASE_FD = first_fd

    def test_question_allowlist_rejects_before_turn_reservation(self):
        self._replace_cases(["approved one", "approved two"])
        self.state["status"] = "running"
        self._write(self.state_path, self.state)
        with self._lease(), self._env():
            with self.assertRaisesRegex(runtime._UnapprovedGuestTurn, "next approved case"):
                runtime._reserve_approved_guest_turn("unapproved arbitrary question")
            self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 0)
            self.assertEqual(runtime._reserve_approved_guest_turn("approved one"), 1)
            with self.assertRaisesRegex(runtime._UnapprovedGuestTurn, "next approved case"):
                runtime._reserve_approved_guest_turn("approved three")
            self.assertEqual(runtime._reserve_approved_guest_turn("approved two"), 2)
        final = json.loads(self.state_path.read_text())
        self.assertEqual((final["guest_turns"], final["approved_case_turn"], final["codex_requests"]), (2, 2, 0))

    def test_middleware_rejects_unapproved_text_without_slot_or_provider_call(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from staylead_platform.composition.dependencies import guest_chat
        from staylead_platform.entrypoints import app as app_module

        self._replace_cases(["approved one", "approved two"])

        class CountingProvider:
            calls = 0
            async def generate(self, request):
                self.calls += 1
                return SimpleNamespace(text='{"ok":true}', usage=SimpleNamespace(
                    input_tokens=1, output_tokens=1, total_tokens=2))

        provider = CountingProvider()
        def fake_app(_settings, *, provider):
            app = FastAPI()
            @app.post("/v1/guest/sessions/test/messages")
            async def messages():
                await provider.generate(SimpleNamespace(input_text="approved", instructions="bounded",
                                                        max_output_tokens=700))
                return {"ok": True}
            return app

        with self._env(), patch.dict(os.environ, {runtime.LIVE_ENV: "1"}), \
                patch.object(runtime, "LEASE_PATH", self.root / "runtime.lock"), \
                patch.object(runtime.shutil, "which", return_value="/fake/codex"), \
                patch.object(guest_chat, "build_provider", return_value=provider), \
                patch.object(app_module, "create_app", side_effect=fake_app):
            app = runtime.create_runtime_app()
            try:
                with TestClient(app) as client:
                    rejected = client.post("/v1/guest/sessions/test/messages", json={"question": "arbitrary"})
                    self.assertEqual(rejected.status_code, 400)
                    self.assertEqual(rejected.json()["error"]["code"], "unapproved_guest_turn")
                    self.assertEqual((provider.calls, json.loads(self.state_path.read_text())["guest_turns"],
                                      json.loads(self.state_path.read_text())["codex_requests"]), (0, 0, 0))
                    accepted = client.post("/v1/guest/sessions/test/messages", json={"question": "approved one"})
                    self.assertEqual(accepted.status_code, 200)
                    current = json.loads(self.state_path.read_text())
                    self.assertEqual((provider.calls, current["guest_turns"], current["codex_requests"]), (1, 1, 1))
            finally:
                runtime._release_process_lease()

    def test_case_and_oracle_hashes_are_checked_before_reservation(self):
        self._replace_cases(["approved one", "approved two"])
        self.state["status"] = "running"
        self._write(self.state_path, self.state)
        original = self.live_cases_path.read_bytes()
        self.live_cases_path.write_text('{"cases":["changed"]}', encoding="utf-8")
        with self._lease(), self._env(), self.assertRaisesRegex(RuntimeError, "case matrix or independent oracle changed"):
            runtime._reserve("guest_turns", runtime.MAX_GUEST_TURNS, "guest turn")
        self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 0)
        self.live_cases_path.write_bytes(original)
        with self._lease(), self._env():
            self.assertEqual(runtime._reserve("guest_turns", runtime.MAX_GUEST_TURNS, "guest turn"), 1)

    def test_provider_failure_keeps_reserved_request_and_halts(self):
        class BrokenProvider:
            async def generate(self, request):
                raise TimeoutError("synthetic timeout")
        request = SimpleNamespace(input_text="synthetic", instructions="bounded", max_output_tokens=700)
        self.state["status"] = "running"
        self._write(self.state_path, self.state)
        token = runtime.TURN.set({"guest_turn": 1, "calls": 0, "request_id": "synthetic", "synthetic_pinned": False})
        try:
            with self._lease(), self._env(), self.assertRaises(TimeoutError):
                asyncio.run(runtime._observed_provider(BrokenProvider()).generate(request))
        finally:
            runtime.TURN.reset(token)
        after = json.loads(self.state_path.read_text())
        self.assertEqual((after["codex_requests"], after["guest_turns"], after["status"]), (1, 0, "halted"))
        self.assertEqual(after["stop_reason"], "provider_failure")

    def test_two_calls_and_700_token_cap_are_enforced_before_launch(self):
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
        self.state["status"] = "running"
        self._write(self.state_path, self.state)
        token = runtime.TURN.set({"guest_turn": 1, "calls": 0, "request_id": "request-1", "synthetic_pinned": False})
        request = SimpleNamespace(input_text="synthetic", instructions="bounded", max_output_tokens=700)
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
        self.assertEqual((provider.calls, json.loads(self.state_path.read_text())["codex_requests"]), (2, 2))

    def test_browser_turn_mapping_selects_only_current_positive_cases(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ selectionOptionForAcceptanceTurn }} from "{helper}";
import assert from "node:assert/strict";
const room = {{ options: [{{ option_id: "current" }}] }};
assert.equal(selectionOptionForAcceptanceTurn(2, room), room.options[0]);
for (const turn of [1, 3, 4]) assert.equal(selectionOptionForAcceptanceTurn(turn, room), null);
assert.equal(selectionOptionForAcceptanceTurn(1, {{ status: "needs_clarification", options: [] }}), null);
assert.equal(selectionOptionForAcceptanceTurn(5, room), null);
'''
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_pine_brief_guard_rejects_unrequested_budget_on_both_turns(self):
        repo = Path(__file__).parents[2]
        browser = repo / "tools/evals/sprint7_browser.mjs"
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import fs from "node:fs";
import assert from "node:assert/strict";
import {{ checkPinePartyBrief, retainsTwoHardAccessibilityNeeds }} from "{helper}";
const source = fs.readFileSync({json.dumps(str(browser))}, "utf8");
const start = source.indexOf("function checkBrief(");
assert.notEqual(start, -1);
const open = source.indexOf("{{", start);
let depth = 0;
let end = -1;
for (let index = open; index < source.length; index += 1) {{
  if (source[index] === "{{") depth += 1;
  if (source[index] === "}}" && --depth === 0) {{ end = index + 1; break; }}
}}
assert.notEqual(end, -1);
const expectedBrief = {{
  1: {{ adults: 1, children: [7], dates: ["2026-11-10", "2026-11-12", 2] }},
  2: {{ adults: 1, children: [8], dates: ["2026-11-10", "2026-11-12", 2] }},
}};
const members = new Map([["fresh-pine", "child-current-id"]]);
const checkBrief = new Function("expectedBrief", "childIdsBySession", "checkPinePartyBrief",
  "retainsTwoHardAccessibilityNeeds", "assert", `${{source.slice(start, end)}}; return checkBrief;`) (
    expectedBrief, members, checkPinePartyBrief, retainsTwoHardAccessibilityNeeds,
    (condition, message) => {{ if (!condition) throw new Error(message); }});
function brief(age) {{ return {{ party: {{ adults: 1, children: [{{ member_id: "child-current-id", age }}],
  guardians: {{ "child-current-id": "adult-1" }}, bed_sharing: [{{
    member_ids: ["adult-1", "child-current-id"], allow_share: true }}] }},
  dates: {{ check_in: "2026-11-10", check_out: "2026-11-12", nights: 2 }},
  pending_fields: [], room_requirements: {{ hard_accessibility_needs: age === 7 ? ["step_free", "wheelchair_bathroom"] : [],
    hard_bed_types: [] }} }}; }}
assert.equal(checkBrief(1, brief(7)), "child-current-id");
assert.equal(checkBrief(2, brief(8)), "child-current-id");
for (const turn of [1, 2]) assert.throws(() => checkBrief(turn, {{ ...brief(turn === 1 ? 7 : 8),
  room_requirements: {{ ...brief(turn === 1 ? 7 : 8).room_requirements, budget_amount: 1 }} }}),
  /invented an unrequested budget/);
for (const turn of [1, 2]) {{
  const current = brief(turn === 1 ? 7 : 8);
  assert.throws(() => checkBrief(turn, {{ ...current, room_requirements: {{
    ...current.room_requirements, hard_bed_types: ["king"] }} }}), /invented or left pending/);
  assert.throws(() => checkBrief(turn, {{ ...current, pending_fields: ["room_requirements.hard_bed_types"] }}),
    /invented or left pending/);
}}
'''
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_city2_approved_branch_requires_no_share_intent_without_invented_bed_type(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ checkCity2Brief, hasDistinctAssignedBeds }} from "{helper}";
import assert from "node:assert/strict";
const approvedBrief = {{ party: {{ bed_sharing: [{{ member_ids: ["adult-1", "adult-2"], allow_share: false }}] }},
  room_requirements: {{ budget_amount: 6500000, budget_strength: "hard", hard_bed_types: [] }} }};
assert.equal(checkCity2Brief(approvedBrief), true);
const option = {{ assignments: [
  {{ member_id: "adult-1", room_index: 0, bed_index: 0, bed_type: "single" }},
  {{ member_id: "adult-2", room_index: 0, bed_index: 1, bed_type: "single" }}
] }};
assert.equal(hasDistinctAssignedBeds(option, ["adult-1", "adult-2"]), true);
assert.equal(hasDistinctAssignedBeds({{ assignments: [option.assignments[0],
  {{ ...option.assignments[1], bed_index: 0 }}] }}, ["adult-1", "adult-2"]), false);
assert.equal(checkCity2Brief({{ ...approvedBrief, party: {{ bed_sharing: [
  {{ member_ids: ["adult-1", "adult-2"], allow_share: true }}] }} }}), false);
assert.equal(checkCity2Brief({{ ...approvedBrief, room_requirements: {{ ...approvedBrief.room_requirements,
  hard_bed_types: ["twin"] }} }}), false);
'''
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_city_option_and_pine_party_checks_accept_canonical_producer_shapes(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ hasUsefulRoomOptions, checkPinePartyBrief }} from "{helper}";
import assert from "node:assert/strict";
const cityTwnOnly = {{ options: [{{ rooms: [{{ room_type_id: "CITY-TWN" }}],
  assignments: [{{ member_id: "adult-1" }}, {{ member_id: "adult-2" }}] }}] }};
assert.equal(hasUsefulRoomOptions(cityTwnOnly), true);
assert.equal(hasUsefulRoomOptions({{ options: [] }}), false);
const pine = {{ party: {{ adults: 1, children: [{{ member_id: "child-current-id", age: 7 }}],
  guardians: {{ "child-current-id": "adult-1" }}, bed_sharing: [
    {{ member_ids: ["adult-1", "child-current-id"], allow_share: true }}] }} }};
assert.equal(checkPinePartyBrief(pine, 7), "child-current-id");
assert.equal(checkPinePartyBrief({{ ...pine, party: {{ ...pine.party, children: [
  {{ ...pine.party.children[0], member_id: "invented-child" }}] }} }}, 7), null);
assert.equal(checkPinePartyBrief({{ ...pine, party: {{ ...pine.party, bed_sharing: [] }} }}, 7), null);
'''
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(Path("/private/tmp/staylead-s7-reacceptance4-cases.json").is_file()
                         and Path("/private/tmp/staylead-s7-reacceptance4-authority.json").is_file(),
                         "requires the coordinator-approved private reacceptance4 matrix")
    def test_approved_matrix_exact_digest_two_pine_turns_and_prior_receipt(self):
        private_path = Path("/private/tmp/staylead-s7-reacceptance4-cases.json")
        cases = runtime._private_file(private_path)
        self.assertEqual(runtime._file_sha256(private_path),
                         "dd7119bd77b717d22a15b1a3d381ee3351ae4e00678944bfcaa526577222832a")
        self.assertEqual(cases["run_id"], runtime.RUN_ID)
        self.assertTrue(cases["authorized_for_live_calls"])
        self.assertEqual((cases["proposed_max_guest_turns"], cases["proposed_max_requests"],
                          cases["max_calls_per_turn"], len(cases["cases"])), (2, 4, 2, 2))
        self.assertEqual([case["session"] for case in cases["cases"]], ["fresh-pine", "fresh-pine"])
        self.assertEqual([case["turn"] for case in cases["cases"]], [1, 2])
        self.assertEqual([case["source_case"] for case in cases["cases"]], [7, 8])
        self.assertEqual([case["approved_previous_turn"] for case in cases["cases"]], [6, 7])
        self.assertEqual(cases["no_automatic_retry"], True)
        self.assertEqual(cases["stop_at_first_blocking_failure"], True)
        authority_path = Path("/private/tmp/staylead-s7-reacceptance4-authority.json")
        authority = runtime._private_file(authority_path)
        self.assertEqual(authority["run_id"], runtime.RUN_ID)
        self.assertEqual(authority["case_matrix_sha256"], runtime._file_sha256(private_path))
        self.assertEqual((authority["max_guest_turns"], authority["max_codex_requests"],
                          authority["max_calls_per_turn"]), (2, 4, 2))
        self.assertIsNone(authority["continuation"])
        self.assertEqual(authority["prior_allocation"], runtime._prior_allocation_record())
        prior = runtime._prior_allocation_record()
        runtime._verify_closed_prior_allocation(prior)
        self.assertEqual((prior["run_id"], prior["guest_turns"], prior["codex_requests"],
                          prior["lifetime_requests"], prior["state_sha256"]),
                         (runtime.PRIOR_RUN_ID, 4, 8, 44, runtime.PRIOR_STATE_SHA256))

    def test_browser_run_directory_is_unique_to_reacceptance4_namespace(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ browserRunDirectory }} from "{helper}";
import assert from "node:assert/strict";
assert.equal(browserRunDirectory("s7-room-advice-20261027-reacceptance4", "r1"),
  "/private/tmp/staylead-s7-browser-s7-room-advice-20261027-reacceptance4-r1");
assert.throws(() => browserRunDirectory("../overwrite", "r2"), /Invalid private browser run directory/);
'''
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_semantic_receipt_binds_run_candidate_turn_and_exact_response(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ semanticReviewReceiptValid }} from "{helper}";
import assert from "node:assert/strict";
const expected = {{ run_id: "run", candidate_sha256: "a".repeat(64), approved_case_turn: 2,
  response_sha256: "b".repeat(64) }};
assert.equal(semanticReviewReceiptValid({{ ...expected, verdict: "pass" }}, expected), true);
for (const bad of [{{ ...expected, verdict: "fail" }}, {{ ...expected, approved_case_turn: 3 }},
  {{ ...expected, response_sha256: "c".repeat(64) }}, null])
  assert.equal(semanticReviewReceiptValid(bad, expected), false);
'''
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_telemetry_allowlist_drops_sensitive_payload(self):
        with self._env():
            runtime._event({"stage": "offline", "run_id": runtime.RUN_ID, "turn": 1,
                            "question": "private utterance", "answer": "private answer", "token": "secret", "status": 200})
        value = self.events_path.read_text()
        self.assertNotIn("private utterance", value)
        self.assertNotIn("private answer", value)
        self.assertNotIn("secret", value)
        self.assertIn('"status": 200', value)

    def test_initializer_binds_fresh_approval_to_matrix_candidate_and_never_overwrites(self):
        self._replace_cases(["approved one", "approved two"])
        approval = self.root / "approval.json"
        config_path = self.root / "new-runtime.json"
        state_path = self.root / "new-state.json"
        record = {"run_id": runtime.RUN_ID, "authorized_for_live_calls": True,
            "authority": "approved synthetic test", "max_guest_turns": 2, "max_codex_requests": 4,
            "max_calls_per_turn": 2, "model": runtime.MODEL, "effort": runtime.EFFORT,
            "provider_timeout_seconds": 25, "turn_timeout_seconds": 45, "output_cap": 700,
            "case_matrix_sha256": self.matrix_sha, "prior_allocation": self.prior_allocation,
            "continuation": None}
        self._write(approval, record)
        record["case_matrix_sha256"] = "0" * 64
        self._write(approval, record)
        with self.assertRaisesRegex(RuntimeError, "Approval does not authorize"):
            runtime.prepare_private_run(approval_file=approval, candidate_manifest=self.manifest_path,
                config_path=config_path, state_path=state_path, database_url="postgresql://offline/db",
                session_signing_secret="synthetic")
        self.assertFalse(config_path.exists() or state_path.exists())
        record["case_matrix_sha256"] = self.matrix_sha
        self._write(approval, record)
        with patch.object(runtime, "_verify_closed_prior_allocation", return_value={}):
            runtime.prepare_private_run(approval_file=approval, candidate_manifest=self.manifest_path,
                config_path=config_path, state_path=state_path, database_url="postgresql://offline/db",
                session_signing_secret="synthetic")
        new_state = runtime._private_file(state_path)
        self.assertEqual((new_state["guest_turns"], new_state["codex_requests"],
                          new_state["reserved_guest_turn_budget"], new_state["reserved_request_budget"]), (0, 0, 2, 4))
        self.assertIsNone(runtime._private_file(config_path)["continuation"])
        before = state_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Refusing to initialize"):
            runtime.prepare_private_run(approval_file=approval, candidate_manifest=self.manifest_path,
                config_path=config_path, state_path=state_path, database_url="postgresql://offline/db",
                session_signing_secret="synthetic")
        self.assertEqual(state_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
