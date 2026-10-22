# Kiểm soát overthinking và công việc không thiết yếu

Áp dụng cho coordinator và mọi agent. Không tạo thêm quy trình, agent hoặc tài liệu để giám sát mục này.

## Chỉ làm việc phục vụ mục tiêu

Trước một hoạt động, xác định nó giúp:
- Hoàn thành AC hoặc đầu ra sản phẩm nào;
- Gỡ blocker thực tế nào;
- Hoặc cung cấp bằng chứng bắt buộc nào.

Nếu không xác định được, không thực hiện.

Ưu tiên đóng defect, hoàn thiện integration và đưa candidate đạt yêu cầu tới merge. Không thay thế tiến độ sản phẩm bằng nghiên cứu, chỉnh tracker hoặc viết packet.

## Phân tích đến mức đủ để hành động

- Đọc để trả lời một câu hỏi cụ thể; không đọc toàn repo trước mỗi thay đổi.
- Khi đã biết expected behavior, nguyên nhân và phạm vi ảnh hưởng, bắt đầu sửa.
- Khi chưa chắc cơ chế, dùng reproducer hoặc slice nhỏ để phân biệt các giả thuyết.
- Không tiếp tục so sánh kiến trúc khi đã có phương án đủ đáp ứng AC và kiểm chứng được.
- Chọn giải pháp đơn giản nhất đủ đúng, tương thích với hệ thống hiện có.
- Không suy đoán trường hợp xa ngoài phạm vi rồi mở rộng thiết kế để xử lý chúng.

Không dùng “cần hiểu kỹ hơn” làm lý do kéo dài nếu chưa chỉ ra câu hỏi còn thiếu và quyết định nào phụ thuộc câu trả lời.

## Giữ kiểm chứng đúng trọng tâm

- Dùng lại evidence hợp lệ.
- Chỉ chạy thêm kiểm chứng khi có thay đổi, failure hoặc rủi ro chưa được giải quyết.
- Không lặp full suite, audit hoặc Review chỉ để tăng mức yên tâm.
- Reviewer tập trung AC, known failures, regression và rủi ro thực tế trên đường producer → consumer.
- Không biến cải thiện tùy chọn hoặc yêu cầu ngoài phạm vi thành blocker mới.
- Không bỏ qua lỗi thật hoặc hạ tiêu chuẩn để làm nhanh.

## Coordinator phải chủ động cắt việc thừa

Nếu agent đọc/nghiên cứu lặp lại mà không tạo quyết định, reproducer, code hoặc bằng chứng cần thiết:
- Thu hẹp câu hỏi và phạm vi;
- Chuyển sang thử nghiệm nhỏ có kết quả quan sát được;
- Hoặc dừng hoạt động đó và giao công việc hữu ích khác.

Không giữ agent chạy chỉ vì nó còn tiếp tục phân tích. Không tăng model/effort hoặc mở thêm reviewer khi chưa có lý do cụ thể.

Các cải thiện ngoài AC chỉ ghi ngắn vào hồ sơ hiện có nếu đáng giữ; không tự triển khai hoặc tạo ticket mới.

Áp dụng bằng phán đoán trong lúc làm. Không lập thêm báo cáo tuân thủ, checklist hoặc vòng approval cho mục này.