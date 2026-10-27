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
        self.live_cases_path.write_text('{"run_id": "' + runtime.CASE_RUN_ID + '", "cases": []}', encoding="utf-8")
        self.matrix_sha = runtime._file_sha256(self.live_cases_path)
        self.oracle_path.write_text('{"synthetic": true}', encoding="utf-8")
        self.oracle_sha = runtime._file_sha256(self.oracle_path)
        self.prior_allocation = runtime._prior_allocation_record()
        self.continuation = runtime._continuation_record()
        source_rel = str(Path(__file__).relative_to(Path(__file__).parents[2]))
        self.source_files = {source_rel: runtime._file_sha256(Path(__file__))}
        manifest = {"run_id": runtime.RUN_ID, "matrix_sha256": self.matrix_sha,
                    "oracle_sha256": self.oracle_sha, "source_files": self.source_files,
                    "live_cases_path": str(self.live_cases_path), "oracle_path": str(self.oracle_path),
                    "prior_allocation": self.prior_allocation, "continuation": self.continuation}
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
            "prior_allocation": self.prior_allocation, "continuation": self.continuation,
        }
        self._write(self.manifest_path, manifest)
        self.state = {
            "run_id": runtime.RUN_ID, "authority": "offline synthetic test",
            "candidate_sha256": self.candidate_sha, "matrix_sha256": self.matrix_sha,
            "authorized_for_live_calls": True, "status": "authorized",
            "max_guest_turns": 7, "max_codex_requests": 14, "max_calls_per_turn": 2,
            "reserved_guest_turn_budget": 7, "reserved_request_budget": 14,
            "guest_turns": runtime.START_GUEST_TURNS, "codex_requests": runtime.START_REQUESTS,
            "continuation_parent_state_sha256": runtime.PARENT_STATE_SHA256,
        }
        self._write(self.config_path, self.config)
        self._write(self.state_path, self.state)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)

    @contextlib.contextmanager
    def _env(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                runtime.CONFIG_ENV: str(self.config_path),
                runtime.STATE_ENV: str(self.state_path),
                runtime.EVENTS_ENV: str(self.events_path),
            }, clear=True))
            stack.enter_context(patch.object(runtime, "_verify_parent_continuation", return_value={}))
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
        self.assertEqual(output["guest_turn_cap"], 7)
        self.assertEqual(output["request_cap"], 14)
        self.assertEqual(output["seed_counters"], {"guest_turns": 3, "codex_requests": 5})
        self.assertEqual(output["approved_case_turns"], [6, 7])
        self.assertTrue(output["no_browser"])
        self.assertTrue(output["no_api_or_model"])

    def test_frozen_caps_and_prelaunch_reservations_are_validated(self):
        self.assertTrue(runtime._valid_state(self.state, self.config, fresh=True))
        self.assertEqual(runtime.RUN_ID, "s7-room-advice-20261026-reacceptance1-cont2")
        self.assertEqual(runtime.PARENT_RUN_ID, "s7-room-advice-20261026-reacceptance1-cont1")
        self.assertEqual(runtime.CASE_RUN_ID, "s7-room-advice-20261026-reacceptance1")
        self.assertEqual((runtime.MAX_GUEST_TURNS, runtime.MAX_REQUESTS, runtime.MAX_CALLS_PER_TURN), (7, 14, 2))
        self.assertEqual((runtime.PROVIDER_TIMEOUT_SECONDS, runtime.TURN_TIMEOUT_SECONDS, runtime.MAX_OUTPUT_TOKENS), (25.0, 45.0, 700))
        self.assertEqual((runtime.MODEL, runtime.EFFORT), ("gpt-6-luna", "low"))
        for changed in (
            {**self.state, "reserved_request_budget": 15},
            {**self.state, "max_guest_turns": 8},
            {**self.state, "codex_requests": True},
            {**self.state, "candidate_sha256": "c" * 64},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(runtime._valid_state(changed, self.config, fresh=True))

    def test_closed_prior_allocation_is_verified_without_seeding_new_counters(self):
        prior = runtime._verify_closed_prior_allocation(self.prior_allocation)
        self.assertEqual(prior["run_id"], runtime.PRIOR_RUN_ID)
        self.assertEqual((prior["guest_turns"], prior["codex_requests"]), (9, 16))
        self.assertEqual((self.state["guest_turns"], self.state["codex_requests"]), (3, 5))
        self.assertFalse(runtime._valid_state({**self.state, "guest_turns": 4}, self.config, fresh=True))

    def test_halted_batch1_authorization_is_not_accepted_for_reacceptance1(self):
        old_state = {**self.state, "run_id": "s7-room-advice-20261026-batch1", "status": "halted",
                     "guest_turns": 3, "codex_requests": 5}
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
            self.assertEqual((after_start["guest_turns"], after_start["codex_requests"]), (3, 5))
            with self.assertRaisesRegex(RuntimeError, "authorization"):
                runtime._transition_status("starting")
            self.assertEqual(json.loads(self.state_path.read_text()), after_start)

    def test_zero_consumption_bootstrap_failure_releases_same_namespace_for_restart(self):
        with self._lease(), self._env():
            runtime._transition_status("starting")
            self.assertTrue(runtime._release_bootstrap_if_unused("bind-failed"))
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after["status"], "authorized")
        self.assertEqual(after["guest_turns"], 3)
        self.assertEqual(after["codex_requests"], 5)
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
        self.state.update(status="running", guest_turns=5, codex_requests=8)
        self._write(self.state_path, self.state)
        with self._lease(), self._env():
            self.assertEqual(runtime._reserve("codex_requests", 14, "request"), 9)
            with self.assertRaisesRegex(RuntimeError, "limit reached"):
                runtime._reserve("codex_requests", 14, "request")
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after["codex_requests"], 9)
        self.assertEqual(after["guest_turns"], 5)

    def test_guest_turn_gate_rejects_nonmatching_question_before_reservation(self):
        self._replace_cases(["one", "two", "three", "four", "five", "approved sixth", "approved seventh"])
        self.state["status"] = "running"
        self._write(self.state_path, self.state)
        with self._lease(), self._env():
            with self.assertRaisesRegex(runtime._UnapprovedGuestTurn, "next approved case"):
                runtime._reserve_approved_guest_turn("arbitrary replacement question")
            self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 3)
            self.assertEqual(runtime._reserve_approved_guest_turn("approved sixth"), (4, 6))
            self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 4)
            with self.assertRaisesRegex(runtime._UnapprovedGuestTurn, "next approved case"):
                runtime._reserve_approved_guest_turn("fifth")
            self.assertEqual(runtime._reserve_approved_guest_turn("approved seventh"), (5, 7))
        final = json.loads(self.state_path.read_text())
        self.assertEqual(final["guest_turns"], 5)
        self.assertEqual(final["codex_requests"], 5)

    def test_runtime_middleware_rejects_unapproved_question_without_slot_or_provider_call(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from staylead_platform.composition.dependencies import guest_chat
        from staylead_platform.entrypoints import app as app_module

        self._replace_cases(["one", "two", "three", "four", "five", "approved sixth", "approved seventh"])

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

        self.state["status"] = "authorized"
        self._write(self.state_path, self.state)
        with self._env(), patch.dict(os.environ, {runtime.LIVE_ENV: "1"}), \
                patch.object(runtime, "LEASE_PATH", self.root / "runtime.lock"), \
                patch.object(runtime.shutil, "which", return_value="/fake/codex"), \
                patch.object(guest_chat, "build_provider", return_value=provider), \
                patch.object(app_module, "create_app", side_effect=fake_app):
            app = runtime.create_runtime_app()
            try:
                with TestClient(app) as client:
                    rejected = client.post("/v1/guest/sessions/test/messages",
                                           json={"question": "unapproved arbitrary question"})
                    self.assertEqual(rejected.status_code, 400)
                    self.assertEqual(rejected.json()["error"]["code"], "unapproved_guest_turn")
                    self.assertEqual((provider.calls, json.loads(self.state_path.read_text())["guest_turns"],
                                      json.loads(self.state_path.read_text())["codex_requests"]), (0, 3, 5))
                    blocked_case = client.post("/v1/guest/sessions/test/messages",
                                               json={"question": "two"})
                    self.assertEqual(blocked_case.status_code, 400)
                    self.assertEqual(blocked_case.json()["error"]["code"], "unapproved_guest_turn")
                    self.assertEqual((provider.calls, json.loads(self.state_path.read_text())["guest_turns"],
                                      json.loads(self.state_path.read_text())["codex_requests"]), (0, 3, 5))
                    accepted = client.post("/v1/guest/sessions/test/messages",
                                           json={"question": "approved sixth"})
                    self.assertEqual(accepted.status_code, 200)
                    final = json.loads(self.state_path.read_text())
                    self.assertEqual((provider.calls, final["guest_turns"], final["codex_requests"]), (1, 4, 6))
            finally:
                runtime._release_process_lease()

    def test_case_and_candidate_file_hashes_are_checked_before_turn_reservation(self):
        self.state["status"] = "running"
        self._write(self.state_path, self.state)
        original = self.live_cases_path.read_bytes()
        self.live_cases_path.write_text('{"cases": ["changed"]}', encoding="utf-8")
        with self._lease(), self._env(), self.assertRaisesRegex(RuntimeError, "case matrix or independent oracle changed"):
            runtime._reserve("guest_turns", 7, "guest turn")
        self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 3)
        self.live_cases_path.write_bytes(original)
        with self._lease(), self._env():
            self.assertEqual(runtime._reserve("guest_turns", 7, "guest turn"), 4)
        self.assertEqual(json.loads(self.state_path.read_text())["guest_turns"], 4)

    def test_provider_failure_keeps_reserved_counter_and_halts_run(self):
        class BrokenProvider:
            async def generate(self, request):
                raise TimeoutError("synthetic timeout")

        request = SimpleNamespace(input_text="synthetic utterance", instructions="synthetic instructions",
                                  max_output_tokens=700)
        self.state.update(status="running", guest_turns=3)
        self._write(self.state_path, self.state)
        turn = {"guest_turn": 4, "approved_case_turn": 6, "calls": 0,
                "request_id": "synthetic-request", "synthetic_pinned": False}
        token = runtime.TURN.set(turn)
        try:
            with self._lease(), self._env(), self.assertRaises(TimeoutError):
                asyncio.run(runtime._observed_provider(BrokenProvider()).generate(request))
        finally:
            runtime.TURN.reset(token)
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after["codex_requests"], 6)
        self.assertEqual(after["guest_turns"], 3)
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
        self.state.update(status="running", guest_turns=3)
        self._write(self.state_path, self.state)
        turn = {"guest_turn": 4, "approved_case_turn": 6, "calls": 0,
                "request_id": "request-1", "synthetic_pinned": False}
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
        self.assertEqual(json.loads(self.state_path.read_text())["codex_requests"], 7)
        rows = [json.loads(line) for line in self.events_path.read_text().splitlines()]
        self.assertEqual(sum(row["stage"] == "provider_completed" for row in rows), 2)
        self.assertTrue(all("input_text" not in row and "instructions" not in row for row in rows))

    def test_prior_allocation_receipt_must_match_exact_sealed_state(self):
        altered = dict(self.prior_allocation, codex_requests=15)
        with self.assertRaisesRegex(RuntimeError, "exact closed immutable receipt"):
            runtime._verify_closed_prior_allocation(altered)

    def test_browser_selection_branch_tolerates_clarification_and_selects_current_positive_cases(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ selectionOptionForAcceptanceTurn }} from "{helper}";
