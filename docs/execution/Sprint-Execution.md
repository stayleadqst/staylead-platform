Hãy tuân thủ `AGENT_EXECUTION.md` và `Not_overthinking.md`, lập team agents phù hợp và thực thi **Sprint hiện tại** theo backlog của project.

## Coordinator Agent

Luôn phải có **01 Coordinator Agent** có năng lực reasoning, judgment và decision-making cao nhất, chịu trách nhiệm điều phối toàn bộ Sprint.

Coordinator Agent phải:

- Liên tục theo dõi progress, trạng thái, dependency, blocker và quality của tất cả sub-agent.
- Chủ động kiểm tra kết quả của sub-agent trước khi cho phép chuyển sang bước tiếp theo.
- Khi sub-agent yêu cầu confirmation, decision hoặc next action, **Coordinator Agent phải tự phân tích và đưa ra quyết định phù hợp ngay**, không để sub-agent dừng chờ human.
- Khi xuất hiện blocker, dependency, lỗi, thiếu input hoặc tình huống bất thường, Coordinator Agent phải chủ động:
  - điều tra nguyên nhân;
  - xác định root cause;
  - chọn giải pháp tốt nhất;
  - giao nhiệm vụ cho agent phù hợp;
  - yêu cầu retry, fix, test hoặc review;
  - tạo ticket mới nếu cần;
  - đưa ticket cần thiết vào Sprint hiện tại;
  - thay đổi execution order nếu cần;
  - tiếp tục các công việc không bị phụ thuộc.
- Nếu một agent bị stuck, thất bại nhiều lần hoặc chất lượng không đạt yêu cầu, Coordinator Agent phải thay đổi approach, giao cho agent khác hoặc tạo agent chuyên trách để xử lý.
- Không được để team idle chỉ vì đang chờ confirmation từ một agent khác.
- Sau mỗi milestone hoặc thay đổi quan trọng, xác định ngay **next best action** và ra lệnh cho team tiếp tục thực thi.
- Chỉ yêu cầu human intervention khi thực sự bắt buộc, ví dụ:
  - cần credential/quyền truy cập mà agents không có;
  - cần quyết định business/product không thể suy ra hợp lý từ backlog hoặc tài liệu hiện có;
  - hành động irreversible hoặc vượt ngoài quyền được phép.
- Trước khi escalation cho human, phải thử tất cả giải pháp hợp lý trong phạm vi cho phép và cung cấp rõ:
  - blocker;
  - root cause;
  - các giải pháp đã thử;
  - bằng chứng;
  - giải pháp đề xuất tốt nhất.

## Sprint Execution

- Hoàn thành tất cả user story theo acceptance criteria và quality gate của project.
- Chủ động giải quyết mọi issue phát sinh trong phạm vi được phép.
- Không đánh dấu Done nếu acceptance criteria hoặc quality gate chưa đạt.
- Luôn thực hiện test, review và verification cần thiết trước khi Done.
- Nếu phát hiện regression hoặc quality issue, tự động mở lại công việc và fix.
- Có thể thực thi song song các story độc lập để tối ưu progress.
- Coordinator Agent phải liên tục tìm công việc có thể thực thi tiếp thay vì để agents chờ.
- **Sprint scope có thể được mở rộng trong quá trình execution nếu việc đó cần thiết để hoàn thành Sprint.**

## Blocker Handling

Trong quá trình thực thi Sprint, nếu Coordinator Agent phát hiện bất kỳ vấn đề nào liên quan tới ticket hiện tại, dependency, technical debt, defect, infrastructure issue, missing capability hoặc bất kỳ công việc bổ sung nào cần thiết để hoàn thành Sprint:

### First Priority

**Ưu tiên số 1 là xử lý vấn đề ngay trong Sprint hiện tại.**

Coordinator Agent phải:

1. Xác định root cause và phạm vi ảnh hưởng.
2. Kiểm tra xem đã có ticket phù hợp trong Product Backlog hay chưa.
3. Nếu đã có ticket:
   - đưa ticket đó vào **Sprint hiện tại**;
   - điều chỉnh priority phù hợp;
   - assign agent xử lý ngay.
4. Nếu chưa có ticket:
   - tạo ticket mới;
   - thêm trực tiếp ticket đó vào **Sprint hiện tại**;
   - đặt priority phù hợp với mức độ ảnh hưởng;
   - assign agent xử lý ngay.
5. Thực thi ticket unblock cho tới khi:
   - root cause được xử lý;
   - blocker được remove;
   - test/verification PASS.
6. Sau đó tiếp tục story ban đầu và đưa story đó tới DONE.

Không được mặc định:

**Blocked → tạo backlog item → để Sprint sau xử lý.**

Flow mặc định phải là:

**Blocker → investigate → create/find ticket → add vào current Sprint → execute → verify → unblock → continue original story.**

## Sprint Scope Expansion Rule

Nếu một ticket mới là cần thiết để hoàn thành một story hoặc để Sprint đạt Definition of Done thì ticket đó **tự động trở thành một phần của Sprint hiện tại**.

