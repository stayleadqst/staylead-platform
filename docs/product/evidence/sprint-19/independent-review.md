# Q19 — Review độc lập full B03 #20

**Ready: YES — full B03 AC1–3 và DoD v2.2 đạt trong phạm vi kỹ thuật đã công bố. Không có finding chặn.** Đây là nghiệm thu capability đã tồn tại; không phải tính năng mới, deployment, real-hotel acceptance hoặc quyền gọi model mới. C còn sở hữu publication/merge, cập nhật trạng thái #20 và Sprint Review/Retro; Q không nhận các bước đó đã hoàn tất.

Review bắt đầu 05/11/2026 09:12:20+07; requested `gpt-6.1-sol/high`; actual model/effort/tokens/cost: **unavailable**. Q đọc độc lập #20/#1 trong GitHub snapshot, policy hiện hành, source, assertions, raw logs và evidence lịch sử; chỉ ghi `q/**`, không sửa candidate, không chạy suite/model/browser/service, không tạo subagent.

## Candidate đã kiểm

- Repo `/private/tmp/staylead-s19-canonical`, branch `sprint-19-b03-full-acceptance`.
- Base `7a4c46b3472ed139e6c6d12e3ceefad8341afd56`; tree `3548641d08a6e251b3edc02f230a2ef11259244d`.
- Frozen fingerprint `ad304cb047b7a6813dd0219452ce09ba4c4acf3f5a7af02e867fe0a3c586592a` — Q xác minh 5/5 file trong manifest và 13/13 pin source/test/config/fixture của case packet. Base SHA không bị trình bày là đã chứa thay đổi chưa commit.
- Schema cuối `2549e19d3b9855f2f16d56dff6cc389041519c659ae1c8dc8656c772f6a8a398`; AST `765f18494d92b3c09853f93f4a807bcd855ff3f21cd9735ffbb9134e63142ee7`. Q tự so byte với `git show` base: đúng một dòng trắng; AST trùng.
- Q tự so trực tiếp checkout S17 còn giữ: 155/156 file byte-identical; file còn lại là schema trên, AST-identical. `pyproject.toml`, web package/lock/tsconfig trùng. Pin S17 consumer `70ed4d8600fd9a83aba511ba594c4c14107b161185705dc0ca8e2b29a3bb0a4a` và verdict `cdde948c886d738dc879c0113cd58e447bf8d640789ba77a51bc51528395cb18` được đọc; chỉ postfix được dùng làm PASS.

## AC và đường producer → consumer

| AC | Kết luận và căn cứ |
|---|---|
| AC1 | **PASS.** Current contracts giữ 2 adults/dates khi thêm child thiếu tuổi, cấp UUID ổn định, giữ pending-age; cập nhật chính child đó thành 7 và xóa đúng pending. Typed operations và source fields có assertions độc lập; PG receipt giữ utterance/ref. Current composed API→processor→PG→answer xác nhận child ID đề xuất là ID được commit và đưa vào answer input. Exact semantic unknown→7 qua AI đã có trong S5/S6, được giữ là bằng chứng lịch sử có candidate/model limits, không gọi là S19 live PASS. |
| AC2 | **PASS.** Current schema/cross-field assertions kiểm partial/ambiguous/conflicting date endpoints, bảo toàn confirmed values, đúng field pending; missing age không được tự điền. Persistence kiểm property/session, expected-version CAS, atomic rollback, một winner cạnh tranh; composition validate trước confirmation/commit. `set_dates` chỉ nhận endpoints, nights được server tính, không nhận nights tùy ý do model tự đặt. Các nhánh này cùng current 26-test batch. Chưa có empirical case riêng “date range hợp lệ nhưng số đêm khách nói khác range”; việc nights là derived/read-only chứng minh canonical không lưu nights tự mâu thuẫn, không tự chứng minh AI đã hỏi đúng trong mọi utterance loại đó. PASS dựa vào các date-cross-field/ambiguous/missing-age cases đúng AC, không nhận case chưa chạy là PASS hoặc suy universal language correctness. |
| AC3 | **PASS.** Current composed test kiểm confirmation trước commit, brief v1 và cùng child ID thật sự vào answer input; replay không gọi thêm provider/không nhân child. Sau 5 FAQ, lượt nights vẫn dùng persisted brief v1; source/ref, stale và partial recovery có assertions. Historical S5 two-session receipt probe trả 404/0 provider calls cho foreign receipt; Q đối chiếu current session/property clauses và signed-confirmation guards. Prompt hiện hành giữ negation/no-edit, stable references; S5/S6 semantic paraphrase/negation/missing-age giữ đúng nhãn lịch sử. Schema strict không có trường passport/full name. |

