# Sprint 2 — Guest Q&A website acceptance

**Verified locally, ready for delivery.** Core: F06 #14, B01b #72, B02b #73 and coordination #71. Hieu approved autonomous execution on 2026-10-23. Optional #74 was not started; parent #17/#19 and epics retain their remaining obligations.

Guest can open the correct hotel chat on desktop/phone, ask naturally, receive grounded answers and provenance, continue the conversation and explicitly retry without mixing sessions or duplicating turns.

## Candidate and scope

- Baseline `e4864515e577f14fc8cf045564a110ddb479160f`; delivery revision is the commit containing this file. [Product/test manifest](evidence/sprint-2/candidate-manifest.json): SHA256 `18d3bcc622df08d5bbd1809c239e6840552a478e33db3bffb0da122794aa3437`, Next build `_ViitmhnAxCRDswxR8RL1`.
- Target: local Next production build → fixed same-origin proxy → FastAPI → real isolated PostgreSQL → existing Azure Foundry Grok adapter. No cloud deployment or paid resources. Browser failure injection was local verification infrastructure, not product code.
- FAQ architecture M6 → M3 → M1 → M3 → M6. No trip brief, M4/M5 or runtime multi-agent planner. Shared chat receives domain resources through composition; Hospitality owns its registration/content/renderer/prompt.
- Model `grok-4-1-fast-reasoning`, deployment `cc-dev-grok-4-1-fast-reasoning`. Fixture knowledge-v1 has CITY109, BEACH108, RETREAT110 guest facts. Config/source/fact versions1.0; schema2. Full imported timestamps/provenance are in observations.
- Builders: gpt-6-luna/high. Independent read-only review: gpt-6.1-sol/high. Coordinator performed actual browser, integration, semantic comparison and delivery. File ownership/contracts recorded before parallel work; mandatory execution guides match the user originals byte-for-byte.

## Local validation

| Check | Final result |
| --- | --- |
| Backend suite, dedicated real PostgreSQL; model providers fake/disabled | **30 passed**, zero Azure calls |
| Web composition/client/proxy/chat contracts | **19 passed**, zero Azure calls |
| Web ESLint, TypeScript, Next production build | PASS |
| Affected backend Ruff and Python compilation | PASS |
| Independent source review, fixes and targeted rereview | No outstanding blocking finding |
| Credential/public-artifact scan | PASS; no known credentials, guest Bearer tokens or secret DSNs in delivery |

Warnings: Node22 experimental TypeScript stripping; existing Starlette/httpx deprecation. No manual GitHub CI run/rerun, CI waiting gate or workflow changes. Automatic workflows may run on delivery; no CI success is asserted here.

## AC map

[Browser observations](evidence/sprint-2/browser-observations.json), [sanitized events](evidence/sprint-2/events.json) and [live responses/usage](evidence/sprint-2/live-observations.json) distinguish fake transport tests from real Grok semantics.

| AC | Evidence and observed outcome |
| --- | --- |
| F06 AC1 | Actual landing/chat takes content, theme, renderer and binding from Hospitality registration. Shared chat has no domain implementation import. Composition contracts pass. |
| F06 AC2 | Unknown profile rejected by contracts. Actual browser wrong domain and version999 each show clear incompatibility before session/message POST; composer disabled, no fallback. |
| F06 AC3 | Test-only alternate registration selects different landing/theme/API target without changing shared chat; no domain-to-domain import. |
| F06 AC4 | Public static artifacts exclude server API target, Azure key variable/value, signing secret, private DB DSNs and sampled catalog content. Documented public inputs are profile/contract metadata; server owns upstream/knowledge/secrets. |
| B01b AC1 | Desktop keyboard Tab→Send/Enter and actual phone390×844 send/answer. Branding, AI and synthetic disclosure visible; innerWidth390/scrollWidth390. [Phone screenshot](evidence/sprint-2/mobile-fake.png) uses fake provider, not semantic proof. |
| B01b AC2 | Separate tab sessions/hotels, correct scoped evidence. Literal script/img attributes, ampersands and mixed Unicode display inert; injected image count0, unchanged title. Evidence metadata rendered as text, no invented source URL. |
| B01b AC3 | Delayed double-click produces one POST. Lost response after committed200: same-ID explicit retry returns stored answer with zero additional provider calls/messages. request_in_progress/unknown completion blocks new composer turns. Confirmed terminal timeout retries with NEW ID only on guest action. |
| B01b AC4 | Hotel change clears transcript/context; late message and delayed session creation ignored. Reload opens new anonymous session. Real same-session reference resolves correct restaurant/floor. |
| B01b AC5 | provider_auth does not auto-renew guest session. Controlled invalid_session offers explicit fresh chat without resending old question. Non-envelope422, timeout and unknown transport normalize without false answer/staff acknowledgement. Actual expiry enforcement remains covered by real-PG tests. |
| B02b AC1 | Actual website/Grok answers multi-part breakfast/parking; no planner/identity collection. Conditions, numbers and subject independently checked. |
| B02b AC2 | Supported claims/provenance stay in the selected hotel; helipad unknown is explicit; two seeded conflicting check-in records both shown with explicit conflict, no silent choice. |
| B02b AC3 | CITY multi-part/reference/partial/conflict, French BEACH and Japanese RETREAT independently compared to fixture facts and explicit seed, not HTTP status/citation/confidence alone. |
| B02b AC4 | French and Japanese guest questions answered from Vietnamese sources without language whitelist. Observed model calls/usage captured; no translation/router/critic/judge loop added. |
| S2-C AC1–3 | Contracts/ownership and handoffs kept separate; findings repaired by source owner; per-AC observations, version manifest and accurate child/parent scope retained. Only evidenced core items can be marked Done at delivery. |

