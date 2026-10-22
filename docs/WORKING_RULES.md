# Working rules — Staylead Platform

Áp dụng cho sprint planning, implementation, review và sửa lỗi; cho coordinator và mọi agent.
Yêu cầu kiến trúc bắt buộc nằm trong [AI_ARCHITECTURE.md](architecture/AI_ARCHITECTURE.md).
Đây là quy tắc làm việc, không phải bằng chứng tính năng đã triển khai.

## 1. Làm đúng mục tiêu và backlog

- Bám user story, acceptance criteria (AC), dependency và Definition of Done hiện hành.
- Trước mỗi hoạt động, xác định AC/đầu ra sản phẩm, blocker thực hoặc bằng chứng bắt buộc mà nó phục vụ. Không xác định được thì bỏ hoạt động đó.
- Không tự thêm yêu cầu, ngưỡng nghiệm thu, dependency hoặc đổi nghĩa AC. Nếu scope sprint không khớp story, nêu chênh lệch và đề xuất refinement trước khi cam kết; không âm thầm bỏ AC.
- Chỉ triển khai nhánh workflow cần cho story, nhưng luôn giữ ranh giới M1–M6. Không dựng đủ sáu module nghiệp vụ cho một câu hỏi đơn giản.
- Planning không tự cấp quyền implementation, deploy, mua tài nguyên, gửi thông báo hoặc thay đổi backlog.

## 2. Phân tích đủ để hành động

- Đọc để trả lời câu hỏi cụ thể; không đọc toàn repo trước mỗi thay đổi.
- Khi biết expected behavior, nguyên nhân và phạm vi ảnh hưởng, bắt đầu thực hiện. Cơ chế chưa rõ thì dùng reproducer hoặc slice nhỏ.
- Chọn giải pháp đơn giản nhất đủ đúng với kiến trúc đã chốt. Không tiếp tục so sánh kiến trúc hoặc mở rộng thiết kế cho giả thuyết xa ngoài scope.
- Ưu tiên sửa defect, hoàn thiện integration và bàn giao kết quả kiểm chứng được. Không thay tiến độ bằng nghiên cứu, chỉnh tracker hoặc viết tài liệu không cần thiết.
- Không thêm framework, agent, reviewer, model escalation hoặc vòng xử lý AI nếu chưa có lý do cụ thể từ AC hoặc lỗi quan sát được.
- Coordinator dừng hoặc thu hẹp hoạt động nghiên cứu lặp lại không tạo quyết định, reproducer, code hoặc bằng chứng cần thiết.

## 3. Thực thi và kiểm chứng

- Hoàn thành công việc đã được phép qua implementation → integration → local validation → review/fix → commit/push khi được phép.
- Kiểm chứng AC và lỗi thực tế trên đường producer → consumer; giữ nguyên tiêu chuẩn dù chọn giải pháp đơn giản.
- Chạy tests, lint và compile/build phù hợp phần thay đổi. Dùng lại evidence còn hợp lệ; chỉ mở rộng hoặc chạy lại khi có thay đổi, failure hoặc rủi ro chưa xử lý.
- Không dùng fixture/fake để tuyên bố đã kiểm chứng model thật, nguồn thật hoặc môi trường thật. Chỉ đánh dấu Done khi toàn bộ AC và DoD có bằng chứng.
- Không tự tạo ticket hoặc triển khai cải thiện ngoài scope; chỉ ghi ngắn trong hồ sơ hiện có nếu đáng giữ.
- Không tạo báo cáo tuân thủ, checklist giám sát hoặc vòng approval riêng cho các quy tắc này.

## 4. Quyền hạn và báo cáo

- Giữ các repo Staylead cũ nguyên trạng; chỉ đọc tham khảo khi cần. Phát triển mới trong `staylead-platform`.
- Không tự chạy/rerun GitHub CI hoặc lấy việc chờ CI làm bước bàn giao; không bypass required checks. CI tự chạy phải được báo đúng sự thật.
- Phân biệt rõ proposed, implemented, locally verified, pushed và deployed; nêu blocker cụ thể, không cam kết khi thiếu bằng chứng.
- Runtime AI mục tiêu hiện tại: Foundry Grok `grok-4-1-fast-reasoning`, qua adapter thay thế được. Đây không phải tên model của coding agent; không tự thay model hoặc thêm reasoning setting chưa được xác minh hỗ trợ.
- Tuyệt đối không lưu Azure credentials (API keys, tokens, client secrets, connection strings có secrets) lên GitHub: source/history, issues/comments, PR, logs hoặc evidence. Chỉ dùng tên biến và placeholder trong nội dung công khai; giá trị thật ở local config bị Git ignore hoặc secret store được phép. Redact trước mọi bàn giao; không thu thập credentials chỉ để lập sprint.

## 5. Tiết kiệm Azure LLM và kiểm thử không phát sinh phí mặc định

- Giảm số lần gọi và token Azure LLM tới mức cần thiết để đáp ứng AC; không hy sinh tính đúng đắn hoặc phá workflow M1–M6 để giảm chi phí.
- Unit tests và lệnh test/build mặc định không gọi LLM thật, kể cả khi máy có credentials. Dùng fake/mock/recorded responses cho logic có thể kiểm chứng offline; không ghi secrets vào recordings.
- Real-LLM integration/eval là nhóm riêng, phải được bật tường minh trong phạm vi kiểm chứng đã được phép; không tự chạy trong CI, startup, watch mode hoặc mỗi lần chạy unit tests.
- Chọn bộ case nhỏ nhất đủ kiểm chứng các AC cần model thật, giới hạn calls/retries/output/context cho run và ghi usage khi provider cung cấp. Không tự chạy toàn bộ dataset hoặc dùng LLM chấm mọi response.
- Dùng lại evidence còn hợp lệ; chỉ chạy lại case bị ảnh hưởng bởi thay đổi hoặc lỗi. Không lặp real-model runs chỉ để tăng mức yên tâm.
- Không giả lập thành công khi tránh live call: AC cần model thật mà chưa chạy phải được ghi chưa kiểm chứng. Không tự đặt ngân sách tiền hoặc cam kết chi phí chưa đo.

Nội dung focus và tránh overthinking được tổng hợp từ `Not_Overthinking.md` do Hieu cung cấp ngày 2026-10-22. Các quy tắc cần áp dụng đã nằm trong file này, không phụ thuộc đường dẫn máy cá nhân.
