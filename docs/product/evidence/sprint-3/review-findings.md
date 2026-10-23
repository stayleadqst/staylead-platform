# Sprint 3 independent review

Reviewer role: fresh `gpt-6.1-sol / high`, as assigned. Product read only by instruction; no claim of an enforced filesystem profile. No product edits, database mutations, live LLM calls, or GitHub writes performed by this reviewer.

**Final review status: no outstanding blocking finding on the reviewed source and supplied acceptance evidence.** Final live image, clip/time reference and unsupported-visual cases pass the independent semantic comparison below. Historical pending statements are retained to show the review sequence; the final section resolves them.

## Candidate and scope

Baseline HEAD: `21ef9a222236b9d46afd236310670c599c40dea4`.
Initial tracked diff SHA256: `c57fe530069e944f5a6bda79d7d1045d4077aa8fe94f91a7c51ceb64519d5284`; this initial diff hash excludes untracked files and is not the final candidate fingerprint.

Final reviewed source/test/fixture fingerprint: **`5b7f71cba464767f9d73ce59fc352c0b32556477378d6b8bb0c46d4b430a4384`**, 189 files. [Exact file hashes](review-source-fingerprint.json) cover every tracked and untracked nonignored file under `apps/`, `tests/`, `fixtures/`, plus repo `AGENTS.md`. Hash input is UTF-8 JSON of sorted `{path, sha256}` rows, with sorted keys and compact separators. Generated ignored outputs and later acceptance documents are excluded. The [live/test candidate](review-source-fingerprint-live.json) is `184753fd700f968485944fde43df84129d3b4c9856410d83e6ffd217966c0704`; its only final difference is the verified removal of one EOF blank line in a test. Product source is identical. Earlier clearance fingerprints are preserved in [initial file hashes](review-source-fingerprint-initial.json) and [first-prompt file hashes](review-source-fingerprint-prompt1.json); affected deltas are reviewed below.

Read the exact user authorization attachment, workspace/repo instructions, WORKING_RULES, AI_ARCHITECTURE, AGENT_EXECUTION, Not_Overthinking, Sprint 1/2 acceptance, full issues 75–77 snapshots, and issue 78 through GitHub. Review focused the Sprint 3 delta on producer → persistence → final cited facts → authenticated binary → browser lifecycle, with existing bounded/session/retry behavior preserved. No broad unrelated audit was performed.

## Findings and clearance

| Finding | Initial reproducer / impact | Final correction and independent clearance |
| --- | --- | --- |
| VTT syntax and duration | A temporary fixture with `WEBVTT` plus `not-a-timestamp --> wrong` was accepted. A cue at 9–10 seconds was also accepted for the verified 3-second MP4. Violated K2-AC3. | Parser validates timestamp syntax, ordered positive cues, matching source/facts, and approved clip bounds. Both original malformed/out-of-duration temporary-pack reproducers now reject. |
| VTT header and dangling cue | Direct `_parse_vtt` accepted a timing line immediately after the header with no blank separator; a valid cue followed by an orphan identifier at EOF was also accepted. | Final direct probes reject with `WebVTT header must be followed by a blank separator line` and `WebVTT cue identifier has no timing line`. Valid 0.5–2.5-second cue still parses. |
| Source expiry leaked into text eligibility | Source ending 2025-12-31 with facts ending 2035 was accepted unchanged; existing fact reader filters fact dates, so expired-source facts could still reach retrieval. | Imported effective fact dates intersect fact/source validity; nonoverlap rejects. Independent temporary-pack probe confirms fact valid_to becomes 2025-12-31. |
| Unsafe media identifiers | `media/room` was accepted but could not traverse the exact binary route. Initial correction still allowed `.`/`..`, which URL normalization removes. | Independent temporary-pack probes confirm slash and both dot-segment IDs reject. |
| Multi-source mapping silently lost | A fact with two source refs and media bound to its second source validated, while persistence retained only the first source and the eligible reader required that first source. | Schema v1 explicitly supports exactly one source version per fact and rejects unsupported multi-source input before publication. Source correction reviewed. |
| Effective-date normalization weakened immutability | Rebuilding canonical identity from clamped facts could make changed raw manifest validity produce the same identity. | Identity retains raw manifest changes. Independent temporary-pack comparison with common source ceiling 2030 and changed raw fact end 2035→2040 yields different canonical hashes. |
| Media lookup blocked the event loop and turn deadline | New synchronous post-answer SQL lookup ran inside `asyncio.timeout_at`, which cannot interrupt a blocking synchronous operation. | Lookup runs via `asyncio.to_thread` with remaining time; SQL adapter sets transaction timeouts. Independent fake slow-media probe: 1.4-second blocking lookup, 1-second turn limit → 504 at 1.0 seconds, concurrent heartbeat at 0.1 seconds. No database or provider used. |
| Fractional UI time label (coordinator finding) | Initial browser label rounded approved 0.5–2.5 seconds to 0:00–0:02. | Reviewed `formatMediaTime` and caller: fractional precision retained. Final rebuilt browser label verification remains with coordinator. |

