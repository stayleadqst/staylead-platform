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
        source_rel = str(Path(__file__).relative_to(Path(__file__).parents[2]))
        self.source_files = {source_rel: runtime._file_sha256(Path(__file__))}
        manifest = {"run_id": runtime.RUN_ID, "matrix_sha256": self.matrix_sha,
                    "oracle_sha256": self.oracle_sha, "source_files": self.source_files,
                    "live_cases_path": str(self.live_cases_path), "oracle_path": str(self.oracle_path)}
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
        }
        self._write(self.manifest_path, manifest)
        self.state = {
            "run_id": runtime.RUN_ID, "authority": "offline synthetic test",
            "candidate_sha256": self.candidate_sha, "matrix_sha256": self.matrix_sha,
            "authorized_for_live_calls": True, "status": "authorized",
            "max_guest_turns": 9, "max_codex_requests": 18, "max_calls_per_turn": 2,
            "reserved_guest_turn_budget": 9, "reserved_request_budget": 18,
            "guest_turns": 0, "codex_requests": 0,
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

    def test_browser_oracle_loader_smoke_exits_before_state_or_browser_setup(self):
        repo = Path(__file__).parents[2]
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("STAYLEAD_S7_") and key != "STAYLEAD_LIVE_EVAL"}
        completed = subprocess.run(
            ["node", "tools/evals/sprint7_browser.mjs", "--oracle-loader-smoke"],
            cwd=repo, env=env, text=True, capture_output=True, check=False, timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(output["status"], "offline-source-loader-ok")
        self.assertGreater(output["source_count"], 0)
        self.assertEqual(output["source_owner_count"], output["source_count"])
        self.assertTrue(output["no_browser"])
        self.assertTrue(output["no_api_or_model"])

    def test_frozen_caps_and_prelaunch_reservations_are_validated(self):
        self.assertTrue(runtime._valid_state(self.state, self.config, fresh=True))
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
            self.assertEqual((after_start["guest_turns"], after_start["codex_requests"]), (0, 0))
            with self.assertRaisesRegex(RuntimeError, "authorization"):
                runtime._transition_status("starting")
            self.assertEqual(json.loads(self.state_path.read_text()), after_start)

    def test_zero_consumption_bootstrap_failure_releases_same_namespace_for_restart(self):
        with self._lease(), self._env():
            runtime._transition_status("starting")
            self.assertTrue(runtime._release_bootstrap_if_unused("bind-failed"))
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after["status"], "authorized")
        self.assertEqual(after["guest_turns"], 0)
        self.assertEqual(after["codex_requests"], 0)
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
        self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 0)
        self.live_cases_path.write_bytes(original)
        with self._lease(), self._env():
            self.assertEqual(runtime._reserve("guest_turns", 9, "guest turn"), 1)
        self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 1)

    def test_provider_failure_keeps_reserved_counter_and_halts_run(self):
        class BrokenProvider:
            async def generate(self, request):
                raise TimeoutError("synthetic timeout")

        request = SimpleNamespace(input_text="synthetic utterance", instructions="synthetic instructions",
                                  max_output_tokens=700)
        self.state.update(status="running", guest_turns=1)
        self._write(self.state_path, self.state)
        turn = {"guest_turn": 1, "calls": 0, "request_id": "synthetic-request", "synthetic_pinned": False}
        token = runtime.TURN.set(turn)
        try:
            with self._lease(), self._env(), self.assertRaises(TimeoutError):
                asyncio.run(runtime._observed_provider(BrokenProvider()).generate(request))
        finally:
            runtime.TURN.reset(token)
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after["codex_requests"], 1)
        self.assertEqual(after["guest_turns"], 1)
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
        self.state.update(status="running", guest_turns=1)
        self._write(self.state_path, self.state)
        turn = {"guest_turn": 1, "calls": 0, "request_id": "request-1", "synthetic_pinned": False}
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
        self.assertEqual(json.loads(self.state_path.read_text())["codex_requests"], 2)
        rows = [json.loads(line) for line in self.events_path.read_text().splitlines()]
        self.assertEqual(sum(row["stage"] == "provider_completed" for row in rows), 2)
        self.assertTrue(all("input_text" not in row and "instructions" not in row for row in rows))

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
            "turn_timeout_seconds": 45.0, "output_cap": 700})
        candidate_record = {"run_id": runtime.RUN_ID, "matrix_sha256": self.matrix_sha,
            "oracle_sha256": self.oracle_sha, "live_cases_path": str(self.live_cases_path),
            "oracle_path": str(self.oracle_path), "source_files": self.source_files}
        candidate_record["candidate_sha256"] = runtime._candidate_manifest_digest(candidate_record)
        self._write(manifest, candidate_record)
        runtime.prepare_private_run(approval_file=approval, candidate_manifest=manifest,
            config_path=new_config, state_path=new_state,
            database_url="postgresql://offline:test@localhost/db", session_signing_secret="synthetic")
        state = runtime._private_file(new_state)
        self.assertEqual(state["status"], "authorized")
        self.assertEqual(state["guest_turns"], 0)
        self.assertEqual(state["reserved_request_budget"], 18)
        before = new_state.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Refusing to initialize"):
            runtime.prepare_private_run(approval_file=approval, candidate_manifest=manifest,
                config_path=new_config, state_path=new_state,
                database_url="postgresql://offline:test@localhost/db", session_signing_secret="synthetic")
        self.assertEqual(new_state.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
