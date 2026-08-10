# Kiến trúc GraphRAG Pháp luật Lao động (LaborCare) — v3

Tài liệu mô tả cấu trúc đồ thị tri thức, quy tắc trích xuất, cơ chế truy hồi và quy trình đánh giá của hệ thống GraphRAG trong dự án VlegalAI.

**Mã nguồn liên quan**

| Thành phần | Tệp |
| --- | --- |
| Từ điển bản thể học (ontology) | [app/legal_ontology.py](../../app/legal_ontology.py) |
| Bộ dựng đồ thị + kho truy hồi cục bộ | [app/legal_graphrag.py](../../app/legal_graphrag.py) |
| Đồng bộ Neo4j + PostgreSQL/pgvector | [app/external_graphrag.py](../../app/external_graphrag.py) |
| Script dựng chỉ mục | [scripts/build_graphrag.py](../../scripts/build_graphrag.py) |
| Bộ dữ liệu benchmark | [questions_100_gemini.jsonl](../../evaluation/benchmarks/ragas-gemini-100/questions_100_gemini.jsonl) |
| Tổng hợp kết quả benchmark | [benchmark_summary.json](../../evaluation/benchmarks/ragas-gemini-100/benchmark_summary.json) |
| Trình chạy đánh giá | [scripts/run_question_bank.py](../../scripts/run_question_bank.py) |

---

## 1. Tổng quan

Kho dữ liệu gồm **57 văn bản quy phạm pháp luật** (Bộ luật Lao động, Luật BHXH, Luật ATVSLĐ, Luật Công đoàn, Luật Việc làm, các nghị định hướng dẫn, nghị định xử phạt, thông tư, luật tố tụng…).

Đồ thị được tổ chức thành **10 tầng ngữ nghĩa**, xếp từ nguồn văn bản gốc lên tới suy luận tình huống:

```
 Tầng 9 · Án lệ & thực tiễn xét xử
 Tầng 8 · Vòng đời NLĐ & doanh nghiệp
 Tầng 7 · Chế tài & rủi ro (khung phạt tiền, biện pháp khắc phục)
 Tầng 6 · Thời gian & thời hiệu
 Tầng 5 · Quy trình & thủ tục hành chính
 Tầng 4 · Chủ thể & quan hệ lao động
 Tầng 3 · TIỀN LƯƠNG & TIỀN THƯỞNG
 Tầng 2 · Thuật ngữ & chủ đề
 Tầng 1 · Cấu trúc văn bản (Chương/Mục/Điều/Khoản/Điểm/Bảng)
 Tầng 0 · Nguồn & hiệu lực (văn bản, cơ quan ban hành, ngày hiệu lực)
```

**Quy mô chỉ mục hiện tại**

| Chỉ số | Giá trị |
| --- | ---: |
| Văn bản | 57 |
| Nút (nodes) | 25.132 |
| Cạnh (edges) | 67.859 |
| Chunk đã nhúng vector | 27.060 |
| Loại nút | 41 |
| Loại quan hệ | 33 |

Vector: **Vertex AI `gemini-embedding-001`**, 1024 chiều và được chuẩn hoá sau khi giảm chiều. Chỉ mục cục bộ lưu ở SQLite (`storage/graphrag/legal_graphrag.sqlite`) kèm FTS5 tiếng Việt; bản production đồng bộ sang Neo4j + PostgreSQL/pgvector.

---

## 2. Tầng 3 — Tiền lương & Tiền thưởng

Đây là tầng nghiệp vụ được xây dựng riêng cho miền lao động, mô hình hoá đầy đủ cấu trúc thu nhập thay vì chỉ coi "tiền lương" là một từ khoá.

### 2.1 Các loại nút

