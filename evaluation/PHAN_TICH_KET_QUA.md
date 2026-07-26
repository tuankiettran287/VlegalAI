# Phân tích kết quả đánh giá GraphRAG — v3

Tài liệu này diễn giải số liệu trong [storage/eval/BAO_CAO_DANH_GIA.md](../storage/eval/BAO_CAO_DANH_GIA.md)
(báo cáo sinh tự động) và [storage/eval/full_system_v3.json](../storage/eval/full_system_v3.json).

**Cấu hình lần chạy**

| Thông số | Giá trị |
| --- | --- |
| Bộ câu hỏi | `evaluation/question_bank.json` v3.0 — 70 câu |
| Kho truy hồi | SQLite cục bộ (`GraphRAGStore`), BM25/FTS5 + BGE-M3 |
| `top_k` | 16 |
| Mô hình sinh câu trả lời | `gemini-2.5-flash` qua Vertex AI |
| Prompt | `LEGAL_SYSTEM_PROMPT` — đúng prompt production |
| Song song | 2 |

---

## 1. Kết quả tổng thể

| Chỉ số | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| Hit@16 | **0,800** | Tỷ lệ câu đạt ngưỡng trích dẫn bắt buộc |
| Citation recall | **0,844** | Tỷ lệ căn cứ pháp lý mong đợi được truy hồi |
| Fact coverage (nguồn) | **0,978** | Dữ kiện bắt buộc có trong ngữ cảnh gửi cho LLM |
| Fact coverage (câu trả lời) | **0,915** | Dữ kiện bắt buộc xuất hiện trong câu trả lời cuối |
| Citation validity | **1,000** | **Không có câu nào bịa ID nguồn `[Sx]`** |
| Grounded rate | 0,943 | Tỷ lệ câu trả lời có trích dẫn nguồn |
| LLM-judge trung bình | 3,74 / 5 | Xem mục 4 về giới hạn của giám khảo |
| MRR | 0,772 | Thứ hạng căn cứ đúng đầu tiên |

**Citation validity 1,000 là kết quả quan trọng nhất về mặt an toàn**: trên toàn bộ
67 câu trả lời sinh được, không câu nào trích dẫn một ID nguồn không tồn tại. Ràng buộc
"chỉ trích dẫn ID do hệ thống cấp" trong prompt kết hợp với ngữ cảnh có đánh số nguồn
đang hoạt động đúng.

---

## 2. Kết quả theo tầng suy luận

| Tầng | Số câu | Hit@16 | Citation recall | Fact (đáp án) | Judge |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single-hop | 25 | **1,000** | 1,000 | 1,000 | 4,08 |
| Multi-hop | 30 | 0,700 | 0,822 | 0,875 | 3,79 |
| Multi-abstract | 15 | 0,667 | 0,628 | 0,900 | 2,50 |

Độ chính xác suy giảm đúng theo độ sâu suy luận, đúng như thiết kế của bộ câu hỏi:

* **Single-hop tuyệt đối**. Mọi câu hỏi tra cứu định nghĩa hoặc con số đều lấy đúng điều
  luật, kể cả những câu chỉ trả lời được nhờ dữ liệu bảng biểu (lương tối thiểu vùng I
  = 5.310.000 đồng/tháng, vùng IV = 17.800 đồng/giờ). Trước khi sửa lỗi bảng bị tách khỏi
  điều luật, những câu này **không thể** trả lời được.
* **Multi-hop 0,700**. Các câu còn thiếu đều rơi vào một dạng: cần điều luật *thứ hai*
  của một cặp mà điều đó ít trùng từ khoá với câu hỏi.
* **Multi-abstract 0,667 hit nhưng recall chỉ 0,628**. Đây là tầng khó nhất — nhiều câu
  đòi 4–6 điều luật riêng biệt cùng lúc; hệ thống thường lấy được 2–4 trong số đó.

---

## 3. Độ trễ

