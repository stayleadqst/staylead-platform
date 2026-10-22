# Sprint 1 — nghiệm thu API Q&A

Sprint goal đạt trong phạm vi API: guest mở phiên ẩn danh theo hotel, gửi câu hỏi; M3 gọi M1 lấy facts đủ điều kiện của đúng hotel, dùng Foundry Grok trả lời có căn cứ và thể hiện phần chưa biết/mâu thuẫn. Không bắt khai chuyến đi. Chưa deploy.

Phạm vi: #10 F05, #11 F02, #13 F04, #66 A01a, #67 A02a, #68 B01a, #69 B02a; điều phối #70. Các parent #16–#19 và epic vẫn còn nghĩa vụ riêng.

## Candidate và môi trường

- Product tree cuối: `56f5dfe3f9c8f75828c1d3200255888e157ea46c` (trước khi thêm hồ sơ nghiệm thu này). Commit chứa báo cáo là bản bàn giao; các file ứng dụng không đổi sau tree này.
- Model thực: `grok-4-1-fast-reasoning`, deployment development hiện hữu `cc-dev-grok-4-1-fast-reasoning`, Azure Foundry OpenAI-compatible Chat Completions `/openai/v1/`. Không tạo resource mới. Endpoint/credential chỉ cấu hình riêng trên server.
- PostgreSQL thật, cluster nghiệm thu riêng qua Unix socket; schema version **2**, migration và bootstrap chạy bằng command riêng, không chạy DDL khi startup.
- Dataset `staylead-hospitality-knowledge-v1`, ba hotel synthetic: CITY **109**, BEACH **108**, RETREAT **110** guest facts; tổng **327**. Không đưa oracle/eval answers vào serving. Hash prompt/config/data và request IDs nằm trong [live observations](evidence/sprint-1/live-observations.json).
- Builder `gpt-6-luna / high`; reviewer độc lập `gpt-6.1-sol / high`; coordinator kiểm integration/semantic expected facts và delivery. Không dùng model runtime làm coding agent hay LLM judge.

## Bằng chứng theo acceptance criteria