The initial `source_id` and nullable-span insert failures were coordinator integration findings, repaired by A before this review; this reviewer does not claim to have discovered them. The initial exact-400 test fixture needed corresponding binding IDs updated; owner corrected its test input. These are retained in coordinator evidence.

**No outstanding blocking source finding on the fingerprint above.** Clearance covers the targeted defects and reviewed paths, not universal correctness or completion of unobserved acceptance criteria.

## Verification and remaining evidence

- Reviewer ran narrow offline temporary-pack and direct-parser reproducers only, plus the fake slow-media deadline probe. No broad test suite was repeated.
- Read `backend-final-tests.txt`: **58 passed**, one existing Starlette/httpx deprecation warning. That suite ran before the final two parser tests; do not describe a 60-test rerun. Coordinator reports the final targeted validator suite **25 passed**, Ruff and compile checks passed.
- Read `http_acceptance.py` and `http-observations.json`: coordinator's actual Next production proxy → FastAPI → isolated PostgreSQL checks use a fake provider. They verify all four hotel lookups, unknown lookup, exact PNG/MP4/VTT bytes/hash/MIME/no-store, missing/wrong/expired session and hotel isolation, exact-route rejection, cached replay, cited-fact binding, text-only and unknown compatibility. These are runtime evidence collected by coordinator, not reviewer-run HTTP requests.
- Inspected `desktop-caption-initial.jpg`: fourth-hotel UI, video frame, rendered caption text and authored/synthetic disclosure are visible. It intentionally preserves the old fractional label and is not evidence that the corrected label was rebuilt.
- Inspected sanitized `runtime-events.jsonl`: actual binary hashes and browser Blob creation/revocation are recorded. Final late-hotel/session absence checks and actual playback observations must be supplied by coordinator; a screenshot alone does not establish playback.
- **Pending:** final production rebuild/browser evidence including fractional label, mobile/desktop playback and captions, late response/session/hotel isolation, final Blob cleanup; minimal real Grok semantic observations and usage/failures. No live acceptance PASS is asserted here.

Reviewer report may be appended with final supplied browser/live evidence. Product source changes after the fingerprint require an affected-delta review, not a repeated broad audit.

## Post-clearance affected-delta review

No broad audit or broad suite rerun. Reviewed the prompt, pack bounds, typed protocol restoration, focused tests and the three import/whitespace-only deltas listed in `postreview-delta.json`.

