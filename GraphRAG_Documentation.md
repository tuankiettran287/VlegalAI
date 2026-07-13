# Tài liệu Kỹ thuật: Kiến trúc GraphRAG Đa Tầng (Multi-Layered GraphRAG)

Tài liệu này chi tiết hóa cấu trúc thiết kế, các tầng tri thức, thực thể, mối quan hệ và cơ chế vận hành của hệ thống **LaborCare GraphRAG Đa Tầng** được triển khai tại dự án VlegalAI.

---

## 1. Tổng quan Kiến trúc

Hệ thống GraphRAG cũ chỉ tập trung vào cấu trúc hình học của văn bản luật (Chương, Điều, Khoản). Kiến trúc mới tổ chức đồ thị tri thức pháp luật lao động theo **8 lớp ngữ nghĩa xếp chồng từ đơn giản (Cú pháp/Cấu trúc văn bản) đến phức tạp (Ánh xạ tình huống thực tế và án lệ xét xử)**.

Sự chuyển đổi này giúp hệ thống GraphRAG không chỉ tìm kiếm từ khóa/vector thông thường, mà còn có khả năng **suy luận bắc cầu qua nhiều tầng ngữ cảnh**, từ đó trả về câu trả lời chính xác, đầy đủ căn cứ pháp lý và thực tế nhất.

```
                  ┌──────────────────────────────────────────────┐
                  │ Tầng 8: Án lệ & Thực tế xét xử               │
                  ├──────────────────────────────────────────────┤
                  │ Tầng 7: Tuân thủ & Quản trị Rủi ro           │
                  ├──────────────────────────────────────────────┤
                  │ Tầng 6: Vòng đời NLĐ & Doanh nghiệp          │
                  ├──────────────────────────────────────────────┤
                  │ Tầng 5: Quy trình & Thủ tục Hành chính       │
                  ├──────────────────────────────────────────────┤
                  │ Tầng 4: Logic Thời gian & Thời hiệu          │
                  ├──────────────────────────────────────────────┤
                  │ Tầng 3: Tình huống & Thực thể Quan hệ        │
                  ├──────────────────────────────────────────────┤
                  │ Tầng 2: Thuật ngữ & Định nghĩa Pháp lý       │
                  ├──────────────────────────────────────────────┤
                  │ Tầng 1: Cấu trúc & Liên kết Văn bản          │
                  └──────────────────────────────────────────────┘
```

---

## 2. Chi tiết 8 Tầng Tri thức (Layers)

Dưới đây là chi tiết kỹ thuật của từng tầng tri thức được thiết kế và trích xuất tự động từ văn bản pháp luật:

### Lớp 1: Cấu trúc & Liên kết Văn bản (Document Hierarchy)
*   **Mục đích**: Bản đồ hóa cấu trúc hình học của văn bản pháp luật gốc, đảm bảo tính tra cứu chính xác đến từng căn cứ pháp lý nhỏ nhất.
*   **Các loại Thực thể (Nodes)**:
    *   `VănBản`: Bộ luật Lao động, Luật BHXH, các Nghị định, Thông tư...
    *   `Chương`: Chương I, Chương II...
    *   `Mục`: Mục 1, Mục 2...
    *   `Điều`: Điều 36, Điều 91...
    *   `Khoản`: Khoản 1, Khoản 2...
    *   `Điểm`: Điểm a, Điểm b...
    *   `CơQuanBanHành`: Quốc hội, Chính phủ, Bộ LĐ-TB&XH...
*   **Các loại Quan hệ (Edges)**:
    *   `THUỘC_VỀ` (`BELONGS_TO`): Liên kết thứ bậc hình học (`[Điểm] -> [Khoản] -> [Điều] -> [Chương] -> [VănBản]`).
    *   `HƯỚNG_DẪN` (`GUIDES`): Liên kết Nghị định/Thông tư hướng dẫn cho Bộ luật/Luật.
    *   `DẪN_CHIẾU_ĐẾN` (`CITES`): Liên kết chéo giữa các điều luật khi có tham chiếu ngữ cảnh.
    *   `SỬA_ĐỔI` (`AMENDS`) / `THAY_THẾ` (`REPLACES`): Thể hiện vòng đời hiệu lực của văn bản.
    *   `BAN_HÀNH` (`ISSUED_BY`): Liên kết `CơQuanBanHành -> VănBản`.

