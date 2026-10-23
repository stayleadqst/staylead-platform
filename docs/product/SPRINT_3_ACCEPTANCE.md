# Sprint 3 — complete hotel packs and approved media

**Verified locally:** a new hotel can join through a complete data pack, then guest chat answers from its approved facts and displays relevant approved PNG/MP4/VTT evidence. Core #75, #76, #77 and coordination #78 satisfy their scoped AC. Delivery revision is the commit containing this document. No deployment was performed; milestone closure remains Hieu's decision.

Baseline `21ef9a222236b9d46afd236310670c599c40dea4`. Final source/test/fixture fingerprint **`5b7f71cba464767f9d73ce59fc352c0b32556477378d6b8bb0c46d4b430a4384`**, 189 files; exact hashes and review are in [candidate versions](evidence/sprint-3/candidate-manifest.json) and [independent review](evidence/sprint-3/review-findings.md). Documentation/evidence are excluded from that product fingerprint. Live acceptance used source/test/fixture fingerprint `184753fd700f968485944fde43df84129d3b4c9856410d83e6ffd217966c0704`; the final difference is one EOF blank line removed from a test. A web whitespace-only EOF cleanup followed the production build; neither changed product behavior. No further semantic product changes followed review or final live acceptance.

## Implementation and ownership

Builder A `gpt-6-luna/high` owned knowledge contracts, strict Hospitality schema, trusted local CLI, validation/staging, explicit PostgreSQL migration, atomic persistence, eligible-media repository, fixtures and producer tests. Builder B `gpt-6-luna/high` owned API/composition, deterministic answer-media projection, binary proxy/client, data-driven chat route, browser renderer and consumer tests. Fresh reviewer `gpt-6.1-sol/high` reviewed the candidate independently without product edits. Coordinator handled integration/runtime/acceptance/documentation/delivery; its exact runtime model/effort is unavailable.

W0 froze typed contracts and one editor per file before W1 parallel work. A delivered the K1 foundation, then K2 validation and joint publication; B began against contracts without waiting for either story to close. No circular story completion dependency. Actual ownership/progress was recorded on #75–#78 before implementation status. Findings went to the responsible owner, with targeted rereview.

FAQ remains M6 → M3 → M1 → M3 → M6, with no trip brief, M4/M5 or runtime multi-agent. Shared platform has no Hospitality dependency. Provider logic remains behind the existing adapter. Media binding adds **zero model calls**: only final validated cited fact IDs feed the approved scoped mapping; no guest/model URL is accepted.

## Candidate, data and limits

- Database schema **3**, applied explicitly; pack schema **1**; guest contract **1**, additive media field. Runtime startup does not migrate/import or call the model.
- New synthetic hotel `HTL-S3-FOURTH`, slug `garden-terrace-demo`; pack `sprint3-hospitality-demo-v1`, version1, config/source/fact versions1. Five authored serving facts, one illustrated PNG, one synthetic H.264 MP4 and linked authored VTT. The original three fixture hotels retain 327 facts. No real-hotel/operator approval is implied.
- Canonical pack hash `c24d5a27db72a4625c568ee6d402222c10541a797035281e4d2f074270515ef7`. Identity hashes untouched canonical sorted UTF-8 manifest JSON plus sorted verified asset path/hash/size records. It is a versioned application format, not a claim to implement RFC8785. Replay is a no-op; any changed manifest/config/version rejects without writes.
- PNG 4,899 bytes, MP4 24,867 bytes, VTT 70 bytes; exact SHA256 values are in [import/asset observations](evidence/sprint-3/initial-import-success.json). MP4 duration verified as3 seconds; approved authored reference0.5–2.5 seconds. Files decode through actual media tools and browser playback.
- Limits: PNG≤5MiB, MP4≤20MiB, UTF-8 VTT≤256KiB, complete pack **including manifest**≤64MiB, maximum400 guest facts. Stat limits precede bounded reads; bytes/hash/MIME/decode/duration/cues are verified before one transaction publishes config/sources/facts/metadata/verified bytes.
- Schema1 supports exactly one approved source version per fact and rejects unsupported multi-source input. Effective serving dates intersect fact/source dates; raw input still defines immutable identity. Whole-file guest approval is mandatory; approving only a segment does not authorize serving the file. Unsupported/oracle fields reject before publication.

## Local checks

[Check results](evidence/sprint-3/check-results.json) preserve command outputs and boundaries:

- Full backend suite **58 passed** against dedicated real PostgreSQL with fake/disabled providers. Subsequent parser/bounds/prompt deltas were checked through the affected suites: **27 validator tests** and **17 grounded-Q&A tests** passed. This is not a claim of a later full63-test run.
- Web **23 contract tests**, ESLint, TypeScript and Next production build passed. Modified Python Ruff, compileall and final diff check passed.
- Broad Ruff additionally reports one unchanged baseline `I001` in the existing orchestrator import block. The identical finding was reproduced from `git show21ef9a2` with the same configuration. New-file import findings were fixed; no unrelated baseline formatting was changed.
- Existing Starlette/httpx deprecation and Node experimental TypeScript-stripping warnings remain warnings.
- No default automated test/build/startup called Azure. No manual GitHub CI run/rerun, workflow/protection change or CI-wait gate. Automatic workflows may run on push; no CI success is asserted.