| Giai đoạn | p50 | p95 |
| --- | ---: | ---: |
| Truy hồi | 1.169 ms | 8.228 ms |
| Sinh câu trả lời (thô) | 4.365 ms | 46.738 ms |
| **Sinh câu trả lời (loại thời gian chờ quota)** | **4.315 ms** | **15.756 ms** |
| Tổng (p50) | 5.811 ms | — |

**Lưu ý quan trọng về con số p95**: 5/70 lệnh gọi bị Vertex AI trả `HTTP 429` và phải chờ
backoff 12–24 giây. Thời gian chờ này là hạn mức của nhà cung cấp khi chạy 70 câu liên tục,
**không phải độ trễ của hệ thống**. Loại các lệnh gọi bị giới hạn ra, p95 sinh câu trả lời
là 15,8 giây. Trình chạy hiện đã ghi riêng `generation_ms_net` và `rate_limited` cho các
lần chạy sau.

Về truy hồi:
* p50 1,17 giây, trong đó phần lớn là mã hoá câu hỏi bằng BGE-M3.
* Việc chuyển tìm kiếm vector sang một phép nhân ma trận numpy đã giảm p50 từ **2.601 ms
  xuống 1.169 ms** (−55%).
* p95 8,2 giây đến từ 15 câu multi-abstract: chế độ tổng hợp duyệt qua các hub chủ đề lớn.
  Nếu cần, có thể giới hạn số đích mỗi hub để đổi độ phủ lấy độ trễ.

---

## 4. Giới hạn của LLM-judge — đọc điểm 3,74 một cách thận trọng

Giám khảo (`gemini-2.5-flash`) trừ điểm nặng ở một số câu **vì lý do sai**:

> MH-18: *"Câu trả lời đã trích dẫn các văn bản pháp luật không có thật (Luật Việc làm 74/2025/QH15)."*
>
> MH-07: *"Câu trả lời đã sử dụng các căn cứ pháp luật không tồn tại (41/2024/QH15)."*

Cả **Luật Bảo hiểm xã hội 41/2024/QH15** và **Luật Việc làm 74/2025/QH15** đều là văn bản
có thật và nằm trong kho dữ liệu. Giám khảo đánh giá chúng là bịa đặt vì chúng ban hành
**sau mốc kiến thức** của mô hình. Đây là hạn chế của giám khảo, không phải lỗi hệ thống —
và cũng chính là lý do tồn tại của RAG.

Vì vậy `judge_pass_rate = 0,693` là **giới hạn dưới**. Các chỉ số khách quan (citation
recall 0,844, fact coverage 0,915, citation validity 1,000) đáng tin cậy hơn cho các câu
liên quan tới văn bản mới.

Ngoài ra giám khảo còn trừ điểm khi câu trả lời "mở rộng quá nhiều so với câu hỏi"
(SH-07, SH-22) — đây là vấn đề về độ dài/tập trung, không phải sai pháp lý.

---

## 5. Các câu chưa đạt và nguyên nhân

### 5.1 Multi-hop (9/30 chưa đạt)

| ID | Căn cứ còn thiếu | Nguyên nhân |
| --- | --- | --- |
| MH-06, MH-07 | Luật BHXH 2024 Điều 64, Điều 50 | Cần điều "điều kiện hưởng" đứng cạnh điều "mức hưởng"; câu hỏi trùng từ khoá với điều mức hưởng nhiều hơn |
| MH-11, MH-28 | BLLĐ Điều 24/25/27 (thử việc) | Nghị định xử phạt chiếm hết các vị trí đầu vì nhắc "thử việc" dày đặc hơn |
| MH-15 | NĐ 293/2025 Điều 3 | Trả về đúng bảng lương tối thiểu nhưng chunk bảng không mang số hiệu điều |
| MH-23, MH-24, MH-26 | BLLĐ Điều 127/102, 41, 48 | Tình huống 3 hop: điều thứ ba nằm ngoài phạm vi mở rộng |
| MH-27 | Luật Việc làm 74/2025 Điều 40/41/43 | Hai luật việc làm (2013 và 2025) cạnh tranh nhau; hệ thống chọn bản 2013 |