### Lớp 2: Thuật ngữ & Định nghĩa Pháp lý (Legal Semantic Spectrum)
*   **Mục đích**: Mô hình hóa các khái niệm định nghĩa gốc trong luật, phương thức tính toán chế độ và các tham số số học cụ thể.
*   **Các loại Thực thể (Nodes)**:
    *   `ThuậtNgữ`: Các thuật ngữ chính được định nghĩa như "người lao động", "người sử dụng lao động", "thử việc", "sa thải", "tiền lương"...
    *   `CáchTính_CôngThức`: Cách tính lương làm thêm giờ, mức hưởng thai sản, cách tính trợ cấp thôi việc...
    *   `ThamSố_ConSố`: Các giá trị định lượng như `150%`, `200%`, `300%`, `30 ngày`, `45 ngày`, `12 tháng`...
*   **Các loại Quan hệ (Edges)**:
    *   `ĐƯỢC_ĐỊNH_NGHĨA_LÀ` (`DEFINED_AS`): Liên kết giữa `ThuậtNgữ` và Điều/Khoản luật định nghĩa.
    *   `ÁP_DỤNG_CHO` (`APPLIES_TO`): Liên kết từ `CáchTính_CôngThức` đến Điều luật quy định.
    *   `CÓ_THAM_SỐ` (`HAS_PARAMETER`): Liên kết từ `CáchTính_CôngThức` đến các `ThamSố_ConSố` cấu thành.

### Lớp 3: Tình huống & Thực thể Quan hệ (Domain Ontology)
*   **Mục đích**: Đóng vai trò làm cầu nối (semantic mapping) dịch nghĩa từ ngôn ngữ giao tiếp đời sống của người lao động sang ngôn ngữ quy chế của luật pháp.
*   **Các loại Thực thể (Nodes)**:
    *   `ChủThể`: Người lao động (NLĐ), Người sử dụng lao động (NSDLĐ), Công đoàn, Thanh tra lao động...
    *   `HợpĐồngLaoĐộng`: HĐ thử việc, HĐ xác định thời hạn, HĐ không xác định thời hạn.
    *   `HànhVi_SựKiện`: Đi muộn, sa thải, tự ý nghỉ việc, thai sản, tai nạn lao động, khấu trừ lương...
    *   `ChếĐộ_QuyềnLợi`: Lương tăng ca, trợ cấp thôi việc, bồi thường tai nạn, trợ cấp thai sản...
*   **Các loại Quan hệ (Edges)**:
    *   `KÝ_KẾT` (`SIGNS`): `[ChủThể] -> [HợpĐồngLaoĐộng]`.
    *   `THỰC_HIỆN` (`PERFORMS`): `[ChủThể] -> [HànhVi_SựKiện]`.
    *   `CÓ_QUYỀN_HƯỞNG` (`ENTITLED_TO`): `[ChủThể] -> [ChếĐộ_QuyềnLợi]`.
    *   `BỊ_NẰM_TRONG_DANH_MỤC_CẤM` (`PROHIBITED_BY`): Liên kết từ `HànhVi_SựKiện` bị cấm hoặc hạn chế tới Điều luật chế tài.

### Lớp 4: Logic Thời gian & Thời hiệu (Temporal & State Transition)
*   **Mục đích**: Xử lý logic tính toán thời gian, hạn chót (deadlines), thời hiệu pháp lý và các trạng thái chuyển đổi.
*   **Các loại Thực thể (Nodes)**:
    *   `SựKiệnKíchHoạt`: Ngày nhận quyết định thôi việc, ngày sinh con, ngày xảy ra tai nạn...
    *   `MốcThờiGian_LuậtĐịnh`: Các khoảng thời gian khống chế (ví dụ: `1 năm`, `30 ngày`, `15 ngày`).
    *   `TrạngTháiPhápLý`: "Còn thời hiệu khởi kiện", "Quá hạn nộp hồ sơ", "Hợp đồng vô hiệu"...