Contexts are independent browser tabs with per-tab in-memory tokens, not separate cookie containers. No persistent-session recovery, physical deletion, full accessibility certification or arbitrary-language quality guarantee is claimed. Images/video, operator publishing, real-hotel acceptance and Azure deployment remain outside this sprint.

## Real-model cases and failed attempts

| Case | Expected / final observed | Result |
| --- | --- | --- |
| CITY multi-part | CITY040 Bến Gió/floor1/06:30–09:30; CITY046 covered parking/reference40/100000VND per vehicle/night/no reserved space. All requested parts correct. | PASS |
| CITY reference | Same-session “restaurant you mentioned” resolves Bến Gió/floor1/CITY040. | PASS |
| CITY partial/conflict | Breakfast06:30–09:30; helipad unconfirmed; fixture00515:00–23:00 and temporary CONFLICT00517:00–22:00 both shown with explicit source conflict. Expanded provenance correct. | PASS |
| BEACH French | Vịnh Nhỏ06:30–10:00; family pool07:00–19:00 and under12 direct adult supervision. Additional child/shared-facility/local-hours policies all sourced; guest age is not presented as a sourced fact. | PASS |
| RETREAT Japanese | Thông Sương07:00–09:30/Monday closed; free/reference18 parking, narrow access and >16 seats require confirmation. Correct hotel and conditions. | PASS |

Saved browser snapshots: [CITY final](evidence/sprint-2/live-city-final.txt), [French final](evidence/sprint-2/live-beach-final.txt), [Japanese](evidence/sprint-2/live-retreat.txt). Reviewer independently checked requested content and cited fixture facts. [CITY screenshot](evidence/sprint-2/live-city-final.png) includes a deliberately seeded conflict; that seed was then deleted from the isolated acceptance DB and remaining count0 verified. No fixture/oracle or prior user demo DB was changed.

Selective reuse avoids unnecessary live reruns: positive initial Japanese observation is reused. A final offline probe confirms the same semantic-selector branch, identical selected IDs040/046/078 and no conflict expansion; the later history filter has no effect on its empty history. French success preceded the history-filter-only fix, but its session had no prior successful messages, so that projection is unchanged. CITY multi-part was rechecked after retrieval repair; final reference/conflict ran after the context filter. The evidence records actual run boundaries rather than claiming all cases were rerun on one build.

Failed attempts remain in accounting: initial CITY conflict was a semantic miss despite200; two French attempts returned502unsupported_output; one later CITY reference returned502invalid_model_output. Final success does not erase failures.

## Repairs and independent review

1. Unresolved logical turn allowed a new request; compatibility failures were generic; AI disclosure missing. UI fixed and regression-covered, independently cleared.
2. Actual browser found root URL join changing authority; review caught double-slash prefix edge. Proxy now clones URL then assigns pathname. Root/prefix/double-prefix regressions and actual production proxy journey pass.
3. CITY conflict retrieval missed check-in due history and generic-token coverage. Current-question direct-fact IDF coverage drives the existing conditional selector gate; history gets lower ranking weight. Both retrieval paths include conflicting versions; conflict metadata uses final evidence. Existing context/output limits remain; no silent conflict truncation.
4. Confirmed French rerun echoed guest age8 in a claim whose source supported only policy12. Prompt now applies sourced policy without restating unsupported guest numbers. Numeric guard unchanged. The first failed French output was not retained, so its exact cause remains unknown.
5. CITY reference echoed prior parking046 after selection retained only040. Selector still sees history; answer history now excludes assistant lines unsupported by final facts. Evidence-ID guard unchanged; regression and actual reference rerun pass.

Independent read-only reviewer cleared each targeted source delta and assessed successful CITY/French/Japanese browser observations. No outstanding blocking finding. Remaining generative variability is not a claim of universal accuracy; unsafe outputs continue to fail closed.

## Token and credential controls

**11 guest turns,19 observed Grok calls**, including all failed attempts and targeted reruns. Provider-reported usage: **38,358 input /2,238 output /59,309 total tokens**. Totals are preserved as reported (not recomputed from visible input/output); monetary cost unknown. No provider error lacked an observed usage result in this run. Default tests/build/startup made zero Azure calls; no189-case live evaluation or LLM judge. Only final generated JSON was captured privately for diagnosis; no hidden reasoning requested/saved.

Azure credentials, guest Bearer tokens and secret DSNs stay outside GitHub/source/history/issues/logs/evidence and client assets. Only configuration names/placeholders and non-secret metadata are documented. Existing prior user demo and PostgreSQL service remain untouched. Local browser demo is not a production deployment.