B01 #17 còn Open không tự chặn khi scoped session/API seam đã đủ cho consumer, đúng DoR #1; Q không nhận published-property/operator obligations của #17 đã đạt. #19 không phải formal dependency và vẫn Open. #11/#13/#10 có `GitHub-dependency-readback.json` ghi normalized fields từ C fetch_issue thực tế trước planning và đều Closed; Q đã đọc artifact này, không gọi đó là lần fetch riêng của Q. Dependency acceptance vẫn dựa vào interfaces đang thực sự được exercise trong current API/PG run, không suy đủ từ trạng thái ticket. Không phát hiện D4/D5 business decision còn thiếu cho slice này.

## DoD v2.2

| Mục | Disposition |
|---|---|
| 1 — pinned expected/observed | Đạt: current packet và independent pins; current/offline/S17/S5/S6 không bị gộp thành một run. |
| 2 — actual vertical slice | Đạt bằng accepted S17 postfix UI→API→processor→UI trên source tương thích trực tiếp, cộng current PG consumer. Không nhận một UI/build mới ở S19. |
| 3 — independent expectations | Đạt: arithmetic, ID, pending, version, source, actual provider input có oracle riêng; provider double không tự chấm mình. |
| 4 — relevant guards | Đạt: scope/auth/confirmation/CAS/atomic/replay/stale được source và current/historical compatible evidence kiểm. Không có renderer/URL change. |
| 5 — AI evidence | Đạt theo AC hiện hành: các semantic cases độc lập có historical real-model observations; không có yêu cầu mới phải gọi live trên whitespace-only S19. Chúng không chứng minh current served-model quality hoặc real source. |
| 6 — local gates | Đạt: raw current batch **26 PASS/0 SKIP** trên base; 7-file compile. Exact final target trước restore đã có **8 overlapping contracts PASS**, 7-file configured Ruff PASS và changed-schema compile. Q xác minh hash raw logs và exact target/AST; reuse hợp lệ theo agent-execution §4, không phải waiver hoặc fresh post-reapply PASS. Không cộng thành 34 unique. Web checks/build S17 được reuse do web/config không đổi. |
| 7 — fresh Q | Đạt tại frozen manifest này, không finding acceptance/authority/result còn mở. |
| 8 — evidence types | Đạt: synthetic facts, offline provider, real PG, actual UI, historical real model và các unknown được phân rõ. |
| 9 — handoff | Đủ pins/commands/limits/ownership/resource state cho C delivery. Trạng thái GitHub/merge/event chỉ C cập nhật theo thực tế; Done không nghĩa deployed. |
| 10 — F01 | Không áp dụng. |

## Counter và giới hạn thực tế

Q chấp nhận B03-format1 là một coherent formatting repair **1/3**, không phải B05/B12/D02 repair hoặc việc reset cap: một lỗi I001 được sửa, không có failed postfix verification; restore/reapply do C sửa chỉ dẫn của chính C đã có preimage/target reservation. **Ba source writes** add→restore→reapply phải được giữ nguyên. Preartifact operation đã dùng 4 lần thử (lần path sai không chạy Ruff); required check trên changed artifact thêm 1, tổng **5 lần thử/gọi được ghi**, không có lần 6. Postfix là artifact mới cần required verification; không dùng nó để retry nguyên trạng operation cũ đã hết. Reapply trả đúng artifact đã PASS nên không cần thêm command chỉ để tăng độ yên tâm. Không suy Hieu retroapproval; các mốc phút ước lượng cũ đã được giữ và sửa thành bounded/unknown.

All inherited caps giữ nguyên: B12 product4/4; B05 product3/3+harness3/3; B04 product1/3+harness5/5; D02 8/8+10/10+9/9; proxy4/4; publication4+S17DNSread1. Q không cấp repair/call allowance. Không service terms/facts/fixture mới nên exemption market-research áp dụng; synthetic không biến thành market validity.

Giới hạn quan trọng: S19 provider là double; S5/S6 real-model observations thuộc candidate lịch sử, actual served model unreported. S17 browser/AX evidence được reviewer S17 đối chiếu nhưng không có screenshot file mới để Q19 tái xem. Không có fresh S19 UI/model/build. Những giới hạn này được công bố, không phải AC fail hay ngoại lệ PO được tự suy. Không kiểm GitHub CI và không thêm wait/manual rerun gate.

Q không mở tài nguyên runtime. Readback thấy cả root/data `postmaster.pid` và Unix socket S19 đều vắng, data được giữ. Q lease/read needs **RELEASED** sau final integrity; coordinator tiếp tục delivery và các event ở lịch cố định. Không cần product repair hoặc test rerun thêm từ review này.