- **Live image failure retained:** `runtime-events.jsonl` records the initial real model selecting the correct room fact, then producing a correct balcony claim plus an uncited claim that no illustration was available (`fact_ids: []`). Server returned 502 `invalid_model_output`; it did not weaken the evidence guard. Two provider calls report 409+617 input, 9+58 output, and 853+1171 = **2024 provider-reported total tokens**. Total is preserved as reported rather than recomputed from visible input/output. These calls are a failed attempt, not semantic acceptance.
- **Prompt correction cleared:** Hospitality prompt now explains that the server attaches approved media after final cited fact validation. Missing descriptors in model context do not establish attachment availability. Model still cannot select media or invent URLs, and unsupported visual properties remain unknown. Orchestrator/output guards and runtime model are unchanged. The focused fake test verifies the answer path and instruction registration; it cannot demonstrate corrected real-model behavior. Coordinator reports 17 grounded-QA tests passed; real image replay and clip/unsupported cases remain pending.
- **Pack total/bounded reads cleared:** coordinator found the 64 MiB aggregate check needed manifest bytes included and reads bounded before allocation. Source now initializes aggregate with raw manifest byte length, stat-checks the manifest and assets before opening, bounds reads by per-kind and remaining total limits, and verifies postread length/hash. Reviewer independently lowered aggregate limit to the fixture boundary: total 34,791 bytes including manifest; limit 34,790 rejected, limit 34,791 accepted. A real sparse manifest of 64 MiB+1 bytes rejected while `Path.open` was patched to raise, proving rejection occurred before opening. Coordinator reports final targeted validator **27 passed**; retain the historical 58 full-suite result rather than inventing a current full-suite rerun count.
- **Typed protocol restoration cleared:** `get_guest_facts` is again on `KnowledgeFactRepository`; `EligibleMediaRepository` declares only media list/read with optional query timeouts. Runtime repository classes are unchanged.
- **Additional runtime artifacts inspected:** `media-deadline-observations.json` reports a real isolated PostgreSQL lock returning 504 at 1.058 seconds with committed state version 0. `proxy-bounds-observations.json` reports no-content-length PNG/MP4/VTT over-limit bodies rejected with 502 and HTML MIME rejected with 502. These are coordinator-run runtime checks, separate from the reviewer fake deadline probe.
- **Final label visual check:** reviewer inspected `desktop-caption-final.jpg`: visible caption text and corrected `0:00.5–0:02.5` reference. `mobile-image-final.jpg` currently depicts the pool video at 0:03/0:03; its filename alone must not be cited as image-rendering evidence. Final browser observation mapping and live semantic acceptance remain pending.

**No outstanding blocking source finding on current fingerprint `72666cb5…`.** Real-model success and remaining browser lifecycle acceptance are not inferred from the source clearance.

## Second live image attempt — semantic failure despite HTTP 200

Reviewed the subsequent `runtime-events.jsonl` response: correct balcony claim, final room-fact citation, approved `media-room` descriptor and exact PNG bytes, but `unknowns: ["Authored illustration."]`. The UI would label the already supplied illustration as unconfirmed. This is a semantic/presentation defect under K3-AC5/AC7, not a new scope requirement; HTTP 200 is not acceptance.

Retain the attempt as failed: two provider calls, input 1138 / output 70 / provider-reported total 2307 tokens. The bounded proposed correction distinguishes unresolved factual hotel information from requests to display server-managed attachments. It must preserve unknowns for unsupported factual/visual inference, media mapping on final cited facts, and existing output guards. No retry or extra model call is added to the product path. Exact second prompt delta and its real replay remain pending at this update.

## Second prompt clarification — source cleared, replay pending

Reviewed exact landed delta: media display requests are server presentation operations; the model must not repeat those operations as unknowns or make attachment availability/visibility claims. `unknowns` still covers unresolved factual hotel information, and unsupported visual properties explicitly remain unknown. No guard, postfilter, media selection, or model call was added or loosened. The focused fake test checks the registered instructions and grounded answer path; coordinator reports 17 targeted tests passed. This fixes the observed distinction without extending acceptance criteria. Real replay must demonstrate the corrected combined text/image outcome.

Only Hospitality prompt and its focused test changed from fingerprint `72666cb5…`; current fingerprint is `184753fd700f968485944fde43df84129d3b4c9856410d83e6ffd217966c0704` (189 files). **No outstanding blocking source finding.**

Read coordinator's `pack-boundary-observations.json`: exact 400-fact import and runtime 400-fact read; changed pack version/content/config reject with existing data unchanged; 401-fact overflow and global fact-ID collision reject atomically. All reported checks are true. This is additional real-PostgreSQL evidence collected by coordinator, not a reviewer-run database check.

## Final integrated acceptance evidence review

Recomputed all 189 source/test/fixture hashes after the final live responses: fingerprint remains **`184753fd700f968485944fde43df84129d3b4c9856410d83e6ffd217966c0704`**, unchanged. No additional calls, tests, or product edits were performed by reviewer.