*   **Các loại Quan hệ (Edges)**:
    *   `BẮT_ĐẦU_TÍNH_THỜI_HIỆU` (`STARTS_LIMITATION`): Liên kết `[SựKiệnKíchHoạt] -> [MốcThờiGian_LuậtĐịnh]`.
    *   `CHUYỂN_TRẠNG_THÁI` (`TRANSITIONS_STATE`): `[MốcThờiGian_LuậtĐịnh] -> [TrạngTháiPhápLý]`.

### Lớp 5: Quy trình & Thủ tục Hành chính (Process-Oriented)
*   **Mục đích**: Mô hình hóa quy trình giải quyết chế độ thực tế cho doanh nghiệp và cá nhân.
*   **Các loại Thực thể (Nodes)**:
    *   `ThủTục_ChếĐộ`: Thủ tục rút BHXH 1 lần, hưởng trợ cấp thất nghiệp, đăng ký nội quy lao động...
    *   `HồSơ_GiấyTờ`: Sổ BHXH, quyết định thôi việc, đơn đề nghị, nội quy lao động...
    *   `ĐiềuKiện`: Đóng đủ 12 tháng, nghỉ việc đủ 1 năm, có từ 10 lao động trở lên...
    *   `CơQuanGiảiQuyết`: Cơ quan BHXH Quận/Huyện, Trung tâm dịch vụ việc làm, Sở LĐ-TB&XH...
    *   `ThờiHạn_ThờiGian`: 05 ngày làm việc, trong vòng 3 tháng...
*   **Các loại Quan hệ (Edges)**:
    *   `YÊU_CẦU_ĐIỀU_KIỆN` (`REQUIRES_CONDITION`): `[ThủTục_ChếĐộ] -> [ĐiềuKiện]`.
    *   `BAO_GỒM_HỒ_SƠ` (`INCLUDES_DOSSIER`): `[ThủTục_ChếĐộ] -> [HồSơ_GiấyTờ]`.
    *   `NỘP_TẠI` (`SUBMITTED_AT`): `[ThủTục_ChếĐộ] -> [CơQuanGiảiQuyết]`.
    *   `CÓ_THỜI_HẠN_LÀ` (`HAS_DURATION`): `[ThủTục_ChếĐộ] -> [ThờiHạn_ThờiGian]`.

### Lớp 6: Vòng đời Người lao động & Doanh nghiệp (Lifecycle-Based)
*   **Mục đích**: Biểu diễn chuỗi hành trình tuần tự, giúp AI suy luận ngữ cảnh động và gợi ý chủ động các bước tiếp theo.
*   **Các loại Thực thể (Nodes)**:
    *   `GiaiĐoạn_NLĐ`: Tuyển dụng $\rightarrow$ Thử việc $\rightarrow$ Ký HĐLĐ $\rightarrow$ Thai sản/Ốm đau $\rightarrow$ Chấm dứt HĐ $\rightarrow$ Nghỉ hưu.
    *   `GiaiĐoạn_DoanhNghiệp`: Thành lập $\rightarrow$ Tuyển dụng $\rightarrow$ Khai báo lao động $\rightarrow$ Xây dựng thang lương $\rightarrow$ Ban hành nội quy $\rightarrow$ Đóng BHXH $\rightarrow$ Giải thể.
    *   `NghĩaVụ_ThờiĐiểm`: Đóng BHXH bắt buộc, báo cáo sử dụng lao động định kỳ...
*   **Các loại Quan hệ (Edges)**:
    *   `GIAI_DOẠN_TIẾP_THEO` (`NEXT_STAGE`): `[Giai đoạn trước] -> [Giai đoạn sau]`.
    *   `KÍCH_HOẠT_NGHĨA_VỤ` (`TRIGGERS_OBLIGATION`): `[Giai đoạn] -> [NghĩaVụ_ThờiĐiểm]`.