## Acceptance mapping

| AC | Expected → verified observation / evidence |
| --- | --- |
| K1-AC1 Atomic publication | Complete hotel4 config/sources/5facts/3media publish together. An actual SQL source-ID collision after staging rolls back hotel/pack/facts/media; initial failed integration import also left the hotel absent. Producer PG test and [initial failure](evidence/sprint-3/initial-import-failure.json). |
| K1-AC2 Idempotency/immutability | Replay produces no new rows. Changed pack version, fact content and hotel config each reject while prior data stays unchanged. Raw date changes hidden by effective-date clamps still change identity. [Real-PG boundary probe](evidence/sprint-3/pack-boundary-observations.json), producer PG test. |
| K1-AC3 Scoped validation | Foreign/missing source or version, invalid/duplicate/global fact IDs, unsupported internal/unapproved fields/formats and invalid paths reject before publish. Actual global fact-ID collision leaves new hotel absent and prior400facts unchanged. Validator suite, PG rollback test and boundary probe. |
| K1-AC4 Backend onboarding | Hotel4 resolves from DB by ID/slug and public API without per-hotel code. Old three hotels and unknown lookup verified through actual production proxy. [HTTP observations](evidence/sprint-3/http-observations.json). |
| K1-AC5 Bounds | Actual PostgreSQL import and runtime reader return exactly400facts.401 rejects atomically, without silent truncation. Manifest+assets exact total-boundary and stat-before-open checks were independently probed. Boundary observations and reviewer report. |
| K2-AC1 Provenance | Each descriptor binds hotel/source/version/fact IDs/media ID/hash and valid clip span; bytes match imported assets. Public descriptors omit filesystem path and arbitrary URL. Import/HTTP observations, typed contracts. |
| K2-AC2 Approval | False or missing whole-file approval and unsupported segment-approval fields reject; no partial video authorization is converted into whole-file permission. Validator approval tests and strict schema. |
| K2-AC3 Asset validation | Scope/hash/MIME/size, absolute/traversal/symlink paths, corrupt media, malformed VTT, missing separators/dangling cues and cues outside verified clip duration/span reject. Import validates before transaction. Original accepted malformed cases were repaired and independently reprobed. Validator27/review; manifest now counts toward64MiB. |
| K2-AC4 Authored evidence | Captions and illustrations explicitly say synthetic/authored; model uses approved textual facts, not raw visual recognition. Actual unsupported accessibility case remains unknown. [Live observations](evidence/sprint-3/live-observations.json). |
| K2-AC5 No oracle | Strict schema rejects oracle/expected-label fields. Serving importer only reads approved manifest/files; evaluation expectations stay outside serving/model input. Validator oracle tests and source review. |
| K2-AC6 Scoped read | Actual PNG/MP4/VTT bytes/hash/MIME match; wrong hotel, expired/ineligible sources/facts and missing assets yield no asset. Repository tests and actual HTTP scope checks. |
| K3-AC1 Data-driven route | Direct `/hotels/garden-terrace-demo/chat` opens hotel4 from backend lookup. Removed demo whitelist admission. All old hotel lookups work; actual unknown page gives unavailable message and disabled composer. [Browser observations](evidence/sprint-3/browser-observations.json). |
| K3-AC2 Grounded binding | Only validated cited fact IDs determine response media. Retrieved-but-uncited facts do not attach; no model-selected URL or extra binding call. Projection API test, actual image/clip responses. |
| K3-AC3 Authenticated binary | Actual Next→API→PG returns byte-identical PNG/MP4/VTT, exact MIME and `no-store`. Missing Bearer401, wrong session403, wrong hotel404, expired persisted session401, missing asset404; no media bytes. Streaming oversized PNG/MP4/VTT without Content-Length and unsupported MIME return502. [HTTP](evidence/sprint-3/http-observations.json), [proxy bounds](evidence/sprint-3/proxy-bounds-observations.json). |
| K3-AC4 Actual playback | Browser decoded640×360 PNG and MP4. Video advanced from0.5 seconds to ended3.0 with no error; VTT visibly reads “The pool deck faces the garden.” Correct button0:00.5–0:02.5. Desktop and390×844 mobile verified, mobile scrollWidth390. [Desktop](evidence/sprint-3/desktop-caption-final.jpg), [mobile](evidence/sprint-3/mobile-caption-final.jpg); actual playback measurements in browser observations. |
| K3-AC5 Text/unknown compatibility | Text-only breakfast returns07:00–10:00 without media; unsupported visual accessibility stays unknown. Existing session/retry/follow-up regressions pass in backend/web suites; final live clip/visual reference uses the same session. Two live presentation defects were fixed, not waived. |
| K3-AC6 Session lifecycle | Test-only outer browser probe observed7Blob creations and7revocations.45-second delayed media cannot appear after client hotel navigation or explicit expired-session renewal; final DOM image/video counts0. Tokens remain in memory/auth headers, not URLs or artifacts. Browser events and [renewal snapshot](evidence/sprint-3/session-renewal-no-late-media.jpg). |
| K3-AC7 Real semantics | Three final Grok cases pass independent expected-vs-source comparison: balcony/image; garden-facing clip0.5–2.5s/caption; step-free accessibility unknown. HTTP200 alone did not pass the earlier failed semantic attempt. [Independent expectations](evidence/sprint-3/semantic-expectations.json), live observations and final reviewer report. |
| C-AC1 | Actual models/ownership/contracts recorded before implementation; one editor/file, W1 parallel consumer start, K1 backend and K3 browser acceptance kept separate. #78 progress and ownership table above. |
| C-AC2 | Each concrete finding had owner/repair/reproducer and targeted rereview; no unrelated audit, repeated full evaluation or scope extension. Source blockers are cleared. Review and retained failures. |
| C-AC3 | Fixed source/test/fixture hash, schema/data/config/model/build versions, all AC evidence, failed attempts/usage and local demo recorded. Parent source/operator obligations and milestone decision remain open. |