import assert from "node:assert/strict";
const unknownChildAdvice = {{ status: "needs_clarification", options: [] }};
assert.equal(selectionOptionForAcceptanceTurn(3, unknownChildAdvice), null);
const frenchPine = {{ option_id: "pine-option" }};
assert.equal(selectionOptionForAcceptanceTurn(7, {{ options: [frenchPine] }}), frenchPine);
assert.equal(selectionOptionForAcceptanceTurn(1, {{ options: [frenchPine] }}), null);
assert.equal(selectionOptionForAcceptanceTurn(2, {{ options: [frenchPine] }}), null);
assert.equal(selectionOptionForAcceptanceTurn(6, {{ options: [frenchPine] }}), null);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                   text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_browser_checks_accept_actual_checked_unknown_and_canonical_m2_shapes(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ hasCanonicalSeparateBedConstraint, retainsTwoHardAccessibilityNeeds,
  roomAdviceHardChecksConsistent, hasExactBedSharingConsent }} from "{helper}";
import assert from "node:assert/strict";
const cityEditBrief = {{ party: {{ bed_sharing: [{{ member_ids: ["adult-1", "adult-2"], allow_share: true }}] }},
  room_requirements: {{ hard_bed_types: ["single"] }} }};
assert.equal(hasCanonicalSeparateBedConstraint(cityEditBrief), true);
const chineseNeeds = {{ room_requirements: {{ hard_accessibility_needs: [
  "Phòng cần lối đi không bậc cho xe lăn", "Phòng tắm phải dùng được với xe lăn"
] }} }};
assert.equal(retainsTwoHardAccessibilityNeeds(chineseNeeds), true);
assert.equal(retainsTwoHardAccessibilityNeeds({{ room_requirements: {{ hard_accessibility_needs: [] }} }}), false);
const committedFamilyBrief = {{ party: {{ bed_sharing: [{{ member_ids: ["adult-1", "adult-2"], allow_share: true }}] }} }};
assert.equal(hasExactBedSharingConsent(committedFamilyBrief, ["adult-1", "adult-2"], true), true);
assert.equal(hasExactBedSharingConsent({{ party: {{ bed_sharing: [] }} }}, ["adult-1", "adult-2"], true), false);
assert.equal(hasExactBedSharingConsent({{ party: {{ bed_sharing: [{{ member_ids: ["adult-1", "adult-2"], allow_share: false }}] }} }},
  ["adult-1", "adult-2"], true), false);