### Lớp 7: Tuân thủ & Quản trị Rủi ro (Compliance & Risk Matrix)
*   **Mục đích**: Chuyển hóa luật thành hệ thống đo lường rủi ro pháp lý vận hành cho phòng HR doanh nghiệp.
*   **Các loại Thực thể (Nodes)**:
    *   `HànhViDoanhNghiệp`: Ký thử việc 3 lần, không đóng BHXH, phạt tiền thay kỷ luật sa thải...
    *   `MứcĐộRủiRo`: Thấp (Nhắc nhở), Vừa (Phạt hành chính), Nghiêm trọng (Bồi thường lớn / Đình chỉ / Hình sự).
    *   `BiệnPhápKhắcPhục`: Truy đóng BHXH, ban hành quy chế đối thoại, nhận lại người lao động và bồi thường...
*   **Các loại Quan hệ (Edges)**:
    *   `GÂY_RA_RỦI_RO` (`CAUSES_RISK`): `[HànhViDoanhNghiệp] -> [MứcĐộRủiRo]`.
    *   `KHẮC_PHỤC_BẰNG` (`MITIGATED_BY`): `[HànhViDoanhNghiệp] -> [BiệnPhápKhắcPhục]`.

### Lớp 8: Án lệ & Thực tế xét xử (Precedent & Case-Based Reasoning)
*   **Mục đích**: So sánh tình huống thực tế của người dùng với các phán quyết lịch sử của Tòa án nhân dân Tối cao để đánh giá tỉ lệ thắng kiện.
*   **Các loại Thực thể (Nodes)**:
    *   `ÁnLệ`: Án lệ số 09/2016/AL, Án lệ số 50/2021/AL...
    *   `BảnÁnMẫu`: Các bản án thực tế về sa thải, nợ lương...
    *   `TìnhTiếtCốtLõi`: Sa thải không họp công đoàn, tự ý nghỉ việc 5 ngày cộng dồn...
    *   `PhánQuyết`: Buộc nhận lại NLĐ, bồi thường X tháng lương, bác yêu cầu khởi kiện...
*   **Các loại Quan hệ (Edges)**:
    *   `ÁP_DỤNG_ĐIỀU_LUẬT` (`APPLIES_ARTICLE`): `[ÁnLệ] -> [Điều/Khoản luật]`.
    *   `CÓ_TÌNH_TIẾT_TƯƠNG_TỰ` (`SIMILAR_FACTS`): `[ÁnLệ] -> [TìnhTiếtCốtLõi]`.
    *   `DẪN_ĐẾN_PHÁN_QUYẾT` (`LEADS_TO_RULING`): `[TìnhTiếtCốtLõi] -> [PhánQuyết]`.

---

## 3. Quy tắc Trích xuất Tự động (Extraction Rules)

Tiến trình xây dựng đồ thị (`LegalGraphBuilder._extract_multi_layer_graph`) quét qua toàn bộ các node nội dung (`Điều`, `Khoản`, `Điểm`) và áp dụng các bộ luật trích xuất:

1.  **Nhận diện Thuật ngữ**: Quét từ khóa khớp với bộ từ điển thuật ngữ lao động (ví dụ: `người lao động`, `sa thải`). Nếu xuất hiện các mẫu câu định nghĩa (`"... là ..."`, `"... được hiểu là ..."`), hệ thống sẽ gán quan hệ `ĐƯỢC_ĐỊNH_NGHĨA_LÀ` từ thuật ngữ đến điều khoản đó.
2.  **Nhận diện Tham số & Công thức**: Trích xuất các tỷ lệ phần trăm (`%`) hoặc con số mốc thời gian (`30 ngày`, `12 tháng`) và liên kết chúng làm tham số (`CÓ_THAM_SỐ`) của các công thức tính chế độ tương ứng.
3.  **Nhận diện Quy trình**: Tìm kiếm các cụm từ chỉ hồ sơ (`sổ bhxh`, `quyết định thôi việc`), cơ quan thụ lý (`cơ quan bảo hiểm xã hội`, `tòa án`) để sinh cấu trúc thực thể lớp 5.
4.  **Bản đồ hóa Rủi ro**: Phân tích các câu cấm đoán (`nghiêm cấm`, `không được phép`) hoặc mức phạt để lập hồ sơ rủi ro lớp 7 và đề xuất biện pháp khắc phục.
5.  **Ánh xạ Án lệ**: Nhận diện mẫu ký tự án lệ (`r"Án lệ số \d+/20\d\d/AL"`) và liên kết chúng đến điều luật cơ sở tương ứng.