Không được trì hoãn ticket đó sang Sprint sau chỉ vì:

- ticket ban đầu không nằm trong Sprint;
- công việc không được dự kiến khi planning;
- phải sửa component khác;
- phải bổ sung test;
- phải sửa CI/CD;
- phải sửa infrastructure;
- phải refactor một phần code;
- phải cập nhật dependency;
- phải sửa integration;
- phải bổ sung missing implementation.

Coordinator Agent có quyền mở rộng Sprint scope hợp lý để đạt Sprint Goal.

## Escalation Strategy

Nếu giải pháp đầu tiên không hiệu quả:

**Retry → investigate deeper → alternate approach → specialist agent → independent review → fix → verify.**

Nếu cần, Coordinator Agent phải:

- chia nhỏ blocker thành nhiều ticket;
- tạo specialist agent;
- chạy investigation song song;
- yêu cầu second opinion;
- rollback approach không hiệu quả;
- thử implementation khác;
- sửa dependency liên quan;
- cập nhật test hoặc infrastructure cần thiết.

Không được giữ một story ở trạng thái Blocked một cách thụ động.

## Human Intervention

Chỉ escalation cho human khi blocker **thực sự không thể giải quyết bởi agents**, ví dụ:

- thiếu credential hoặc permission chỉ human mới cấp được;
- cần external approval;
- cần business decision không thể suy ra từ specification;
- cần hành động ngoài phạm vi authorization;
- cần resource bên ngoài mà agents không thể tự tạo hoặc thay thế.

Ngay cả khi cần human intervention:

- Coordinator Agent phải tiếp tục tất cả công việc không phụ thuộc;
- chuẩn bị sẵn next action để thực thi ngay khi input có;
- không để toàn bộ Sprint dừng lại.

## Autonomous Decision Rule

Mặc định:

**Sub-agent → báo cáo trạng thái / vấn đề → Coordinator Agent phân tích → quyết định → ra lệnh next action → sub-agent tiếp tục thực thi.**

Không sử dụng flow:

**Sub-agent → hỏi human → chờ.**

Trừ khi human intervention thực sự bắt buộc theo các điều kiện đã nêu ở trên.

Coordinator Agent được quyền chủ động:

- approve/reject kết quả của sub-agent;
- yêu cầu rework;
- yêu cầu thêm test;
- yêu cầu independent review;
- thay đổi task assignment;
- tạo agent mới;
- chia nhỏ task;
- thay đổi execution sequence;
- retry bằng approach khác;
- xử lý dependency;
- tạo ticket mới;
- đưa ticket backlog vào current Sprint;
- thay đổi priority;
- cập nhật backlog;
- quyết định next action phù hợp nhất.

## Definition of Sprint Success

Mục tiêu cao nhất là đưa Sprint đến trạng thái **DONE với chất lượng tốt nhất có thể**.

**Không chấp nhận việc kết thúc Sprint với blocker có thể giải quyết bằng engineering work.**

Sprint chỉ được xem là DONE khi:

- tất cả story thuộc Sprint đạt Acceptance Criteria;
- tất cả blocker có thể xử lý bằng engineering work đã được giải quyết;
- tất cả ticket bổ sung cần thiết để unblock Sprint đã được hoàn thành;
- tất cả required tests và quality gates PASS;
- không còn regression đã biết chưa xử lý;
- dependency cần thiết cho Sprint đã được hoàn tất;
- Coordinator Agent đã thực hiện final verification toàn bộ Sprint.

Nếu xuất hiện công việc mới cần thiết để đạt các điều kiện trên:

**Add vào Sprint → Execute → Verify → Continue**

thay vì:

**Move to Backlog → Defer to next Sprint.**

## Primary Objective

Coordinator Agent phải tối ưu mọi quyết định theo thứ tự ưu tiên:

1. **DONE Sprint**
2. **Correctness**
3. **Quality**
4. **Resolve blockers**
5. **Maintainability**
6. **Execution speed**

Mục tiêu vận hành là:

> **Do not manage blockers. Eliminate blockers.**

Và:

> **Do not defer work that is required to complete the Sprint. Bring it into the Sprint and execute it.**

Sprint phải được đưa tới **DONE bằng mọi giải pháp hợp lý trong phạm vi quyền hạn, quality gate và project constraints cho phép**.

## Reporting

Báo cáo theo mẫu trong `AGENT_EXECUTION.md`, thể hiện rõ:

- Sprint progress;
- trạng thái từng user story;
- công việc đang được từng agent thực hiện;
- các story đã Done;
- các story đang In Progress;
- blocker đang được xử lý;
- root cause;
- ticket được kéo thêm vào Sprint;
- ticket mới được tạo;
- quality/test status;
- quyết định quan trọng của Coordinator Agent;
- next actions đang được thực thi.

**Không dừng sau khi report.**

Sau mỗi lần report, Coordinator Agent phải tiếp tục xác định và ra lệnh cho **next best action** cho team cho đến khi Sprint đạt Definition of Sprint Success hoặc gặp một blocker thực sự bắt buộc human intervention.

**Bắt đầu thực thi ngay.**