| Item / AC | Expected → observed và bằng chứng |
| --- | --- |
| F05 AC1 | Hai cập nhật cùng expected version → chỉ một commit, còn lại conflict. Contract/PG regression và probe hai transaction đồng thời thực: version cuối 1. |
| F05 AC2 | Request retry không thêm side effect; scope sai bị chặn → HTTP replay giữ nguyên response/call count; payload đổi hoặc reuse khác session 409; token khác session 403. `test_http_guest_session_scope_and_idempotent_response_retry`. |
| F05 AC3 | Core thay được schema domain → alternate Pydantic domain validator được áp dụng qua typed envelope; boundary test cấm shared platform import Hospitality/infrastructure. `test_state_contracts_are_typed_and_can_mark_source_results_stale`, architecture suite. |
| F05 AC4 | Biểu diễn version/freshness/dependency → typed `ResultDependencies`, `SourceVersion`, current/stale/needs-check và affected dependencies; contract test kiểm stale. Chưa triển khai room/stay invalidation engine. |
| F02 AC1 | Empty DB + migration riêng → schema2; startup không migrate. Explicit migration CLI, integration schema assertion và startup/source inspection. |
| F02 AC2 | State tồn tại sau restart, queries scoped → tạo engine/app mới đọc đúng committed session/version; HTTP token/repository scope checks giữ cách ly. [Offline probes](evidence/sprint-1/offline-ac-probes.json). |
| F02 AC3 | DB thật giữ atomicity/idempotency → PostgreSQL version/conflict/replay tests pass; probe concurrent transactions một success/một conflict. |
| F02 AC4 | Transaction lỗi không partial state → rollback regression; deadline/cancellation trước commit giữ version0/messages0; DB errors không trả DSN. `test_postgres_expected_version_atomicity_and_transaction_rollback` và các deadline/cancellation tests. |
| F04 AC1 | Neutral provider contract cho fake và Azure → consumer chỉ dùng typed request/result/error; composition chọn adapter; unsupported provider bị từ chối, không giả success. Contract/architecture tests và mocked transport probe. |
| F04 AC2 | Smoke thực có metadata/usage → actual API observations có model/deployment/provider request IDs và usage; dùng chung evidence B02a, không gọi trùng để chia báo cáo. |
| F04 AC3 | Timeout/auth/429/cancellation → probe transport offline 9 cases: 200, 401, 403, 429, 500, 400, timeout, malformed response, cancellation. Typed errors, cancellation được truyền; adapter không retry tự động. Live timeout cũng trả 504, không false success. |
| F04 AC4 | Credential chỉ server → web build/lint/typecheck pass trên frontend không đổi; kiểm public config, composition và staged credential scan. Không có Azure key/session signing secret trong source/evidence. |
| A01a AC1 | Bootstrap đúng hotel/version, reject config lỗi → ba hotel import thành công; thiếu timezone bị reject và published row không đổi. Parse toàn pack trước persist, transaction mỗi hotel. |
| A01a AC2 | Mapping/config server giữ quyền → extra client hotel/config fields không thay trusted slug mapping; slug ngoài allowlist 404; không có public config-write endpoint hoặc staff/contact tool. |
| A01a AC3 | Public projection không private reference → sentinel private_reference/api_key bị loại; config có synthetic/source_pack; unknown knowledge giữ status qua M1. Không coi fixture approval là khách sạn thật duyệt. |
| A02a AC1 | Chỉ guest/approved/valid/scoped → 327 eligible facts; internal record CITY004 không vào serving; nguồn hết hạn bị loại cả runtime. Invalid source/root/schema báo lỗi. Fixture projection + source-validity integration test + offline probes. |
| A02a AC2 | Retrieval có provenance đúng hotel → public evidence gồm hotel/fact/source ID/version/section/imported_at; ba live hotel giữ facts riêng. Loader chỉ đọc manifest/properties/sources/facts, không đọc oracle. |
| A02a AC3 | Nhiều ý/thiếu/mâu thuẫn → CITY breakfast+parking đủ hai ý; partial helipad tách unknown; seeded conflict trả cả hai cửa sổ check-in và nêu mâu thuẫn. Không mặc định LLM rewrite/reranker. |
| A02a AC4 | Import/query lỗi không lộ secret → typed/generic errors; fixtures được gắn synthetic trong config/evidence. Đây là importer/retrieval/DB thật trên dữ liệu mẫu. |
| B01a AC1 | Phiên ẩn danh đúng hotel → POST session 201, không login/phone/email; trusted slug mapping và signed token. HTTP PostgreSQL integration + real HTTP live runs. |
| B01a AC2 | Cách ly phiên/retry → 401 missing token, 403 token/path mismatch, 409 idempotency mismatch; completed replay không gọi model lần nữa hoặc thêm messages. |
| B01a AC3 | Pending/error/context/payload đúng → request reservation, finite timeout/cancellation, versioned commit/rollback và recent context đúng phiên; API trả JSON data, không render HTML. Reference follow-up CITY vẫn trả đúng tầng nhà hàng. Browser rendering thuộc parent. |
| B02a AC1 | Câu nhiều ý có căn cứ → CITY breakfast 06:30–09:30 tại Bến Gió tầng1; parking40 chỗ tham chiếu,100000 VND/xe/đêm, không giữ chỗ; citations đúng CITY040/046. |
| B02a AC2 | Reference/missing/conflict và authority → CITY follow-up đúng tầng1; helipad ở unknown; conflict seed nêu cả15:00–23:00 và17:00–22:00, không tự chọn. Offline guards bác số/URL/foreign references do guest/model đưa vào; credentials không đưa vào model context, không có tool SQL/HTTP/staff để source text đổi quyền. Không tuyên bố chứng minh miễn nhiễm mọi prompt injection. |
| B02a AC3 | Khác ngôn ngữ nguồn và provider lỗi → French BEACH breakfast06:30–10:00/pool07:00–19:00; Japanese RETREAT breakfast07:00–09:30, nghỉ thứHai,18 chỗ miễn phí, xe>16 chỗ cần xác nhận. Không language enum đóng. Transport errors kiểm offline, không gọi model lỗi để tạo fallback. |
| B02a AC4 | Trace/version/opt-in/bounds → [JSON observations](evidence/sprint-1/live-observations.json) ghi model/request/calls/tokens/facts/tree/hash; harness default opt-out exit2 trước HTTP; unit/build/startup không gọi LLM. Không chạy toàn189 oracle cases, không critic/judge mặc định. |