---

## 4. Cơ chế Suy luận & Tìm kiếm Đồ thị (Retrieval & Graph Propagation)

Khi người dùng gửi câu hỏi (ví dụ: *"Hết hạn thử việc công ty không ký hợp đồng chính thức và bắt thử việc tiếp có bị phạt không?"*):

```
                                FTS & Vector Search
                                         │
                                         ▼ (Khớp các chunk nền tảng)
                           ┌───────────────────────────┐
                           │   Lớp 3: HĐ thử việc      │
                           └─────────────┬─────────────┘
                                         │
                                         ▼ (Duyệt theo cạnh rủi ro)
                           ┌───────────────────────────┐
                           │ Lớp 7: Thử việc quá 2 lần │
                           └─────────────┬─────────────┘
                                         │
                                         ▼ (Duyệt theo quan hệ khắc phục)
                           ┌───────────────────────────┐
                           │ Lớp 7: Phạt hành chính    │
                           └───────────────────────────┘
```

1.  **Truy xuất cơ sở**: Thực hiện tìm kiếm hỗn hợp (Hybrid Search = BM25 FTS + Qdrant Dense Vector) trên các mảnh văn bản (Chunks).
2.  **Mở rộng Đồ thị (Graph Expansion)**: Từ các đỉnh kết quả ban đầu, hệ thống duyệt đồ thị để thu thập các nút lân cận theo các quan hệ đa tầng.
3.  **Phép nhân Trọng số (Score Propagation)**: Điểm số của nút mở rộng được tính bằng công thức:
    $$\text{Score}_{\text{expanded}} = \text{Score}_{\text{base}} \times \text{Weight}_{\text{relation}}$$
    Bảng trọng số quan hệ (`relation_weight`):
    *   `CÓ_TÌNH_TIẾT_TƯƠNG_TỰ` (`SIMILAR_FACTS`): **0.88** (Độ ưu tiên cao nhất cho án lệ tương đương).
    *   `ĐƯỢC_ĐỊNH_NGHĨA_LÀ` (`DEFINED_AS`): **0.85** (Độ ưu tiên cao cho định nghĩa từ ngữ).
    *   `GÂY_RA_RỦI_RO` (`CAUSES_RISK`): **0.85** (Độ ưu tiên cao cho quản trị rủi ro doanh nghiệp).
    *   `YÊU_CẦU_ĐIỀU_KIỆN` (`REQUIRES_CONDITION`): **0.82**.
    *   `CÓ_QUYỀN_HƯỞNG` (`ENTITLED_TO`): **0.80**.
    *   `DẪN_CHIẾU_ĐẾN` (`CITES`): **0.72**.
4.  **Tổng hợp ngữ cảnh**: Rerank các chunk đại diện tốt nhất cho các nút được chọn và xây dựng Context gửi sang LLM (Groq Llama-3.3-70b) để viết câu trả lời cuối cùng kèm trích dẫn nguồn `[S1]`, `[S2]`.

---

## 5. Cơ chế Dự phòng Cục bộ (Graceful Fallback)

Hệ thống được thiết kế để đảm bảo hoạt động **100% thời gian**, ngay cả khi xảy ra sự cố hạ tầng:

*   Khi khởi chạy hoặc gọi các API `/api/stats`, `/api/chat`, `/api/search`: Hệ thống sẽ lần lượt kiểm tra kết nối tới **Hybrid (Neo4j + Qdrant)** $\rightarrow$ **Qdrant Solo** $\rightarrow$ **Neo4j Solo**.
*   Nếu tất cả các cơ sở dữ liệu ngoài bị ngắt kết nối (do lỗi mạng, tường lửa, DNS), hệ thống sẽ **tự động chuyển hướng xử lý sang Local SQLite (`GraphRAGStore`)**.
*   Trên giao diện web, hệ thống sẽ hiển thị một cảnh báo nhỏ để người dùng biết họ đang sử dụng phiên bản dự phòng ngoại tuyến (Local SQLite) và cung cấp toàn bộ thông số thống kê tương ứng của đồ thị đa tầng cục bộ.