| Nút | Ý nghĩa | Ví dụ thực tế |
| --- | --- | --- |
| `KhoảnThuNhập` | Một khoản cấu thành thu nhập | Tiền lương, phụ cấp lương, các khoản bổ sung khác, tiền lương làm thêm giờ, tiền lương ngừng việc, tạm ứng tiền lương, khấu trừ tiền lương, tiền thưởng, lương hưu, trợ cấp thôi việc… |
| `LoạiThưởng` | Hình thái thưởng | Quy chế thưởng, thưởng bằng tiền, thưởng bằng tài sản, thưởng theo kết quả sản xuất kinh doanh |
| `HìnhThứcTrảLương` | Cách trả lương | Theo thời gian, theo sản phẩm, khoán, tiền mặt, qua tài khoản ngân hàng |
| `KỳHạnTrảLương` | Chu kỳ trả lương | Theo giờ/ngày/tuần, theo tháng, theo sản phẩm-khoán, chậm trả lương |
| `MứcLươngTốiThiểu` | Mức lương tối thiểu theo vùng, **kèm số tiền** | Vùng I: 5.310.000 đ/tháng và 25.500 đ/giờ (NĐ 293/2025) |
| `CănCứTínhLương` | Cơ sở để tính một khoản tiền | Đơn giá tiền lương, tiền lương thực trả, tiền lương bình quân, thang lương-bảng lương, định mức lao động |
| `TỷLệHưởng` | Tỷ lệ luật định | 150%, 200%, 300%, 30%, 20% |
| `CáchTính_CôngThức` | Phương pháp tính chế độ | Cách tính lương làm thêm, trợ cấp thôi việc, lương hưu |
| `SốTiền` | Số tiền tuyệt đối bằng VNĐ | 5.310.000 đồng |

### 2.2 Các quan hệ đặc thù

| Quan hệ | Hướng | Ý nghĩa |
| --- | --- | --- |
| `CẤU_THÀNH_LƯƠNG` | KhoảnThuNhập → KhoảnThuNhập | Phụ cấp lương, mức lương theo công việc, khoản bổ sung khác **cấu thành** tiền lương |
| `CÓ_MỨC_HƯỞNG` | KhoảnThuNhập → TỷLệHưởng | Lương làm thêm ngày lễ → 300% |
| `TRẢ_THEO_HÌNH_THỨC` | KhoảnThuNhập → HìnhThứcTrảLương | Tiền lương → trả qua tài khoản ngân hàng |
| `CÓ_KỲ_HẠN_TRẢ` | KhoảnThuNhập → KỳHạnTrảLương | Tiền lương → trả một tháng một lần |
| `ÁP_DỤNG_VÙNG` | MứcLươngTốiThiểu → mức vùng | Lương tối thiểu → vùng I/II/III/IV |
| `CĂN_CỨ_TÍNH` | KhoảnThuNhập → CănCứTínhLương | Lương làm thêm → đơn giá tiền lương |
| `BỊ_KHẤU_TRỪ_TỪ` | Khấu trừ → tiền lương | Khấu trừ tối đa 30% lương thực trả |
| `CÓ_SỐ_TIỀN` | Thực thể → SốTiền | Lương tối thiểu vùng I → 5.310.000 đồng |
| `QUY_ĐỊNH_TẠI` | Thực thể ngữ nghĩa → Điều/Khoản | Neo mọi khái niệm về điều luật quy định nó |

### 2.3 Ví dụ đường đi trong đồ thị

```
"quy chế thưởng"  (LoạiThưởng)
      │ QUY_ĐỊNH_TẠI
      ├──────────────► Điều 104 Bộ luật Lao động 45/2019/QH14   (nghĩa vụ gốc)
      ├──────────────► Điều 41 Nghị định 145/2020/NĐ-CP         (hướng dẫn)
      └──────────────► Điều 17 Nghị định 12/2022/NĐ-CP          (chế tài)
                              │ BỊ_XỬ_PHẠT
                              └──► Phạt tiền từ 5.000.000 đến 10.000.000 đồng
                                          │ GÂY_RA_RỦI_RO
                                          └──► Mức độ rủi ro: Thấp
```

Ba văn bản này **không dẫn chiếu lẫn nhau bằng văn bản**; chỉ có nút khái niệm chung mới nối được chúng. Đây là giá trị cốt lõi của GraphRAG so với RAG thuần vector.

---

## 3. Danh mục đầy đủ các tầng

### Tầng 0 — Nguồn & hiệu lực
* Nút: `VănBản`, `CơQuanBanHành`, `HiệuLựcVănBản`
* Quan hệ: `BAN_HÀNH`, `CÓ_HIỆU_LỰC_TỪ`, `HƯỚNG_DẪN`, `SỬA_ĐỔI`, `THAY_THẾ`

Ngày hiệu lực được trích tự động từ câu *"Luật này có hiệu lực thi hành từ ngày dd tháng mm năm yyyy"* (56 quan hệ `CÓ_HIỆU_LỰC_TỪ`).

### Tầng 1 — Cấu trúc văn bản
* Nút: `Chương`, `Mục`, `Điều`, `Khoản`, `Điểm`, `PhụLục_Bảng`
* Quan hệ: `THUỘC_VỀ`, `DẪN_CHIẾU_ĐẾN`, `CÓ_BẢNG_BIỂU`

