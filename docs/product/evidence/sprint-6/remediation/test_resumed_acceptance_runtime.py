"""Offline safety tests for the separate Sprint 6 remediation runtime."""

from __future__ import annotations

import importlib.util
import json
import os
import asyncio
import tempfile
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


RUNTIME_PATH = Path(__file__).with_name("resumed_acceptance_runtime.py")
SPEC = importlib.util.spec_from_file_location("s6_remediation_runtime", RUNTIME_PATH)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class RuntimeBoundsTests(unittest.TestCase):
    def test_fresh_namespace_and_frozen_limits(self):
        self.assertEqual(runtime.RUN_ID, "s6-codex-20261026-remediation-1")
        self.assertNotEqual(runtime.RUN_STATE, Path("/private/tmp/staylead-sprint6-run-state.json"))
        self.assertEqual((runtime.MAX_GUEST_TURNS, runtime.MAX_REQUESTS, runtime.MAX_CALLS_PER_TURN), (9, 18, 2))
        self.assertEqual((runtime.MAX_OUTPUT_TOKENS, 25.0, 45.0), (700, 25.0, 45.0))

    def test_counter_validation_rejects_overflow_bool_and_negative(self):
        self.assertTrue(runtime._valid_counter(18, 18))
        self.assertTrue(runtime._valid_counter(9, 9))
        self.assertTrue(runtime._valid_counter(2, 2))
        for value, limit in ((19, 18), (10, 9), (3, 2), (True, 18), (-1, 18)):
            with self.subTest(value=value, limit=limit):
                self.assertFalse(runtime._valid_counter(value, limit))

    def test_malformed_or_original_state_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            for payload in ("{", json.dumps({"run_id": "s6-codex-20261026"}), json.dumps({"run_id": runtime.RUN_ID, "codex_requests": 19})):
                state_path.write_text(payload, encoding="utf-8")
                with patch.object(runtime, "RUN_STATE", state_path):
                    with self.assertRaises(SystemExit):
                        runtime._load_state()

    def test_persistent_request_and_turn_counters_refuse_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state = {
                "run_id": runtime.RUN_ID,
                "max_codex_requests": 18,
                "codex_requests": 17,
                "max_guest_turns": 9,
                "guest_turns": 8,
                "max_calls_per_turn": 2,
                "max_answer_only_resumes": 18,
                "answer_only_resumes": 0,
                "answer_only_receipt_hashes": [],
                "prior_grok_attempts": 8,
                "authorized_for_live_calls": True,
                "authority": "unit-test synthetic state",
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with patch.object(runtime, "RUN_STATE", state_path):
                self.assertEqual(runtime._reserve_provider_request(), 18)
                self.assertEqual(runtime._reserve_guest_turn(), 9)
                with self.assertRaisesRegex(RuntimeError, "limit reached"):
                    runtime._reserve_provider_request()
                with self.assertRaisesRegex(RuntimeError, "limit reached"):
                    runtime._reserve_guest_turn()
                self.assertEqual(json.loads(state_path.read_text())["codex_requests"], 18)
                self.assertEqual(json.loads(state_path.read_text())["guest_turns"], 9)

    def test_explicit_answer_only_resume_has_separate_counter_and_blocks_duplicate_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state = {
                "run_id": runtime.RUN_ID,
                "max_codex_requests": 18,
                "codex_requests": 2,
                "max_guest_turns": 9,
                "guest_turns": 1,
                "max_calls_per_turn": 2,
                "max_answer_only_resumes": 18,
                "answer_only_resumes": 0,
                "answer_only_receipt_hashes": [],
                "prior_grok_attempts": 8,
                "authorized_for_live_calls": True,
                "authority": "unit-test synthetic state",
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with patch.object(runtime, "RUN_STATE", state_path):
                self.assertEqual(runtime._reserve_answer_only_resume("synthetic-receipt"), (1, 1))
                after_first = json.loads(state_path.read_text())
                self.assertEqual(after_first["guest_turns"], 1)
                self.assertEqual(after_first["codex_requests"], 2)
                self.assertEqual(after_first["answer_only_resumes"], 1)
                with self.assertRaisesRegex(RuntimeError, "already reserved"):
                    runtime._reserve_answer_only_resume("synthetic-receipt")
                self.assertEqual(json.loads(state_path.read_text())["answer_only_resumes"], 1)

    def test_two_provider_requests_per_turn_is_hard_stop(self):
        class Provider:
            invocation_metadata = {"model": "synthetic", "reasoning_effort": "low"}

            def __init__(self):
                self.calls = 0

            async def generate(self, request):
                self.calls += 1
                @dataclass
                class Usage:
                    input_tokens: int = 1
                    output_tokens: int = 1
                    total_tokens: int = 2
                return SimpleNamespace(
                    provider="synthetic", deployment="offline", request_id=f"test-{self.calls}",
                    usage=Usage(), text='{"ok":true}',
                )

        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                state_path = Path(directory) / "state.json"
                events_path = Path(directory) / "events.jsonl"
                state_path.write_text(json.dumps({
                    "run_id": runtime.RUN_ID,
                    "max_codex_requests": 18,
                    "codex_requests": 0,
                    "max_guest_turns": 9,
                    "guest_turns": 1,
                    "max_calls_per_turn": 2,
                    "max_answer_only_resumes": 18,
                    "answer_only_resumes": 0,
                    "answer_only_receipt_hashes": [],
                    "prior_grok_attempts": 8,
                    "authorized_for_live_calls": True,
                    "authority": "unit-test synthetic state",
                }), encoding="utf-8")
                provider = runtime._observed_provider(Provider(), "synthetic-test")
                turn = {"calls": 0, "request_id": "offline-test", "guest_turn": 1}
                token = runtime.TURN.set(turn)
                try:
                    with patch.object(runtime, "RUN_STATE", state_path), patch.object(runtime, "EVENTS", events_path), patch.dict(os.environ, {}, clear=True):
                        request = SimpleNamespace(input_text="synthetic fixture", instructions="synthetic prompt", max_output_tokens=700)
                        await provider.generate(request)
                        await provider.generate(request)
                        with self.assertRaisesRegex(RuntimeError, "two-Codex-requests-per-turn"):
                            await provider.generate(request)
                        self.assertEqual(provider.calls, 2)
                        self.assertEqual(json.loads(state_path.read_text())["codex_requests"], 2)
                finally:
                    runtime.TURN.reset(token)

        asyncio.run(exercise())

    def test_validation_diagnostics_allowlist_only(self):
        safe = {
            "code": "model_validation",
            "error_count": 2,
            "errors": [
                {"loc": ["answer", 0, "amount"], "type": "int_parsing", "input": "LEAK"},
                {"loc": ["metadata", "<key>"], "type": "missing", "ctx": {"secret": "LEAK"}},
            ],
            "input": "LEAK",
        }
        self.assertEqual(runtime._safe_validation_diagnostics(safe), {
            "code": "model_validation",
            "error_count": 2,
            "errors": [
                {"loc": ["answer", 0, "amount"], "type": "int_parsing"},
                {"loc": ["metadata", "<key>"], "type": "missing"},
            ],
        })
        for malformed in (
            {"code": "other", "error_count": 1, "errors": []},
            {"code": "model_validation", "error_count": 1, "errors": [{"loc": ["private-value"], "type": "missing"}]},
            {"code": "model_validation", "error_count": 10001, "errors": []},
        ):
            with self.subTest(malformed=malformed):
                self.assertIsNone(runtime._safe_validation_diagnostics(malformed))

    def test_capture_requires_pinned_synthetic_opt_in_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            capture_dir = Path(directory) / "synthetic-output"
            common = {"guest_turn": 1, "attempt": 1, "synthetic_pinned": True,
                      "request_shape": {"input_sha256": "a" * 64, "instructions_sha256": "b" * 64}}
            with patch.object(runtime, "CAPTURE_DIR", capture_dir), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(runtime._capture_synthetic_json('{"answer":"x"}', common)["capture_status"], "disabled")
            env = {
                "STAYLEAD_S6_CAPTURE_SYNTHETIC_JSON": "1",
                "STAYLEAD_S6_SYNTHETIC_MATRIX_ID": "staylead-s6-nine-turn-multilingual-20261026-v1",
            }
            with patch.object(runtime, "CAPTURE_DIR", capture_dir), patch.dict(os.environ, env, clear=True):
                self.assertEqual(runtime._capture_synthetic_json("x" * (64 * 1024 + 1), common)["capture_status"], "rejected_over_64kib")
                self.assertEqual(runtime._capture_synthetic_json("not-json", common)["capture_status"], "rejected_not_json")
                result = runtime._capture_synthetic_json('{"answer":"synthetic"}', common)
                self.assertEqual(result["capture_status"], "captured_private")
                capture_path = capture_dir / "output-01.json"
                self.assertEqual(capture_dir.stat().st_mode & 0o777, 0o700)
                self.assertEqual(capture_path.stat().st_mode & 0o777, 0o600)
                saved = json.loads(capture_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["body_json"], {"answer": "synthetic"})
                self.assertEqual(saved["body_text"], '{"answer":"synthetic"}')
                self.assertNotIn("LEAK", capture_path.read_text(encoding="utf-8"))
                self.assertEqual(runtime._capture_synthetic_json('{"answer":"again"}', common)["capture_status"], "refused_existing_capture")

    def test_capture_refuses_symlink_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            capture_dir = root / "capture"
            capture_dir.symlink_to(target, target_is_directory=True)
            env = {
                "STAYLEAD_S6_CAPTURE_SYNTHETIC_JSON": "1",
                "STAYLEAD_S6_SYNTHETIC_MATRIX_ID": runtime.MATRIX_ID,
            }
            common = {"guest_turn": 1, "attempt": 1, "synthetic_pinned": True, "request_shape": {}}
            with patch.object(runtime, "CAPTURE_DIR", capture_dir), patch.dict(os.environ, env, clear=True):
                result = runtime._capture_synthetic_json('{"answer":"synthetic"}', common)
            self.assertEqual(result["capture_status"], "refused_unsafe_capture_directory")
            self.assertEqual(list(target.iterdir()), [])

    def test_capture_refuses_non_pinned_turn_even_with_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "STAYLEAD_S6_CAPTURE_SYNTHETIC_JSON": "1",
                "STAYLEAD_S6_SYNTHETIC_MATRIX_ID": runtime.MATRIX_ID,
            }
            common = {"guest_turn": 1, "attempt": 1, "synthetic_pinned": False, "request_shape": {}}
            with patch.object(runtime, "CAPTURE_DIR", Path(directory)), patch.dict(os.environ, env, clear=True):
                self.assertEqual(runtime._capture_synthetic_json('{"answer":"not synthetic"}', common)["capture_status"], "disabled")

    def test_pinned_synthetic_matrix_turn_matches_exact_utterance(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] / "live-cases.json").read_text(encoding="utf-8"))
        question = matrix["turns"][0]["utterance"]
        self.assertTrue(runtime._is_pinned_synthetic_turn(1, question))
        self.assertFalse(runtime._is_pinned_synthetic_turn(1, question + " altered"))

    def test_no_startup_provider_call_without_explicit_live_gate(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                runtime.create_runtime_app()

    def test_browser_driver_does_not_submit_after_failure_and_snapshots_copy_counters(self):
        source = Path(__file__).with_name("resumed-live-browser.mjs").read_text(encoding="utf-8")
        self.assertIn("keepBrowserOpen = true", source)
        self.assertIn("this driver will not submit another turn", source)
        self.assertIn("beforeCopy = runtimeSnapshot", source)
        self.assertIn("afterCopy = runtimeSnapshot", source)
        self.assertIn("turn-screenshots", source)


if __name__ == "__main__":
    unittest.main()