Compared `semantic-expectations.json` (evaluation only) against the authored manifest/VTT, final real-provider JSON/HTTP events and supplied browser snapshots. Expectations were not imported serving data or model context.

| Case | Independently assessed final observation | Result |
| --- | --- | --- |
| Image fact/caption | Same exact image question succeeds in a fresh session: king room balcony is true, cited `fact-room-balcony`, final approved descriptor is `media-room`, `unknowns` empty, authored/synthetic caption matches manifest. Exact PNG hash matches fixture. `live-image-final.txt` and inspected `live-mobile-image-final.jpg` show the correct illustration and factual answer without the prior false unknown. | PASS |
| Clip/time reference | Same-session follow-up states garden-facing view with `fact-pool-view` and `fact-pool-clip-window`, and approved reference 0.5–2.5 seconds. Descriptor is `media-pool-clip`, actual duration 3 seconds, captions ID `media-pool-vtt`; exact binary hashes match fixture. `live-clip-final.txt` and inspected screenshot show the fractional button and visible VTT text `The pool deck faces the garden.`, matching authored VTT. Coordinator observed advancing playback at 0.706 seconds, nonpaused, duration 3; screenshot is supplementary, not standalone playback proof. | PASS |
| Unsupported visual inference | Final provider output has no supported claims and unknown `Whether the pool has step-free wheelchair access`; selected evidence included the explicit unknown accessibility fact. Final response has no citations or media. Existing UI frames the unknown as `Could not confirm`. No wheelchair/step-free conclusion is inferred from illustration/video. | PASS |

Runtime model reported by provider: `grok-4-1-fast-reasoning`; existing configured deployment, adapter and bounded selector/answer workflow retained. These are coordinator-executed real calls, independently reviewed by this reviewer; fake tests were not treated as model evidence.

Read final `browser-observations.json`: actual production Next proxy, isolated PostgreSQL and browser evidence records direct fourth-hotel route and unknown route; decoded 640×360 image; decoded 3-second MP4 advancing and ending; visible VTT/fractional seek; fake-provider mobile viewport 390×844 with scroll width 390; delayed 45-second media followed by hotel switch and session renewal shows no late media/transcript; seven Blob creations and seven revocations; no observed token in URL. Source lifecycle guards and cleanup were separately reviewed. The real-image screenshot is 612 pixels wide and is **not** evidence of a live 390-pixel viewport; 390-pixel layout evidence belongs to the separately recorded fake-provider browser run. The mislabeled video layout screenshot is mapped as video evidence, not image proof.

Usage independently summed from all `live_provider` events: **5 guest attempts, 10 provider calls; 6,391 input / 323 output / 13,899 provider-reported total tokens**. Preserve provider total as reported. Three final attempts pass; two earlier image attempts remain failures (one 502, one HTTP 200 semantic failure). No failed attempt is erased and no HTTP 200 alone is counted as PASS. Monetary cost is unknown; no extra live rerun is requested by this review.

The reviewed AC evidence now separates offline/fake checks, real PostgreSQL/proxy/browser observations, and real model semantics. Source review and these bounded acceptance observations have no outstanding blocking finding. This clearance does not establish real-hotel/operator sources, universal model correctness, deployment, push/commit state, parent/epic completion or milestone closure.

## Final delivery formatting delta

Compared all 189 files against live/test candidate `184753fd…`. Exactly one file changed: `tests/contracts/test_sprint3_media_api.py`. Appending exactly one newline to its final bytes reproduces the prior file's SHA256, proving the final change only removes one trailing blank line. No product file changed. Final fingerprint is **`5b7f71cba464767f9d73ce59fc352c0b32556477378d6b8bb0c46d4b430a4384`**. No tests or live calls were rerun for this formatting-only change; prior relevant verification and all three final semantic acceptance cases remain valid on identical product source.

Coordinator reports the live provider API was stopped after bounded acceptance and the local demo uses the offline fake provider with real PostgreSQL and approved PNG/MP4/VTT. Treat that continuing demo as offline/fake; it does not replace or invalidate the recorded real-model acceptance. Recorded live accounting remains five attempts / ten calls / 13,899 provider-reported total tokens. **No outstanding blocking review finding.**