`DẪN_CHIẾU_ĐẾN` phân giải được cả tham chiếu **liên văn bản**: cụm *"Điều 129 của Bộ luật này"* trỏ về chính văn bản, còn *"theo quy định của Luật Bảo hiểm xã hội"* được phân giải sang văn bản đích qua chỉ mục bí danh.

### Tầng 2 — Thuật ngữ & chủ đề
* Nút: `ThuậtNgữ` (212 thuật ngữ), `ChủĐề` (22 chủ đề)
* Quan hệ: `ĐƯỢC_ĐỊNH_NGHĨA_LÀ`, `ĐỀ_CẬP_ĐẾN`, `THUỘC_CHỦ_ĐỀ`

Thuật ngữ **không còn được viết tay**: hệ thống quét mọi điều *"Giải thích từ ngữ"* trong toàn bộ 57 văn bản và bóc tách mẫu `N. <Thuật ngữ> là <định nghĩa>`. Nhờ đó số thuật ngữ tăng từ 12 (bản cũ) lên 212 và luôn là định nghĩa chính thức của chính văn bản đó.

22 chủ đề (`Hợp đồng lao động`, `Tiền lương & Tiền thưởng`, `Bảo hiểm xã hội`, `Xử phạt vi phạm hành chính`, `Tố tụng & Thi hành án`, `Cán bộ, công chức, viên chức`, …) phủ toàn bộ corpus, kể cả các mảng ngoài lao động thuần tuý.

### Tầng 4 — Chủ thể & quan hệ lao động
* Nút: `ChủThể`, `HợpĐồngLaoĐộng`, `HànhVi_SựKiện`, `ChếĐộ_QuyềnLợi`, `NghĩaVụ`
* Quan hệ: `KÝ_KẾT`, `THỰC_HIỆN`, `CÓ_QUYỀN_HƯỞNG`, `CÓ_NGHĨA_VỤ`, `BỊ_NGHIÊM_CẤM`

`BỊ_NGHIÊM_CẤM` chỉ phát sinh khi điều khoản thực sự chứa dấu hiệu cấm (*nghiêm cấm, không được, bị cấm, trái pháp luật*).

### Tầng 5 — Quy trình & thủ tục
* Nút: `ThủTục_ChếĐộ`, `HồSơ_GiấyTờ`, `ĐiềuKiện`, `CơQuanGiảiQuyết`, `ThờiHạn_ThủTục`
* Quan hệ: `YÊU_CẦU_ĐIỀU_KIỆN`, `BAO_GỒM_HỒ_SƠ`, `NỘP_TẠI`, `CÓ_THỜI_HẠN_LÀ`

### Tầng 6 — Thời gian & thời hiệu
* Nút: `SựKiệnKíchHoạt`, `MốcThờiGian_LuậtĐịnh`, `TrạngTháiPhápLý`
* Quan hệ: `BẮT_ĐẦU_TÍNH_THỜI_HIỆU`, `CHUYỂN_TRẠNG_THÁI`

Mốc thời gian được chuẩn hoá (`30 ngày`, `06 tháng`, `01 năm`) nên các cách viết khác nhau gộp về cùng một nút.

### Tầng 7 — Chế tài & rủi ro
* Nút: `HànhViViPhạm` (52), `MứcPhạtTiền` (35), `HìnhThứcXửPhạtBổSung`, `BiệnPhápKhắcPhục`, `MứcĐộRủiRo`
* Quan hệ: `BỊ_XỬ_PHẠT`, `GÂY_RA_RỦI_RO`, `KHẮC_PHỤC_BẰNG`, `BỊ_XỬ_PHẠT_BỔ_SUNG`

Hành vi vi phạm được **khai thác tự động từ tiêu đề điều luật** của các nghị định xử phạt (mẫu *"Điều 17. Vi phạm quy định về tiền lương"*), sau đó mọi khung phạt `Phạt tiền từ X đồng đến Y đồng` nằm dưới điều đó được bóc tách thành nút `MứcPhạtTiền` có giá trị số. Khung phạt được xếp vào 4 mức rủi ro theo trần tiền phạt.

### Tầng 8 — Vòng đời
* Nút: `GiaiĐoạn_NLĐ` (8 giai đoạn), `GiaiĐoạn_DoanhNghiệp` (8 giai đoạn)
* Quan hệ: `GIAI_ĐOẠN_TIẾP_THEO`, `KÍCH_HOẠT_NGHĨA_VỤ`

