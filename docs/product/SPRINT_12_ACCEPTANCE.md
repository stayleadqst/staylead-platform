# Sprint 12 — B11: kết quả kỹ thuật

Official backlog: [B11 #34](https://github.com/stayleadqst/staylead-platform/issues/34); sprint record: [#110](https://github.com/stayleadqst/staylead-platform/issues/110). Core duy nhất B11, đầy đủ AC1–3; D02 không nhận. Policy `pilot-retention-24h-ops7d-v1`; M1–M6 giữ nguyên.

Candidate nguồn gồm 213 files, fingerprint `8ec664f8f849b7883d6f30eef97cc6be8fdb0c047d3bebf730b239c1070763af`, base `be3f738aa7ba7231b3ff556dbb8bbcf29f9c71bf`, owner `sprint-12-retention-transport`, target `sprint-5-canonical-brief`. [Manifest](evidence/sprint-12/candidate-final.json) pin nội dung nguồn; trạng thái pending trong manifest là snapshot lúc đóng băng. Publication/merge thực tế ghi ở #110, không suy ra từ SHA base.

| AC | Kết quả và bằng chứng |
| --- | --- |
| AC1 | PASS: hết hạn/xóa chặn token/replay/brief/transcript/consumer cũ; UI xóa nội dung, media và copy, abort/fence dữ liệu về muộn; timer và resume check. Q tái hiện độc lập lỗi language preference và lock qua expiry trước sửa, rồi xác nhận nguyên reproducer PASS. |
| AC2 | PASS: bearer phải khớp SID/HID; xóa lặp own session trả204 kể cả signed token đã hết hạn; token sai/property khác bị từ chối. Hai tab thực tế giữ session còn lại hoạt động. Delete/sweep đồng thời giữ đúng một quota reservation. |
| AC3 | PASS: controlled clock qua24h và +8ngày; startup catchup/background nearest-expiry/shutdown và CLI; xóa toàn bộ content/derived/orphan. Chỉ quota metadata đã redaction tốiđa600s, không token/SID gốc/clientID gốc/prompt/answer/trace, trong giới hạn≤7ngày. |

[Q final](evidence/sprint-12/q-final-review.json) PASS technical DoD, cả3finding đã đóng; [validation](evidence/sprint-12/validation-final.json): backend208PASS/exit0; focused B11 PG9PASS; web54contracts/lint/typecheck/configured productionbuild PASS; compile/diff-check PASS. Ruff tổng exit1 còn đúng3I001 baseline (settings/guest_chat/store), không lỗi mới; [đối chiếu exact baseline](evidence/sprint-12/ruff-baseline-comparison.json). Không báo toàn bộ Ruff xanh.

Browser→local productionNext→API→privatePostgreSQL đã chạy với provider deterministic: [desktop/two-session](evidence/sprint-12/browser-observations-v1.json), [mobile/error/retry/inflight/timer](evidence/sprint-12/browser-observations-v2.json). Timer20s là override test; policy thật24h. Q đọc observations và xem screenshot, không nhận các browser actions là tự Q thực thi. Web8pins không đổi nên tái sử dụng gates hợp lệ.

Đây là kiểm chứng local/offline. Không live inference, deploy, real-hotel acceptance hoặc bảo đảm physical cleanup khi deployment tương lai ngừng chạy. Startup catchup/CLI là đường hỗ trợ đã kiểm. Không suy stakeholder acceptance từ tests/Q; Review/feedback/Retro được ghi theo thời điểm thực ở #110 và record closure sau sự kiện.

Lịch29/10/2026 +07: starts_at09:32:09 (clock đầu tiên quan sát trong planning), ends_at11:40; Review11:15, Retro11:30. Planning story table đã hiển thị chat và readback GitHub trước coding. Không tạo milestone Sprint12.

[Counters](evidence/sprint-12/counters.json) giữ toàn bộ lần thất bại và inherited S10/S11. Liveness3/3 hết; harness/lint4/4 hết sau Hieu cho phép đúng một vòng thêm. Lần sửa fixture đầu tiên chưa reserve trước là process deviation, không được hợp thức hóa hồi tố. Không reset theo function/session. Runtime actual model/effort/usage không exposed = unavailable; requested builders Luna/high và fresh Q Sol/high. Không claim enforced read-only/deadline supervisor.