Actual PostgreSQL lock probe also holds `knowledge_media` in ACCESS EXCLUSIVE mode: one-second whole-turn deadline returns504 in **1.058s**, state_version remains0. Independent fake slow-media probe also confirms event-loop responsiveness. [Deadline evidence](evidence/sprint-3/media-deadline-observations.json).

## Live model results and retained failures

Existing Azure Foundry deployment `cc-dev-grok-4-1-fast-reasoning`, runtime model `grok-4-1-fast-reasoning`. Only explicit opt-in acceptance used it. No OCR/ASR/vision, LLM judge,189-case evaluation or model call for media selection.

| Attempt | Result |
| --- | --- |
| Image1, earlier prompt |502 invalid_model_output. Correct balcony claim plus unsupported “no illustration” assertion without cited fact IDs. Fail-closed guard retained.2calls /2024reportedtotal tokens. |
| Image2, first prompt fix |200 but semantic FAIL: correct balcony/image with “Authored illustration” incorrectly in unknowns.2calls /2307reportedtotal. |
| Image3, final prompt/fresh session |PASS: correct balcony, approved image/caption, unknowns empty.2calls /2165reportedtotal. |
| Clip, same final session |PASS: garden-facing, exact0.5–2.5seconds, correct video/VTT and playback.2calls /3196reportedtotal. |
| Unsupported visual inference, same session |PASS: step-free wheelchair access remains unconfirmed; no supported claims/evidence/new media.2calls /4207reportedtotal. |

Total **5 guest attempts,10 observed provider calls**, including failures. Provider-reported **6391input /323output /13899total tokens**. Total is preserved as provider-reported, not recomputed from input/output; monetary cost unknown. All observed calls returned usage; no missing failure usage was treated as zero. Prompt hashes and request IDs bind every attempt to its actual version. Coding-agent token usage is unavailable. Final image repeats the balcony claim once; this observed redundancy does not change its fact/evidence correctness.

Other retained repairs: missing flattened source reference and nullable media spans in early integration; VTT parser, source-expiry intersection, unsafe/dot-segment IDs, rejected unsupported multi-source mappings, canonical identity after date clamps, aggregate pack size, restored knowledge read protocol, media query deadline and fractional time label. Initial build lacked required public profile variables; supplying documented configuration resolved it. These failures remain in evidence/review, not hidden behind final success.

## Local demo and exclusions

Open **http://127.0.0.1:13003/hotels/garden-terrace-demo/chat** while the host/runtime is running. After separate explicit confirmation, Hieu authorized retaining a **live Grok demo for his own trial questions**. Next connects directly to the reviewed live API and isolated PostgreSQL; model calls occur only when a question is submitted, never at startup. The three final acceptance cases above were run separately and retained; subsequent user trial usage is outside their totals. Ask:

1. “Does the king room have a balcony? Show its illustration.”
2. “What view does the pool clip describe and what is its approved time reference? Show the clip.” Click **Play from 0:00.5–0:02.5**.
3. “Does that video prove step-free wheelchair access?” The answer should retain uncertainty.

Automatic approval review initially rejected retaining a live-Grok demo because of additional paid calls beyond bounded acceptance. The live API was stopped and an offline demo verified; Hieu then explicitly confirmed “Cho phép demo local gọi Grok khi tôi thử”, authorizing the retained live mode. No additional acceptance model call was made during this configuration change. The existing user demos/databases were untouched; this uses a separate local PostgreSQL runtime. Closing/sleeping the laptop can suspend localhost/network access. A local demo is not a deployment or a guarantee of execution while the host sleeps.

Synthetic authored data does not close A02 #18, B02 #19, real-source/operator work or E1/E2 obligations. No existing-pack refresh/revoke/append, OCR/ASR/vision, gallery/cross-hotel comparison, M2/M4/M5, second market, landing/QR, stretch #74, deployment, paid resources or budget increase. Parent/epic/milestone closure is not part of this delivery. Azure credentials, signing secrets, guest Bearer tokens and secret database DSNs remain outside source/GitHub/logs/screenshots/evidence.
