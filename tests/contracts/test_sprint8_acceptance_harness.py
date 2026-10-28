"""Offline-only control tests for the opt-in Sprint 8 acceptance harness."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location("sprint8_runtime_tested", ROOT / "tools/evals/sprint8_runtime.py")
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.cases = self.root / "cases.json"
        self.oracle = self.root / "oracle.json"
        self.manifest = self.root / "manifest.json"
        self.config_path = self.root / "config.json"
        self.state_path = self.root / "state.json"
        self.events = self.root / "events.jsonl"
        self._write(self.oracle, {"synthetic": True, "reviewed": True})
        self._write(self.cases, {"run_id": runtime.RUN_ID, "authorized_for_live_calls": True,
            "property": {"hotel_id": "HTL-S8-DEMO", "slug": "lotus-pilot-demo"},
            "limits": {"guest_turns": 4, "requests": 8, "calls_per_turn": 2,
                "provider_timeout_seconds": 25, "turn_timeout_seconds": 45, "max_output_tokens": 700,
                "model": runtime.MODEL, "effort": runtime.EFFORT, "automatic_retry": False,
                "fallback": False, "stop_at_first_blocking_failure": True},
            "cases": [{"id": f"s8-0{i}", "session": session, "input": f"case {i}"}
                for i, session in enumerate(("fresh-A", "fresh-B", "fresh-C", "same-C"), 1)]})
        prompt = Path(__file__).parents[2] / "apps/api/src/staylead_platform/domains/hospitality/prompts/grounded_qa.py"
        files = {"apps/api/src/staylead_platform/domains/hospitality/prompts/grounded_qa.py": self._hash(prompt)}
        m = {"schema_version": 1, "baseline": "12122f7d012c0617670438de5419efdc3d7729ab",
            "branch": "sprint-8-guide-shortlist", "scope": "apps, fixtures, product tests; new acceptance harness excluded and separately pinned",
            "files": files,
            "profile": {"max_guest_turns": 4, "max_requests": 8,
            "max_calls_per_turn": 2, "provider_timeout_seconds": 25, "turn_timeout_seconds": 45,
            "max_output_tokens": 700, "model": runtime.MODEL, "effort": runtime.EFFORT,
            "automatic_retry": False, "fallback": False, "stop_at_first_blocking_failure": True},
            "browser_executable": "/private/tmp/offline-test-chrome"}
        m["hash_method"] = "sha256(canonical JSON files map: sort_keys=True,separators=(comma,colon))"
        m["candidate_sha256"] = m["sha256"] = runtime._candidate_digest(files)
        self._write(self.manifest, m)
        self.manifest_patch = patch.object(runtime, "CANDIDATE_MANIFEST_PATH", self.manifest)
        self.manifest_patch.start()
        root = Path(__file__).parents[2]
        harness_files = {rel: self._hash(root / rel) for rel in runtime.HARNESS_FILES}
        self.config = {"run_id": runtime.RUN_ID, "authorized_for_live_calls": True,
            "authority": "offline fake-provider test", "candidate_sha256": m["candidate_sha256"],
            "browser_executable": m["browser_executable"],
            "case_sha256": self._hash(self.cases), "oracle_sha256": self._hash(self.oracle),
            "harness_files": harness_files, "live_cases_path": str(self.cases),
            "oracle_path": str(self.oracle), "database_url": "postgresql://localhost/offline",
            "session_signing_secret": "synthetic-only", **m["profile"]}
        self.config["harness_sha256"] = runtime._harness_digest(self.config)
        self.state = {"run_id": runtime.RUN_ID, "authorized_for_live_calls": True,
            "authority": "offline fake-provider test",
            "status": "authorized", "candidate_sha256": m["candidate_sha256"],
            "case_sha256": self.config["case_sha256"], "oracle_sha256": self.config["oracle_sha256"],
            "harness_sha256": self.config["harness_sha256"],
            "guest_turns": 0, "approved_case_turn": 0, "requests": 0, **m["profile"]}
        self._write(self.config_path, self.config); self._write(self.state_path, self.state)
        self.env = patch.dict(os.environ, {runtime.CONFIG_ENV: str(self.config_path), runtime.STATE_ENV: str(self.state_path), runtime.EVENTS_ENV: str(self.events)})
        self.env.start()
        self.lease_patch = patch.object(runtime, "LEASE_PATH", self.root / "lease")
        self.lease_patch.start()

    def tearDown(self):
        self.lease_patch.stop(); self.env.stop(); self.manifest_patch.stop(); runtime._release_lease(); self.temp.cleanup()

    @staticmethod
    def _hash(path: Path) -> str:
        import hashlib
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        path.chmod(0o600)

    def _state_now(self):
        return json.loads(self.state_path.read_text())

    def test_default_import_and_startup_are_offline_and_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "STAYLEAD_S8_LIVE_EVAL=1"):
            runtime.create_runtime_app()
        self.assertEqual((self._state_now()["guest_turns"], self._state_now()["requests"]), (0, 0))

    def test_browser_offline_smoke_never_starts_browser_or_calls_api(self):
        result = subprocess.run(["node", "tools/evals/sprint8_browser.mjs", "--offline-harness-smoke"],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
            env={key: value for key, value in os.environ.items() if not key.startswith("STAYLEAD_S8_")})
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["batch_namespace"], runtime.RUN_ID)
        self.assertEqual((report["guest_turn_cap"], report["request_cap"]), (4, 8))
        self.assertTrue(report["no_browser"] and report["no_api_or_model"])

    def test_failed_semantic_oracle_retains_attempt_response_render_counters_and_screenshot(self):
        report_path = self.root / "failed-oracle-evidence.json"
        result = subprocess.run(
            ["node", "tools/evals/sprint8_browser.mjs", "--offline-oracle-failure-smoke", str(report_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
            env={key: value for key, value in os.environ.items() if not key.startswith("STAYLEAD_S8_")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["status"], "offline-oracle-failure-evidence-ok")
        self.assertEqual(summary["verdict"]["reason"], "required_localized_phrase_missing")
        self.assertTrue(summary["localized_unknown_rendered"])
        self.assertTrue(summary["missing_localized_unknown_rejected"])
        self.assertEqual(report_path.stat().st_mode & 0o777, 0o600)
        report = json.loads(report_path.read_text())
        self.assertLess(report_path.stat().st_size, 128 * 1024)
        self.assertEqual(len(report["turns"]), 1)
        turn = report["turns"][0]
        evidence_path = Path(turn["evidence_path"])
        self.assertEqual(evidence_path.stat().st_mode & 0o777, 0o600)
        import hashlib
        self.assertEqual(turn["evidence_sha256"], hashlib.sha256(evidence_path.read_bytes()).hexdigest())
        evidence = json.loads(evidence_path.read_text())
        self.assertEqual(evidence["response"]["local_guide"]["supported_claims"][0]["venue_id"], "ATT-01")
        self.assertIn("请向场所确认当前营业时间。", evidence["rendered"]["text"])
        self.assertEqual(evidence["counter_snapshot"], {"guest_turns": 1, "approved_case_turn": 1, "requests": 2})
        screenshot = Path(evidence["screenshot"])
        self.assertTrue(screenshot.is_file())
        self.assertEqual(screenshot.stat().st_mode & 0o777, 0o600)
        self.assertEqual(turn["verdict"], summary["verdict"])

    def test_fresh_api_startup_handoff_and_current_turn_dom_selection_are_exact(self):
        self.assertTrue(runtime._valid_state(self.state, self.config, fresh=True))
        runtime._update(lambda state: state.update(status="running"))
        started = self._state_now()
        self.assertTrue(runtime._valid_state(started, self.config))
        script = """