### Tầng 9 — Án lệ
* Nút: `ÁnLệ`, `TìnhTiếtCốtLõi`, `PhánQuyết`
* Quan hệ: `ÁP_DỤNG_ĐIỀU_LUẬT`, `CÓ_TÌNH_TIẾT_TƯƠNG_TỰ`, `DẪN_ĐẾN_PHÁN_QUYẾT`

Kho dữ liệu hiện tại chưa có bản án nên tầng này sẵn sàng nhưng rỗng; chỉ cần thả tệp bản án vào `data/legal-documents` là tầng tự sinh.

---

## 4. Đường ống dựng chỉ mục

```
.docx ──► docx_blocks()  ──► _parse_document()  ──► _finalize_node_text()
             (giữ đúng          (Chương/Mục/Điều/       (chuẩn hoá, giữ
              thứ tự văn bản      Khoản/Điểm/Bảng)       xuống dòng bảng)
              + bảng inline)
                                        │
       ┌────────────────────────────────┴─────────────────────────────┐
       ▼                                                              ▼
_build_document_relations()   _build_effective_dates()   _build_reference_edges()
       │                                                              │
       └──────────────────────────┬───────────────────────────────────┘
                                  ▼
   _layer2_terms_and_topics() → _layer3_wage_and_bonus() → _layer4_domain_ontology()
   → _layer5_procedures() → _layer6_temporal() → _layer7_sanctions_and_risk()
   → _layer8_lifecycles() → _layer9_precedents()
                                  ▼
                _build_chunks() → _embed_chunks() (Vertex AI Gemini Embedding 001)
                                  ▼
                    SQLite + FTS5  |  JSONL export
                                  ▼
              sync_neo4j() / sync_postgres()  (bản production)
```

Lệnh dựng lại toàn bộ chỉ mục:

```bash
python scripts/build_graphrag.py
```

### 4.1 Bốn lỗi mất dữ liệu đã được sửa ở v3

| Lỗi | Hậu quả trước đây | Cách xử lý |
| --- | --- | --- |
| Bảng biểu bị tách khỏi điều luật | `python-docx` đọc riêng đoạn văn và bảng, nên **toàn bộ bảng bị dồn xuống cuối văn bản**. Bảng mức lương tối thiểu vùng của NĐ 293/2025 mất liên kết với Điều 3 → không bao giờ truy hồi được số tiền. | `docx_blocks()` duyệt `iter_inner_content()` theo đúng thứ tự tài liệu; bảng trở thành nút `PhụLục_Bảng` gắn vào khoản chứa nó. |
| Số hiệu điều luật do Word tự đánh số | Luật ATVSLĐ 84/2015 dùng auto-numbering nên `paragraph.text` **không chứa "Điều N"** → cả 93 điều biến mất, văn bản chỉ còn 15 nút. | `_numbering_key()` đọc `numPr` trong XML; khi văn bản gần như không có tiêu đề `Điều N.` tường minh thì dùng danh sách đánh số làm mốc điều. |
| Phân loại sai loại văn bản | `detect_doc_type` chấm điểm trên nội dung, mà nghị định nào cũng trích "Bộ luật Lao động" ở phần căn cứ → phần lớn nghị định/thông tư bị gán nhãn "Bộ luật", làm hỏng quan hệ `HƯỚNG_DẪN`. | Ưu tiên tiền tố tên tệp, rồi tới mã văn bản, cuối cùng mới xét nội dung. |
| Xuống dòng bị làm phẳng | `normalize_space` gộp mọi ký tự trắng nên `Vùng I \| 5.310.000 \| 25.500` bị trộn thành một dòng dài không phân tích được. | Thêm `normalize_block()` giữ nguyên ranh giới dòng cho nội dung bảng. |

### 4.2 Quy tắc trích xuất chính

1. **Định nghĩa** — quét điều *"Giải thích từ ngữ"*, bóc `N. <Thuật ngữ> là <định nghĩa>`, tạo `ThuậtNgữ` + `ĐƯỢC_ĐỊNH_NGHĨA_LÀ` tới đúng khoản.
2. **Khung phạt** — regex `Phạt tiền từ ([\d.]+) đồng đến ([\d.]+) đồng`, chuyển thành số nguyên VNĐ.
3. **Tỷ lệ & tham số** — bóc `%` và mốc thời gian, chỉ gắn `CÓ_MỨC_HƯỞNG` khi khoản đó thực sự nói về khoản thu nhập tương ứng (`WAGE_RATE_HINTS`).
4. **Lương tối thiểu vùng** — đọc dòng bảng `Vùng <số La Mã> | <lương tháng> | <lương giờ>`.
5. **Đề cập thuật ngữ** — chỉ tạo ở cấp Điều, yêu cầu thuật ngữ nằm trong tiêu đề hoặc xuất hiện ≥2 lần, và giới hạn 220 cạnh/thuật ngữ để cụm phổ biến như *"người lao động"* không nối vào nửa đồ thị.