## Local validation và review

- **28/28 backend tests pass**, gồm PostgreSQL thật, fake model; [output](evidence/sprint-1/backend-tests.txt). Một warning deprecation của Starlette TestClient/httpx, không phải failure.
- `ruff check --config apps/api/pyproject.toml apps/api/src tests tools/evals/sprint1_live.py`, compileall và `git diff --cached --check`: pass. Lệnh Ruff ban đầu thiếu project config nhận config từ thư mục cha; lệnh đúng như README pass, không đổi source để xử lý cấu hình ngoài repo.
- Frontend không đổi: `npm run lint`, `npm run typecheck`, `npm run build` đã pass, dùng lại evidence hợp lệ; không chạy lại vì delta chỉ backend/docs.
- Reviewer sửa/kiểm lại bốn finding thực: unknown/conflict guard bypass; hạn dùng nguồn; deadline SQL có late commit; duplicate inline citation requirement. Reproducer hai lock với budget1s hiện trả504 khoảng1s, sau nhả lock vẫn version0/messages0. Cleanup không đổi completed thành error. Tất cả được clear trên tree7165; projection nhỏ được coordinator kiểm; final conflict prompt được cùng reviewer kiểm delta, không còn blocking finding.
- Live evidence giữ theo tree đã chạy. Tree799ac chỉ rút gọn semantic payload, giữ provenance/full facts server-side; tree56f5 chỉ làm rõ protocol unknown/conflict. Nghiệm thu lại đúng nhánh conflict và unknown bị ảnh hưởng; reuse supported/multilingual/reference evidence, không chạy lại toàn bộ live set.

## Giới hạn và usage

- Câu hỏi tối đa2000 ký tự; session24 giờ; recent context tối đa8 messages (retrieval dùng4 gần nhất); retrieval tối đa400 eligible records/hotel, tối đa20 answer facts. Selector chỉ nhận metadata ID/topic/subject/field khi lexical coverage<0.45; không gửi toàn nội dung catalog. Context answer tối đa22000 ký tự; output mặc định700 token, selector140; tối đa2 model calls/turn; không automatic retry. Provider timeout25s, whole-turn45s mặc định. Giá trị và clamps nằm trong source version ghi ở trên, không phải hard billing cap Azure.
- Tổng **11 paid guest-turn attempts**: **8 thành công**, **3 lỗi** trong quá trình sửa/nghiệm thu. Quan sát được **10 model calls thành công**, **30.745 total tokens** theo provider. Usage/calls của3 lượt lỗi không được trả đủ nên **unknown**, không tính thành0; chi phí tiền **unavailable**. Các tổng token provider có thể gồm thành phần ngoài input/output, không tự cộng lại để thay total.
- Ba lỗi: CITY inline-citation guard502; conflict provider timeout504; conflict prose reference guard502. Các defect protocol đã sửa và affected cases pass; timeout được giữ trong accounting. Không có test tự động gọi Azure.
- Cùng câu CITY sau projection: input3443 →1630 token, một model call và facts/conditions vẫn đúng. Đây là đo input của một câu, không cam kết mức tiết kiệm toàn sản phẩm.
- Conflict chỉ thêm một row synthetic vào DB nghiệm thu riêng rồi xóa trong `finally`; không sửa fixture/oracle. Không phải nguồn khách sạn thật có mâu thuẫn.
- Chỉ read-only FAQ API. Chưa website chat, operator auth/publish, nguồn khách sạn thật, OCR/ASR/video understanding, nhu cầu chuyến đi, phòng/lịch trình, booking/payment/staff action hoặc deployment. Session expiry chặn sử dụng sau hạn; chưa có job physical retention/delete. Parent và các story tương ứng giữ Open.

Hai tài liệu Hieu cung cấp đã lưu nguyên bản tại [AGENT_EXECUTION.md](../execution/AGENT_EXECUTION.md) và [Not_Overthinking.md](../execution/Not_Overthinking.md); AGENTS và working rules yêu cầu áp dụng thường xuyên cùng AI_ARCHITECTURE.