import assert from 'node:assert/strict';
import { freshRuntimeHandoffReady, latestTurnForQuestion, hardNeedsPreserved } from './tools/evals/sprint8_browser_helpers.mjs';
const state = JSON.parse(process.argv[1]);
assert.equal(freshRuntimeHandoffReady(state), true, 'fresh running API state should hand off');
assert.equal(freshRuntimeHandoffReady({...state, requests: 1}), false, 'consumed state must not hand off');
const oldGuide = { venue: 'old same-session card' };
const newGuide = { venue: 'new current card' };
const turns = [
  { question: 'case 3 question', guide: oldGuide },
  { question: 'case 4 question', guide: newGuide },
];
assert.equal(latestTurnForQuestion(turns, 'case 4 question')?.guide, newGuide);
assert.equal(latestTurnForQuestion(turns, 'different question'), null);
const before = { local_guide_preferences: { hard_accessibility_needs: ['step_free', 'wheelchair_access'], allergy_requirements: ['peanut'] } };
const reordered = { local_guide_preferences: { hard_accessibility_needs: ['wheelchair_access', 'step_free'], allergy_requirements: ['peanut'] } };
assert.equal(hardNeedsPreserved(before, reordered), true);
assert.equal(hardNeedsPreserved(before, {...reordered, local_guide_preferences: {...reordered.local_guide_preferences, allergy_requirements: []}}), false);
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps(started)],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_proposed_case_matrix_does_not_authorize_startup(self):
        proposed = json.loads((ROOT / runtime.PROPOSED_CASES).read_text())
        self.assertIs(proposed["authorized_for_live_calls"], False)
        self.assertFalse(runtime._valid_state({**self.state, "authorized_for_live_calls": False}, self.config, fresh=True))

    def test_closed_acceptance_namespace_cannot_be_reused_by_reacceptance_controls(self):
        closed_run_id = "s8-local-guide-20261028-acceptance"
        self.assertEqual(runtime.RUN_ID, "s8-local-guide-20261028-reacceptance1")
        self.assertEqual(runtime.CASE_RUN_ID, runtime.RUN_ID)
        self.assertFalse(runtime._valid_state({**self.state, "run_id": closed_run_id}, self.config, fresh=True))
        self.assertFalse(runtime._valid_state(self.state, {**self.config, "run_id": closed_run_id}, fresh=True))

    def test_exact_case_order_and_same_session_are_persisted(self):
        with self.assertRaises(runtime.UnapprovedTurn):
            runtime.reserve_turn("id-a", "case 2")
        self.assertEqual(self._state_now()["guest_turns"], 0)
        self.assertEqual(runtime.reserve_turn("id-a", "case 1"), 1)
        self.assertEqual(runtime.reserve_turn("id-b", "case 2"), 2)
        self.assertEqual(runtime.reserve_turn("id-c", "case 3"), 3)
        with self.assertRaises(runtime.UnapprovedTurn):
            runtime.reserve_turn("other-session", "case 4")
        self.assertEqual(runtime.reserve_turn("id-c", "case 4"), 4)
        self.assertEqual(self._state_now()["sessions"], {"fresh-A": "id-a", "fresh-B": "id-b", "fresh-C": "id-c"})

    def test_request_reserved_before_attempt_and_failure_halts_without_retry(self):
        runtime.reserve_turn("id-a", "case 1")
        class Provider:
            async def generate(self, request):
                raise TimeoutError("synthetic provider failure")
        provider = runtime._observed(Provider())
        token = runtime.TURN.set({"number": 1, "calls": 0})
        try:
            with self.assertRaises(TimeoutError):
                asyncio.run(provider.generate(SimpleNamespace(max_output_tokens=700, input_text="x", instructions="y")))
        finally:
            runtime.TURN.reset(token)
        state = self._state_now()
        self.assertEqual((state["requests"], state["status"]), (1, "halted"))
        with self.assertRaisesRegex(RuntimeError, "halted"):
            runtime.reserve_turn("id-a", "case 1")

    def test_provider_timeout_is_enforced_after_reservation(self):
        runtime.reserve_turn("id-a", "case 1")
        class SlowProvider:
            async def generate(self, request):
                await asyncio.sleep(0.03)
                return SimpleNamespace(text="{}", usage=None)
        provider = runtime._observed(SlowProvider())
        token = runtime.TURN.set({"number": 1, "calls": 0})
        real_timeout = asyncio.timeout
        try:
            with patch.object(runtime.asyncio, "timeout", lambda _seconds: real_timeout(0.001)), self.assertRaises(TimeoutError):
                asyncio.run(provider.generate(SimpleNamespace(max_output_tokens=700, input_text="", instructions="")))
        finally:
            runtime.TURN.reset(token)
        self.assertEqual((self._state_now()["requests"], self._state_now()["status"]), (1, "halted"))

    def test_each_turn_has_two_call_cap_and_global_request_cap(self):
        runtime.reserve_turn("id-a", "case 1")
        token = runtime.TURN.set({"number": 1, "calls": 0})
        try:
            self.assertEqual(runtime.reserve_request(), 1)
            self.assertEqual(runtime.reserve_request(), 2)
            with self.assertRaisesRegex(RuntimeError, "two-request"):
                runtime.reserve_request()
        finally:
            runtime.TURN.reset(token)
        self.assertEqual(self._state_now()["requests"], 2)

    def test_global_eight_request_cap_and_provider_output_cap(self):
        for session, question in (("id-a", "case 1"), ("id-b", "case 2"), ("id-c", "case 3"), ("id-c", "case 4")):
            turn = runtime.reserve_turn(session, question)
            token = runtime.TURN.set({"number": turn, "calls": 0})
            try:
                runtime.reserve_request(); runtime.reserve_request()
            finally:
                runtime.TURN.reset(token)
        turn_token = runtime.TURN.set({"number": 4, "calls": 0})
        try:
            with self.assertRaisesRegex(RuntimeError, "request cap"):
                runtime.reserve_request()
        finally:
            runtime.TURN.reset(turn_token)
        class Provider:
            async def generate(self, request):
                return SimpleNamespace(text="{}", usage=None)
        wrapped = runtime._observed(Provider())
        token = runtime.TURN.set({"number": 4, "calls": 0})
        try:
            with self.assertRaisesRegex(RuntimeError, "output cap"):
                asyncio.run(wrapped.generate(SimpleNamespace(max_output_tokens=701, input_text="", instructions="")))
        finally:
            runtime.TURN.reset(token)
        self.assertEqual(self._state_now()["requests"], 8)

    def test_duplicate_process_lease_is_refused(self):
        runtime._acquire_lease()
        first = runtime.LEASE_FD
        runtime.LEASE_FD = None
        try:
            with self.assertRaisesRegex(RuntimeError, "holds the process lease"):
                runtime._acquire_lease()
        finally:
            runtime.LEASE_FD = first

    def test_reload_cannot_reuse_started_or_consumed_namespace(self):
        state = self._state_now(); state["status"] = "running"; state["guest_turns"] = 1; state["approved_case_turn"] = 1
        self._write(self.state_path, state)
        self.assertFalse(runtime._valid_state(state, self.config, fresh=True))

    def test_candidate_or_case_change_blocks_before_reservation(self):
        raw = self.cases.read_text().replace("case 1", "changed case 1")
        self.cases.write_text(raw); self.cases.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, "cases or independent oracle pin changed"):
            runtime.reserve_turn("id-a", "case 1")
        self.assertEqual(self._state_now()["guest_turns"], 0)

    def test_control_files_must_be_private_regular_files(self):
        self.state_path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "0600"):
            runtime._private(self.state_path)


if __name__ == "__main__":
    unittest.main()