---

## 5. Cơ chế truy hồi

`GraphRAGStore.retrieve()` chạy 6 giai đoạn:

```
1. TRUY HỒI KÉP        BM25/FTS5  +  vector Gemini Embedding 001 (một phép nhân ma trận numpy)
                       → pool = max(60, top_k × 8) ứng viên
        ▼
2. CHẤM ĐIỂM LẠI       độ phủ từ khoá · khớp chính xác "Điều N/Khoản N"
                       · ưu tiên chunk bảng khi câu hỏi hỏi số
                       · NHÂN TRỌNG SỐ THỨ BẬC PHÁP LÝ
        ▼
3. GIEO MẦM TỪ ĐỒ THỊ  · câu hỏi định nghĩa  → nhảy thẳng tới khoản định nghĩa
                       · cụm khái niệm       → các điều QUY_ĐỊNH_TẠI khái niệm đó
        ▼
4. MỞ RỘNG ĐỒ THỊ      tổ tiên · cạnh ngữ nghĩa (33 quan hệ, có trọng số)
                       · điều liền kề · nhảy 2 bước qua nút khái niệm
        ▼
5. BẮC CẦU VĂN BẢN     đi theo HƯỚNG_DẪN/SỬA_ĐỔI/THAY_THẾ rồi truy vấn lại
                       trong văn bản liên quan
        ▼
6. ĐA DẠNG HOÁ         hạn mức theo văn bản/nút; hạ điểm chunk khái niệm
```

### 5.1 Trọng số thứ bậc pháp luật

Đây là tín hiệu quan trọng nhất được thêm ở v3. Nghị định 145/2020 là văn bản dài nhất kho (581 KB) nên **luôn thắng cả BM25 lẫn vector** đơn thuần vì lặp lại nhiều từ vựng — kết quả là câu trả lời trích nghị định hướng dẫn thay vì chính điều luật gốc.

| Loại văn bản | Hệ số |
| --- | ---: |
| Bộ luật | 1,16 |
| Luật | 1,12 |
| Văn bản hợp nhất | 1,04 |
| Nghị quyết | 1,00 |
| Nghị định | 0,94 |
| Thông tư | 0,90 |

Nếu người dùng gọi đích danh số hiệu văn bản (*"theo Nghị định 145/2020"*) thì văn bản đó được nâng lên 1,25 và trọng số thứ bậc bị vô hiệu hoá.

Riêng thay đổi này nâng tỷ lệ đạt của tầng multi-abstract từ **0,267 → 0,533**.

### 5.2 Gieo mầm từ đồ thị

* **Câu hỏi định nghĩa** (*"… là gì"*, *"định nghĩa …"*): tra `ThuậtNgữ` khớp câu hỏi rồi đi theo `ĐƯỢC_ĐỊNH_NGHĨA_LÀ` tới đúng khoản định nghĩa, thay vì hy vọng khoản đó thắng hàng trăm điều chỉ *dùng* thuật ngữ.
* **Câu hỏi có cụm khái niệm** (*"quy chế thưởng"*, *"thang lương, bảng lương"*): tra nút khái niệm rồi lấy các điều `QUY_ĐỊNH_TẠI` — đây chính là cách nối Điều 104 BLLĐ với Điều 17 NĐ 12/2022 và Điều 41 NĐ 145/2020.

### 5.3 Trọng số quan hệ

Điểm của nút mở rộng = điểm nút gốc × trọng số quan hệ. Bảng đầy đủ nằm trong `RELATIONS` của [app/legal_ontology.py](../../app/legal_ontology.py); một số giá trị tiêu biểu:

| Quan hệ | Trọng số |
| --- | ---: |
| `BỊ_NGHIÊM_CẤM` | 0,90 |
| `BỊ_XỬ_PHẠT` | 0,90 |
| `CÓ_MỨC_HƯỞNG` | 0,88 |
| `ĐƯỢC_ĐỊNH_NGHĨA_LÀ` | 0,88 |
| `QUY_ĐỊNH_TẠI` | 0,86 |
| `CẤU_THÀNH_LƯƠNG` | 0,86 |
| `ÁP_DỤNG_VÙNG` | 0,84 |
| `DẪN_CHIẾU_ĐẾN` | 0,74 |
| `THUỘC_VỀ` | 0,45 |
| `ĐỀ_CẬP_ĐẾN` | 0,34 |