assert.equal(hasExactBedSharingConsent({{ party: {{ bed_sharing: [{{ member_ids: ["adult-1", "adult-2", "child-1"], allow_share: true }}] }} }},
  ["adult-1", "adult-2"], true), false);
const checkedPartial = {{ status: "partial", options: [{{ checks: [
  {{ code: "wheelchair_access", status: "unknown", fact_ids: ["FACT-ROOM-1"] }}
], rationale: [{{ claim_code: "accessibility_confirmation", text: "Details need confirmation.", fact_ids: ["FACT-ROOM-1"] }}] }}] }};
assert.equal(roomAdviceHardChecksConsistent(checkedPartial), true);
assert.equal(roomAdviceHardChecksConsistent({{ status: "conflict", options: [] }}), true);
assert.equal(roomAdviceHardChecksConsistent({{ status: "ready", options: [{{ checks: [
  {{ code: "occupancy", status: "conflict", fact_ids: ["FACT-ROOM-1"] }}
] }}] }}), false);
assert.equal(roomAdviceHardChecksConsistent({{ status: "conflict", options: [{{ checks: [] }}] }}), false);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], cwd=repo,
                                   text=True, capture_output=True, check=False, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(Path("/private/tmp/staylead-s7-reacceptance1-cases.json").is_file(),
                         "requires root-approved exact reacceptance1 matrix")
    def test_approved_reacceptance_matrix_and_real_session_public_shape_are_pinned(self):
        repo = Path(__file__).parents[2]
        private_path = Path("/private/tmp/staylead-s7-reacceptance1-cases.json")
        cases = runtime._private_file(private_path)
        self.assertEqual(runtime._file_sha256(private_path),
                         "d48d28c04b23f0ea7151a3e24c6f5556169bdfdd2a7a0caca0ed7d01e338ec50")
        proposal = json.loads((repo / "docs/product/evidence/sprint-7/reacceptance-cases-proposed.json")
                              .read_text(encoding="utf-8"))
        for key in set(proposal) - {"status", "authorized_for_live_calls"}:
            self.assertEqual(cases[key], proposal[key], key)
        self.assertEqual(cases["authorized_for_live_calls"], True)
        self.assertEqual((cases["run_id"], cases["proposed_max_guest_turns"],
                          cases["proposed_max_requests"], len(cases["cases"])),
                         (runtime.CASE_RUN_ID, 7, 14, 7))
        self.assertEqual([case["session"] for case in cases["cases"]],
                         ["fresh-city", "fresh-city", "fresh-beach", "fresh-beach",
                          "fresh-beach", "fresh-pine", "fresh-pine"])
        authority = runtime._private_file(Path("/private/tmp/staylead-s7-reacceptance1-cont2-authority.json"))
        parent = runtime._private_file(runtime.PARENT_STATE_PATH)
        self.assertEqual(authority["continuation"], runtime._continuation_record())
        self.assertEqual(runtime._file_sha256(runtime.PARENT_STATE_PATH), runtime.PARENT_STATE_SHA256)
        self.assertEqual((parent["run_id"], parent["guest_turns"], parent["codex_requests"], parent["status"]),
                         (runtime.PARENT_RUN_ID, 3, 5, "halted"))
        self.assertEqual(runtime.APPROVED_CASE_TURNS, (6, 7))
        self.assertEqual(runtime.BUDGET_TURNS, (4, 5))

        from staylead_platform.domains.hospitality.registration.fixture_pack import (
            parse_fixture_pack,
        )

        prepared = {item.slug: item for item in parse_fixture_pack(repo / "fixtures/hospitality/knowledge-v1")}
        for slug, expected_id in (("harbor-city-demo", "HTL-CITY01"),
                                  ("lagoon-family-demo", "HTL-BEACH02"),
                                  ("pine-ridge-demo", "HTL-RETREAT03")):
            hotel = prepared[slug]
            public_session_hotel = {**hotel.public_config, "booking_channel": {"destination_url": "https://booking.example/" + slug}}
            self.assertEqual(hotel.hotel_id, expected_id)
            self.assertEqual(public_session_hotel["hotel_id"], expected_id)
            self.assertTrue({"hotel_id", "name", "address", "description", "timezone", "currency"}
                            <= public_session_hotel.keys())
            self.assertNotIn("hotel_slug", public_session_hotel)

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

    def test_browser_run_directory_is_unique_to_fresh_reacceptance_namespace(self):
        repo = Path(__file__).parents[2]
        helper = (repo / "tools/evals/sprint7_browser_helpers.mjs").as_uri()
        script = f'''import {{ browserRunDirectory }} from "{helper}";
import assert from "node:assert/strict";
assert.equal(browserRunDirectory("s7-room-advice-20261026-reacceptance1-cont2", "r1"),
  "/private/tmp/staylead-s7-browser-s7-room-advice-20261026-reacceptance1-cont2-r1");
assert.throws(() => browserRunDirectory("../overwrite", "r2"), /Invalid private browser run directory/);
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
            "authority": "approved offline synthetic fixture", "max_guest_turns": 7,
            "max_codex_requests": 14, "max_calls_per_turn": 2, "model": "gpt-6-luna",
            "effort": "low", "provider_timeout_seconds": 25.0,
            "turn_timeout_seconds": 45.0, "output_cap": 700,
            "case_matrix_sha256": self.matrix_sha,
            "prior_allocation": self.prior_allocation, "continuation": self.continuation})
        candidate_record = {"run_id": runtime.RUN_ID, "matrix_sha256": self.matrix_sha,
            "oracle_sha256": self.oracle_sha, "live_cases_path": str(self.live_cases_path),
            "oracle_path": str(self.oracle_path), "source_files": self.source_files,
            "prior_allocation": self.prior_allocation, "continuation": self.continuation}
        candidate_record["candidate_sha256"] = runtime._candidate_manifest_digest(candidate_record)
        self._write(manifest, candidate_record)
        approval_record = json.loads(approval.read_text(encoding="utf-8"))
        approval_record["case_matrix_sha256"] = "0" * 64
        self._write(approval, approval_record)
        with self.assertRaisesRegex(RuntimeError, "Approval does not authorize"):
            runtime.prepare_private_run(approval_file=approval, candidate_manifest=manifest,
                config_path=new_config, state_path=new_state,
                database_url="postgresql://offline:test@localhost/db", session_signing_secret="synthetic")
        self.assertFalse(new_config.exists())
        self.assertFalse(new_state.exists())
        approval_record["case_matrix_sha256"] = self.matrix_sha
        self._write(approval, approval_record)
        with patch.object(runtime, "_verify_parent_continuation", return_value={}):
            runtime.prepare_private_run(approval_file=approval, candidate_manifest=manifest,
                config_path=new_config, state_path=new_state,
                database_url="postgresql://offline:test@localhost/db", session_signing_secret="synthetic")
        state = runtime._private_file(new_state)
        self.assertEqual(state["status"], "authorized")
        self.assertEqual(state["guest_turns"], 3)
        self.assertEqual(state["codex_requests"], 5)
        self.assertEqual(state["reserved_request_budget"], 14)
        before = new_state.read_bytes()
        with (self.assertRaisesRegex(RuntimeError, "Refusing to initialize"),
              patch.object(runtime, "_verify_parent_continuation", return_value={})):
            runtime.prepare_private_run(approval_file=approval, candidate_manifest=manifest,
                config_path=new_config, state_path=new_state,
                database_url="postgresql://offline:test@localhost/db", session_signing_secret="synthetic")
        self.assertEqual(new_state.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