### 5.2 Multi-abstract (5/15 chưa đạt)

MA-02, MA-04, MA-07, MA-09, MA-10 đều thất bại theo cùng một cách: cần 3–5 điều luật khác
nhau của Bộ luật Lao động trong cùng một cửa sổ 16 nguồn. Hệ thống lấy được 2–3 điều.
Đây là giới hạn của cửa sổ ngữ cảnh chứ không phải của đồ thị — các điều đó **đều được nối
với nhau qua nút chủ đề `Tiền lương & Tiền thưởng`**, chỉ là không đủ chỗ để đưa hết vào.

### 5.3 Ba câu lỗi hạ tầng

MA-03, MA-11, MA-13 hết hạn mức Vertex AI sau 6 lần thử lại. Không phải lỗi truy hồi —
phần truy hồi của ba câu này đều đạt.

---

## 6. Tác động của từng thay đổi

Đo trên cùng bộ câu hỏi, `top_k = 12`:

| Cấu hình | Hit@k tổng | Multi-abstract | Truy hồi p50 |
| --- | ---: | ---: | ---: |
| Sau khi sửa 4 lỗi mất dữ liệu (mốc nền) | 0,643 | 0,200 | 2.601 ms |
| \+ trọng số thứ bậc pháp luật | **0,743** | **0,533** | 1.115 ms |
| \+ gieo mầm khái niệm, hạ điểm chunk khái niệm | 0,743 | 0,533 | 1.067 ms |
| \+ nâng `top_k` lên 16 | **0,800** | **0,667** | 1.169 ms |

**Trọng số thứ bậc pháp luật là thay đổi có tác động lớn nhất** — nâng multi-abstract lên
gấp đôi. Nguyên nhân: Nghị định 145/2020 là văn bản dài nhất kho (581 KB) nên luôn thắng cả
BM25 lẫn vector chỉ vì dài và lặp từ vựng, khiến hệ thống trích nghị định hướng dẫn thay vì
chính điều luật gốc.

---

## 7. Đề xuất cải thiện tiếp theo

Theo thứ tự ưu tiên:

1. **Ngân sách ngữ cảnh động theo loại câu hỏi.** Câu multi-abstract nên dùng `top_k` 24–28
   thay vì 16; câu single-hop giữ 8 để giảm độ trễ và chi phí token. Chỉ riêng việc này
   đã nâng multi-abstract từ 0,533 lên 0,667 khi tăng từ 12 lên 16.
2. **Truy hồi hai vòng cho câu tổng hợp.** Vòng một xác định chủ đề, vòng hai truy vấn
   trong phạm vi chủ đề đó với ngân sách riêng cho từng văn bản.
3. **Ưu tiên văn bản mới khi có xung đột.** Luật Việc làm 74/2025 phải thắng bản 2013;
   đồ thị đã có nút `HiệuLựcVănBản` nhưng cơ chế chấm điểm chưa dùng đến.
4. **Thay giám khảo bằng mô hình có kiến thức mới hơn, hoặc cấp cho giám khảo danh sách
   văn bản trong kho** để loại bỏ các trường hợp báo nhầm "văn bản không có thật".
5. **Bổ sung kho bản án** để kích hoạt tầng 9 (án lệ) hiện đang rỗng.

---

## 8. Cách tái lập

```bash
# Dựng lại chỉ mục
python scripts/build_graphrag.py

# Chỉ chấm truy hồi (nhanh, không tốn quota LLM)
python scripts/run_question_bank.py --top-k 16

# Toàn bộ đường ống + giám khảo + báo cáo
GEMINI_USE_ADC=true python scripts/run_question_bank.py \
    --mode full --judge --top-k 16 --concurrency 2 \
    --report storage/eval/full_system_v3.json \
    --markdown storage/eval/BAO_CAO_DANH_GIA.md
```