Đi ngược chiều một quan hệ chỉ được tính 0,85 lần trọng số xuôi chiều.

### 5.4 Câu hỏi tổng hợp

Khi câu hỏi chứa dấu hiệu tổng hợp (*"tổng hợp"*, *"liệt kê"*, *"so sánh"*, *"toàn bộ"*, *"các khoản"*…), hệ thống chuyển sang chế độ aggregative: cho phép đi qua các hub chủ đề lớn, lấy nhiều đích hơn mỗi hub, và nới hạn mức số chunk trên mỗi văn bản (vì câu trả lời tổng hợp thường nằm rải rác trong cùng một bộ luật).

---

## 6. Đánh giá

### 6.1 Bộ câu hỏi

[questions_100_gemini.jsonl](../../evaluation/benchmarks/ragas-gemini-100/questions_100_gemini.jsonl) gồm **100 câu hỏi** do Gemini sinh, phân theo kiểu tổng hợp:

| Tầng | Số câu | Mô tả |
| --- | ---: | --- |
| **Single-hop specific** | 50 | Câu trả lời nằm trong một ngữ cảnh pháp lý cụ thể. |
| **Multi-hop specific** | 25 | Phải nối nhiều ngữ cảnh để trả lời một vấn đề cụ thể. |
| **Multi-hop abstract** | 25 | Phải tổng hợp hoặc trừu tượng hoá trên nhiều ngữ cảnh. |

Mỗi câu khai báo:
* `user_input` / `reference` — câu hỏi và câu trả lời tham chiếu;
* `reference_context_ids` / `reference_contexts` — ngữ cảnh chuẩn để đối chiếu truy hồi;
* `reference_citations` / `doc_ids` — căn cứ và văn bản nguồn;
* `synthesizer` / `relation` — kiểu tổng hợp và quan hệ được kiểm thử.

### 6.2 Artifact đánh giá

Toàn bộ một lần chạy được giữ cùng nhau trong `evaluation/benchmarks/ragas-gemini-100/`:

* `retrieval_*.jsonl` — ngữ cảnh và điểm truy hồi theo kiến trúc;
* `answers_*.jsonl` — câu trả lời, trích dẫn và độ trễ;
* `ragas_*_checkpoint.jsonl` / `ragas_scores_*.csv` — checkpoint và điểm RAGAS;
* `benchmark_summary.json` / `architecture_comparison.*` — tổng hợp và biểu đồ so sánh.

Tóm tắt máy đọc được mới nhất nằm tại [benchmark_summary.json](../../evaluation/benchmarks/ragas-gemini-100/benchmark_summary.json).

---

## 7. Cơ chế dự phòng

Thứ tự thử kết nối khi phục vụ API: **Neo4j + PostgreSQL (hybrid)** → **PostgreSQL** → **Neo4j** → **SQLite cục bộ**. Khi mọi cơ sở dữ liệu ngoài mất kết nối, hệ thống tự chuyển sang `GraphRAGStore` cục bộ và giao diện hiển thị cảnh báo đang chạy ở chế độ ngoại tuyến.

Ánh xạ tên quan hệ tiếng Việt sang nhãn Neo4j được sinh trực tiếp từ `RELATIONS` trong ontology (xem `RELATION_TYPE_MAP` trong [app/external_graphrag.py](../../app/external_graphrag.py)), nên thêm một quan hệ mới vào ontology là đủ để nó chảy qua toàn bộ hệ thống.

---

## 8. Mở rộng đồ thị

Thêm một khái niệm mới chỉ cần sửa dữ liệu trong [app/legal_ontology.py](../../app/legal_ontology.py):

```python
WAGE_COMPONENTS = (
    ...
    (_c("tien-an-ca", "Tiền ăn ca",
        ["tien an ca", "ho tro tien an"],
        "Khoản hỗ trợ bữa ăn giữa ca do hai bên thoả thuận."), "tien-luong"),
)
```

Thêm một quan hệ mới thì khai báo trong `RELATIONS` (tên tiếng Việt, nhãn tiếng Anh, tầng, trọng số truy hồi, mô tả) rồi phát cạnh trong tầng tương ứng của builder. Không cần sửa lớp truy hồi hay lớp đồng bộ.
