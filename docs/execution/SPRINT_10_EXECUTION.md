# Sprint 10 — Thực thi
<!-- staylead-sprint:10 -->

**Trạng thái thực tế:** Đang local validation và sửa P1 mới xác minh. Planning ban đầu INCOMPLETE; hồ sơ đã bổ sung muộn trên tracker chính [#105](https://github.com/stayleadqst/staylead-platform/issues/105), #29 In Progress/assigned, timebox/lịch đã chốt và readback đúng. Đây là corrective planning, không nhận đã qua gate trước coding. Chưa fullAC/DoD/QPASS hoặc closure/chuyển sprint.
**Sprint Goal:** Khách vẫn nhận được thông tin có căn cứ và có bước tiếp theo rõ ràng, đúng khách sạn khi thiếu dữ kiện hoặc trợ lý gặp lỗi.

## Quyền và ranh giới
Ủy quyền của Hieu ngày 2026-10-28 nằm tại AGENTS.md cấp workspace và bàn giao riêng cho phiên Sprint 10. Phiên này thực hiện đúng một sprint từ planning đến delivery, Sprint Review và Retrospective. Chỉ mở phiên Sprint 11 mới sau khi Review và Retro của Sprint 10 COMPLETE.

Giữ đủ M1–M6, AC và DoD hiện hành. Không gọi live product inference mới, deploy, mua tài nguyên, đổi credentials/hạ tầng dùng chung, liên hệ người ngoài, chạy/rerun CI thủ công, chờ CI làm gate hoặc bypass checks/protection. Các hạn chế lịch sử chỉ #30/preparation đã được quyền mới thay thế. Hieu đã trực tiếp cho phép tạo/cập nhật GitHub gồm thông báo tự phát sinh; không có quyền gửi riêng email/Slack/kênh khác.

## Phạm vi, DoR và dự kiến
Core: [#29 B08](https://github.com/stayleadqst/staylead-platform/issues/29), giữ nguyên đủ B08-AC1–3. Nghiệm thu kỹ thuật local dùng khách sạn synthetic, cấu hình test do server quản lý và provider giả có lỗi được kiểm soát; không nhận là dữ liệu/duyệt khách sạn thật hay production.

Dependencies #16/#19: tái sử dụng capability và evidence S1–S4 về cấu hình, nguồn và Q&A qua model thật; không coi parent Open là chưa có code. Không đóng các parent còn nghĩa vụ rộng hơn. AC1 giữ prompt/orchestrator hiện hành, dùng lại evidence CITY partial/conflict của S2 và kiểm tra hồi quy hiện tại. Phần contact/outage mới là deterministic, không cần gọi model thật.

D1: giữ phạm vi fixture synthetic đã có; chưa có dữ liệu khách sạn thật mới. D4: giữ chính sách expiry/source và giới hạn hiện hành 2 calls/turn, 25 giây/provider, 45 giây/turn, 700 output tokens; không đặt retention policy mới. Contact/hours là cấu hình tùy chọn theo hotel slug do server xác định, thiếu thì unknown; không suy từ model, chat hoặc nguồn.

Ước lượng S, gồm integration/QA/fix/delivery và các sự kiện; không phải measured velocity/ngày công. Hieu xác nhận sprint tối đa24giờ. C chốt starts_at2026-10-28T15:40:09+07:00 từ firstturn metadata, ends_at2026-10-28T17:00:00+07:00, Review16:45, Retro16:55. Các mốc được bổ sung muộn, không backdate. Một sprint/một session vẫn giữ. Inspection tại worker result/failure/phase; next_check_at16:30 hoặc kết quả worker/Q tới trước. Không tạo scheduler/controller framework.

## Nhánh và tài nguyên
- Repo stayleadqst/staylead-platform. Base đã xác minh qua GitHub connector: bcddfe84e5361587075f08aa01b9ac185998ca43 trên sprint-5-canonical-brief.
- Nhánh owner: sprint-10-helpful-fallback. Checkout sạch khi bắt đầu; không sửa nhánh S9 hay chọn main. PR83/89 cũ giữ nguyên.
- Git fetch CLI lỗi DNS trong sandbox; connector xác minh remote thành công.
- C sở hữu PostgreSQL riêng tại validation/sprint-10-20261028/pgdata, loopback55440, socket /private/tmp/staylead-s10-pg-20261028, role staylead_s10; database staylead_s10_test và staylead_s10_browser tách riêng. Không nhận tài nguyên dùng chung.
- API18540/web13540 đã chạy riêng; API1/2 dừng, API3 session85739 và websession82853 hiện doC giữ; không có inference thật.

## Nhóm thực thi
| Vai trò | Model / effort chính xác | Sở hữu và trách nhiệm |
|---|---|---|
| C điều phối | unavailable / unavailable | Contracts, integration, tracker/evidence, kiểm đường producer→consumer, publish/merge; không coding sản phẩm |
| B /root/b08_builder | gpt-6-luna / high | Backend contact/hours, UI liên hệ thuộc Hospitality, resource outage trung lập và tests được cấp lease; giữ đường semantic/M2/B09 |
| Q độc lập, context mới | gpt-6.1-sol / high | Candidate cố định, đầy đủ AC/DoD và negative cases; không sửa candidate; bắt đầu sau local gates |
| Hieu | Người | Quyết định nghiệp vụ hoặc quyền ngoài còn thiếu; agent không thay quyền của Hieu |

## Sprint backlog và kế hoạch công việc
**Danh sách user story cam kết:** đúng1story P0: [#29 — B08: Trả lời hữu ích khi thiếu dữ kiện hoặc dịch vụ lỗi](https://github.com/stayleadqst/staylead-platform/issues/29), đủ AC1–3, dependencies #16/#19 dùng lại evidence S1–S9; B gpt-6-luna/high triển khai, Q gpt-6.1-sol/high review độc lập, C integration/delivery. Không có stretch story. T0–T8 bên dưới là tasks của sprint, không phải user story mới.

**Sai sót planning thực tế:** kế hoạch đã được lưu trước coding nhưng C không trình bày trực tiếp danh sách story/ticket trong chat trước khi dispatch. Hieu nêu lỗi nghiêm trọng ngày28-10-2026; C đã bổ sung danh sách và lưu yêu cầu bắt buộc vào AGENTS.md cấp workspace. Không sửa lịch sử thành đã làm đúng. Từ sprint sau, hiển thị và lưu story→GitHub ticket/priority/AC/dependency/owner/trạng thái trước coding; không tự thêm approval gate. Trạng thái đồng bộ GitHub phải được nêu riêng và chính xác.

| ID / phase | Owner — model / effort | Phần việc / file ownership | Dependency / thứ tự | Đầu ra và kiểm chứng |
|---|---|---|---|---|
| T0 — Planning | C unavailable/unavailable; B Luna/high refinement | Chốt đủ AC #29, contract contact/hours và outage, phạm vi/leases | Hoàn tất trước coding | Record này, DoR/refinement, không bỏ AC |
| T1 — AC2 liên hệ | B gpt-6-luna/high | Settings booking_contact_hours_by_hotel; composition _booking_channel; Hospitality booking-channel.ts/turn-result-renderer.tsx và tests | T0; cùng owner làm tuần tự với T2 | Contact/hours đúng property, approved link và contact cùng dùng được, thiếu thì unknown, nêu rõ chưa gửi tin/liên hệ; kiểm scope/bounds/control chars/rendering |
| T2 — AC3 outage | B gpt-6-luna/high | GuestChat.tsx, resource outage trung lập, tests; API app và browser harness B08 | T0, contract T1 | Resource tĩnh đã review theo locale khi có; nếu thiếu thì nêu rõ English fallback; không phụ thuộc model hỏng/auto retry, giữ same-ID/partial receipt B09 |
| T3 — AC1 và vertical slice thật | C unavailable/unavailable; B Luna/high viết tests | B sở hữu tests B08; C chạy serial PG/API/web và lưu evidence | T1/T2 sẵn sàng; đóng lease trước Q | Supported partial + exact unknown/conflict/next step; cách ly property, thiếu contact, locale/RTL/fallback, timeout và tiếp tục hỏi; UI→API→processor→UI thật với provider giả được gắn nhãn |
| T4 — Local gates | C unavailable/unavailable | Tests backend bị ảnh hưởng, Ruff/compile; web contracts/lint/typecheck/build | T3 | Tất cả gates liên quan PASS trên candidate; reuse evidence không bị ảnh hưởng |
| T5 — Review độc lập và fix | Q Sol/high review; B Luna/high sửa; C unavailable/unavailable kiểm | Đóng băng candidate khi Q đọc; finding có reproducer và owner | T4 | Report Q mới, đủ AC1–3/DoD; giữ failure/counters, không lặp cùng cơ chế vô hạn |
| T6 — Delivery | C unavailable/unavailable | Commit/publish PR owner vào sprint-5-canonical-brief | T5 PASS và đủ scoped AC/DoD | Đối chiếu tree/head, merge khi GitHub cho phép; CI tự chạy có thể xảy ra, không manual/wait gate |
| T7 — Sprint Review/Retro | C unavailable/unavailable | Record này, acceptance/checkpoint | Biết kết quả T6 thật | Đánh giá Goal, demo/evidence và feedback thực; ghi rõ chưa có stakeholder feedback; Review kỹ thuật trong quyền và Retro dựa dữ liệu; dừng tài nguyên/đóng leases |
| T8 — Bàn giao | C unavailable/unavailable | Phiên mới Sprint 11 - Execution | Review và Retro COMPLETE, đã giải phóng resources, còn backlog khả thi trong quyền | Handoff gọn giữ refs/counters/decisions; không planning/coding Sprint11 trong phiên này |

## Tiêu chí nghiệm thu giữ nguyên
| AC | Kết quả kỳ vọng độc lập | Evidence dự kiến |
|---|---|---|
| B08-AC1 | Một ý có nguồn, ý khác thiếu/conflict: giữ phần có căn cứ, nêu đúng phần thiếu/conflict và bước xác nhận; không từ chối toàn bộ vì score thấp | Evidence CITY thật S2 chỉ cho đường còn hợp lệ + hồi quy API/UI/grounded contracts hiện tại |
| B08-AC2 | Khách muốn người thật và property có contact/hours: hiển thị đúng cấu hình property, không bịa số/deadline/acknowledgement, giải thích chưa thực hiện hành động ngoài | API projection, browser contact control/request, negative config/rendering và foreign property |
| B08-AC3 | Model timeout hoặc thiếu contact, có/không resource locale: fallback an toàn độc lập model, đa ngôn ngữ, timeout, khách tiếp tục thông tin và không retry vô hạn | Controlled provider fault qua API/browser, locale/RTL và client timeout contracts |

## Điều phối, token và counters
Tối đa4agent kể cả C; dùng C+B, rồi Q độc lập. Một file chỉ một editor; Q không sửa candidate. B được reuse cho fixes. Không broad audit, cleanup ngoài scope, full-suite lặp hoặc live batch. Tokens/telemetry ghi unavailable nếu runtime không trả; không tự đặt numerical budget/repair cap. Implementation ban đầu không tính repair; failure class, vòng sửa và lỗi operation được giữ riêng. Counters/allowances S1–S9 giữ nguyên/đã đóng. Live calls Sprint10=0; live allowance mới=0.

## Nhật ký thực tế
- Trước coding: lưu kế hoạch tiếng Anh ban đầu, sau đó chuyển sang tiếng Việt theo yêu cầu Hieu; không đổi nghĩa Goal/AC/phạm vi.
- Tạo issue điều phối GitHub bị automatic approval review từ chối vì có thể phát sinh thông báo ngoài. Chưa tạo issue hoặc milestone, không retry gián tiếp. Dùng record repo này làm tracker chính tương đương trong lúc tiếp tục engineering; đã hỏi lại quyền GitHub, phản hồi hiện tại yêu cầu dùng tiếng Việt, chưa phải xác nhận quyền mutation.
- B hoàn tất scan chỉ đọc, sau đó nhận lease T1–T3. C giữ docs/evidence và PG; Q chưa dispatch.
- PG init/start và tạo hai DB riêng thành công bằng scoped host execution.
- Root: grounded-QA/B09 contracts104 PASS; B09 PG10 PASS. Lần PG đầu có10 setup errors do sandbox chặn loopback Operation not permitted; host invocation chạy thành công. Logs tại validation/sprint-10-20261028, không có inference.
- C review delta ban đầu yêu cầu bỏ wording Hospitality/giả định có contact khỏi shared resource, thêm outage ở confirmation/answer-only, và tránh harness nhận answer cũ là recovery. Đây là kiểm integration trước candidate, chưa phải Q PASS.
- Official #29 vẫn Draft trên GitHub; trạng thái local thực tế IN_PROGRESS, B là owner.
- Web lint/typecheck/build và canonical web contracts47 PASS. Ruff đầu báo2 lỗi định dạng trong test API app; B sửa, root Ruff/compile PASS. Đây là lỗi chất lượng harness, không phải regression nghiệp vụ.
- Browser default lượt1: partial breakfast+helipad unknown đã hiển thị, nhưng typed contact request502 invalid_model_output/invalid preparation metadata; root HTTP độc lập tái hiện cùng lỗi. Chưa AC2 PASS. B nhận repair harness attempt1; không đổi production validators/prompt. API/web đang chạy riêng ở18540/13540; PG55440 do C giữ. Không live inference.
- Attempt1 bổ sung đúng schema preparation metadata (provider contracts4PASS) nhưng browser default-2 vẫn FAIL ở guard khác: purebooking intent lại có breakfast claims/helipad unknown ngoài phạm vi. Root HTTP tái hiện502 contentoutside-turnscope. Giữ nguyên failure class harnessoutputshape, đóng attempt1FAILED và giữ attempt2 trước mutation; B sửa test provider+contract phải đi qua validator thực. Không đổi source apps/AC. API1 đã STOPPEDexit0; API2 session21687 hiện chạy riêng, web82853/PG55440 doC giữ. Contact contracts7PASS, Ruff/compile/diffPASS trên delta đã sửa metadata; không coi đó là fullACPASS.

## Kết quả cuối sprint — chưa thực hiện
Review: NOT_RUN. Retrospective: NOT_RUN. Goal: NOT_EVALUABLE.
Implemented/locally verified/pushed/merged/deployed: chưa xác nhận đủ.

## Corrective planning và P1 — trạng thái mới nhất
**Tiến độ mới nhất:** P1fixed trong1productrepair; actualAPI→PG201/200 và Q sourceCLOSED trên pin025039c…/217. Root post-fixB09PG10PASS, backendRuff/compile/diffPASS; web47contracts/lint/typecheck/build còn hợp lệ vì websource không đổi. Browserdefault5PASS partial/contact/hours/missingcontact/propertyisolation/literalHTML. Q chấp nhận AC1/AC2technicalproof, chưa fullDoDPASS.

Harnessreadinessrepair3 đã dùng, giữ3previousfailures. Outage lần đầuFAIL vì providerfake ngủ2s rồiHTTP200 trướcwholeturn5s; configadapter1s không tự áp chofake. C dừng mutation khi cap3harnessđãhết; Hieu trực tiếp cấp thêm1vòng quaasyncreply. Attempt4reserved trướcmutation, tổngcap4 riêngB08harness, không liveinference/productsourcemutation/endsatextension. B sửa boundedfault clock→typedProviderError và phải kiểmAPI504trướcbrowser; AC3chưaPASS. Hai capsourceproduct1 vàharness4 được giữ riêng theo failuremechanism, không xóa hoặc reset history.

Hieu đã mở khóa hai input: GitHubcreate/update gồm thông báo tự sinh và sprintmax24h. #105 đã tạo làm sprintrecordchính (không có milestone riêng), #29 InProgress/assigned và cả2body readbackkhớp100%; xem tracker-journal.json. Các ghi chú chờ quyền bên trên là lịch sử, không còn blocker hiện hành. Body8phase trong processpackage khớp ZIP8/8; binding mới giữ4agentinclC và không claim restart/wake đãhoạtđộng.

Sau2harnessrepairs, actualAPI→PG cho purebookingcombinedpreparation hợp lệ/channelsrỗng vẫn502 do genericmeaningfultextguard. Q xác nhận P1 sourcecontradiction và thu hồi provisionalsourcePASS pin8f65426d…/217. C giữ lượt P1-booking-empty attempt1 trước mutation; B sở hữu core optionalcallback trung lập, predicate Hospitality exactpurebooking, compositionwiring và actualorchestrator/APInegatives. Không thêm fact/unknown hoặc broadenintent để láchguard; 2harnessrepairs giữ lịch sử. Websource/build không đổi và reuse hợp lệ. Sourcepin cuối cần tạo mới và Q kiểm delta.

## Đối chiếu quy trình gốc theo yêu cầu Hieu
ZIP /Users/ccvn/Downloads/autonomous-agile-process-v2.0.zip có SHA256944b8521d2fb8b161fb2756ae6c541132f1e0beb0c19c3df0e6d9a2148816896, trùng provenance trước đây. Body8phase giữ nguyên ZIP, khác ở header preparation cũ; README/policy/runtime-binding đã lỗi thời so với quyền mới. Phát hiện thực tế: tracker chưa sẵn sàng khi dispatch; không có ends_at/lịchReviewRetro cố định; lời ghi planningcomplete quá sớm; bindingcontinuousfalse chưa cập nhật; nguồn ZIP phân biệt24h đề xuất với60min/3repair/3retry đã xác nhận trong hội thoại nguồn, cần map provenance đúng project thay vì gọi chung là ví dụ. Chưa có evidence runtime restart/wake độc lập, không nhận fullunattendedautomation. T7 chỉ là kế hoạch, không được mặc định QPASS thành Review/RetroCOMPLETE.

C đã gửi hai câu hỏi cần input thật: quyền GitHub có thông báo tự sinh sau automatic-review rejection, và fixed timebox chưa có trong project authority. Không coi yêu cầu dùng tiếng Việt hoặc phê bình quy trình là câu trả lời phê duyệt. Trong lúc chờ, C giữ product frozen và tiếp tục localverification; B Luna/high chỉ nhận lease sửa binding docs/header/runtime JSON, không đổi body8phase hay xây controller. Các kết quả/evidence cũ và counters được giữ.


## FINAL — 2026-10-29T05:48:45.862450+07:00
B08 #29 Done; PR106 merged c333bc49c84aa57844e465aee5d0139c6baec2fa, source/test pins và tree verified. FullAC/local/Q PASS. Review bắt đầu16:47:52, hoàn thành16:53:39+07. Retro COMPLETE muộn tại2026-10-29T05:48:45.862450+07:00; ends_at vẫn17:00. Tại hạn delivery/Review hoàn thành nhưng Retro missed; không backdate. Xem báo cáo acceptance cuối cho lessons/limits/cleanup. Không implementation mới sau hạn; chỉ đóng hồ sơ docs/tracker.
