# Báo cáo đánh giá GraphRAG — LaborCare GraphRAG question bank v3.0

- Chế độ chạy: **full**
- Kho truy hồi: `local` · top-k = 16
- Mô hình sinh câu trả lời: `gemini-2.5-flash`
- Tổng thời gian: 848.08s · 70 câu hỏi

## 1. Kết quả tổng hợp theo tầng suy luận

| Tầng | Số câu | Hit@k | Citation recall | Fact (nguồn) | Fact (câu trả lời) | Citation hợp lệ | Judge (0-5) | p50 (ms) | p95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Single-hop | 25 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 4.08 | 3818 | 41522 |
| Multi-hop | 30 | 0.700 | 0.822 | 0.967 | 0.875 | 1.000 | 3.79 | 5811 | 77008 |
| Multi-abstract | 15 | 0.667 | 0.628 | 0.967 | 0.900 | 1.000 | 2.50 | 13670 | 18283 |
| **Tổng** | 70 | 0.800 | 0.844 | 0.978 | 0.915 | 1.000 | 3.74 | 5811 | 53450 |

## 2. Kết quả theo mức độ

| Mức | Số câu | Hit@k | Citation recall | MRR |
| --- | ---: | ---: | ---: | ---: |
| 1 | 13 | 1.000 | 1.000 | 0.896 |
| 2 | 12 | 1.000 | 1.000 | 0.917 |
| 3 | 8 | 0.750 | 0.875 | 0.875 |
| 4 | 12 | 0.833 | 0.917 | 0.786 |
| 5 | 10 | 0.500 | 0.667 | 0.778 |
| 6 | 5 | 0.600 | 0.767 | 0.641 |
| 7 | 4 | 0.500 | 0.396 | 0.417 |
| 8 | 6 | 0.833 | 0.667 | 0.382 |

## 3. Kết quả theo chủ đề

| Chủ đề | Số câu | Hit@k | Citation recall |
| --- | ---: | ---: | ---: |
| an-toan-ve-sinh-lao-dong | 3 | 1.000 | 0.889 |
| bao-hiem-xa-hoi | 6 | 0.500 | 0.750 |
| cham-dut-hdld | 7 | 0.714 | 0.738 |
| cong-doan-doi-thoai | 1 | 1.000 | 1.000 |
| hop-dong-lao-dong | 6 | 0.667 | 0.750 |
| huu-tri-tuoi-nghi-huu | 2 | 1.000 | 1.000 |
| ky-luat-lao-dong | 4 | 0.750 | 0.792 |
| lao-dong-dac-thu | 2 | 1.000 | 1.000 |
| lao-dong-nuoc-ngoai | 1 | 1.000 | 1.000 |
| thoi-gio-lam-viec | 3 | 1.000 | 1.000 |
| tien-luong-tien-thuong | 24 | 0.875 | 0.882 |
| to-tung-thi-hanh-an | 1 | 1.000 | 0.667 |
| tranh-chap-lao-dong | 1 | 1.000 | 1.000 |
| viec-lam-that-nghiep | 2 | 0.500 | 0.750 |
| xu-phat-hanh-chinh | 7 | 0.714 | 0.821 |

## 4. Chi tiết từng câu hỏi

| ID | Tầng | Hop | Hit | Recall | Fact nguồn | Fact đáp án | Judge | Ret (ms) | Gen (ms) | Câu hỏi |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SH-01 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1154 | 2811 | Tiền lương là gì theo Bộ luật Lao động? |
| SH-02 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 978 | 4283 | Thưởng cho người lao động được quy định như thế nào? |
| SH-03 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 5 | 943 | 1642 | Mức lương tối thiểu được hiểu như thế nào? |
| SH-04 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 4 | 1055 | 2001 | Nguyên tắc trả lương cho người lao động là gì? |
| SH-05 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 5 | 994 | 3126 | Có những hình thức trả lương nào? |
| SH-06 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 5 | 1096 | 2968 | Tiền lương ngừng việc được trả ra sao khi công ty phải dừng sản xuất? |
| SH-07 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 2 | 1027 | 4869 | Hợp đồng lao động là gì? |
| SH-08 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 5 | 958 | 2136 | Có mấy loại hợp đồng lao động? |
| SH-09 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 5 | 1123 | 2694 | Có những hình thức xử lý kỷ luật lao động nào? |
| SH-10 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 4 | 986 | 2679 | Trợ cấp thôi việc áp dụng cho người lao động nào? |
| SH-11 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 4 | 884 | 2846 | Bảo hiểm xã hội là gì? |
| SH-12 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 3 | 1056 | 76713 | Tai nạn lao động được định nghĩa như thế nào? |
| SH-13 | single_hop | 1 | ✅ | 1.00 | - | - | 4 | 1192 | 5664 | Công đoàn có vai trò gì đối với người lao động? |
| SH-14 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1087 | 1333 | Mức lương tối thiểu vùng I hiện nay là bao nhiêu đồng một tháng? |
| SH-15 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 0 | 1265 | 1438 | Mức lương tối thiểu giờ của vùng IV là bao nhiêu? |
| SH-16 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 970 | 2766 | Làm thêm giờ vào ngày nghỉ lễ, tết thì được trả lương ít nhất bằng bao nhiêu phần trăm? |
| SH-17 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 984 | 1724 | Làm thêm giờ vào ngày thường được trả lương bằng bao nhiêu phần trăm? |
| SH-18 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 1004 | 40519 | Làm việc vào ban đêm thì được trả thêm ít nhất bao nhiêu phần trăm tiền lương? |
| SH-19 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1060 | 2122 | Mức khấu trừ tiền lương hằng tháng tối đa là bao nhiêu phần trăm tiền lương thực trả? |
| SH-20 | single_hop | 1 | ✅ | 1.00 | 1.00 | - | 5 | 1052 | 1252 | Người hưởng lương theo tháng thì được trả lương mấy lần trong tháng? |
| SH-21 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1190 | 2467 | Người lao động được nghỉ hằng năm bao nhiêu ngày trong điều kiện bình thường? |
| SH-22 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 2 | 1077 | 3284 | Thời giờ làm việc bình thường tối đa là bao nhiêu giờ trong một ngày và một tuần? |
| SH-23 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 980 | 13536 | Thời gian thử việc tối đa với công việc quản lý doanh nghiệp là bao nhiêu ngày? |
| SH-24 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1067 | 2827 | Không xây dựng thang lương, bảng lương thì bị phạt tiền bao nhiêu? |
| SH-25 | single_hop | 1 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 1125 | 3106 | Tuổi nghỉ hưu của lao động nam và lao động nữ trong điều kiện bình thường là bao nhiêu? |
| MH-01 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 1196 | 3181 | Tiền lương làm thêm giờ được tính theo những mức nào cho ngày thường, ngày nghỉ hằng tuần  |
| MH-02 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 1239 | 4365 | Khi xây dựng thang lương, bảng lương và quy chế thưởng, người sử dụng lao động phải làm nh |
| MH-03 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 1336 | 2850 | Người lao động đơn phương chấm dứt hợp đồng lao động phải báo trước bao nhiêu ngày với từn |
| MH-04 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 8287 | 77117 | Người sử dụng lao động được sa thải người lao động trong những trường hợp nào? |
| MH-05 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1138 | 4498 | Lao động nữ mang thai và nuôi con nhỏ được bảo vệ như thế nào khi bị xử lý kỷ luật hoặc ch |
| MH-06 | multi_hop | 2 | ❌ | 0.50 | 1.00 | - | 3 | 1095 | 6565 | Điều kiện hưởng lương hưu và cách tính mức lương hưu hằng tháng theo Luật Bảo hiểm xã hội  |
| MH-07 | multi_hop | 2 | ❌ | 0.50 | 1.00 | 1.00 | 1 | 1058 | 6441 | Lao động nữ sinh con được nghỉ chế độ thai sản bao lâu và cần đóng bảo hiểm xã hội bao nhi |
| MH-08 | multi_hop | 2 | ✅ | 1.00 | 1.00 | - | 5 | 8402 | 18055 | Trách nhiệm của người sử dụng lao động đối với người lao động bị tai nạn lao động gồm nhữn |
| MH-09 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 0.00 | 4 | 1244 | 16570 | Công ty trả lương chậm cho nhân viên thì vi phạm quy định nào của Bộ luật Lao động và bị x |
| MH-10 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 1331 | 2467 | Doanh nghiệp không công bố công khai quy chế thưởng tại nơi làm việc thì bị phạt như thế n |
| MH-11 | multi_hop | 2 | ❌ | 0.50 | 1.00 | 1.00 | 5 | 1263 | 2092 | Bắt người lao động thử việc quá một lần cho một công việc thì bị xử phạt ra sao? |
| MH-12 | multi_hop | 2 | ✅ | 1.00 | 1.00 | - | 3 | 1242 | 5349 | Doanh nghiệp không đóng bảo hiểm xã hội bắt buộc cho người lao động thì bị phạt bao nhiêu  |
| MH-13 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 1159 | 4652 | Cách tính tiền lương làm thêm giờ được Bộ luật Lao động quy định nguyên tắc và nghị định n |
| MH-14 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 2 | 1022 | 4518 | Tiền lương làm thêm giờ vào ban đêm được tính như thế nào theo nghị định hướng dẫn? |
| MH-15 | multi_hop | 2 | ❌ | 0.50 | 1.00 | 1.00 | 4 | 1193 | 1609 | Mức lương tối thiểu do văn bản nào quy định và Bộ luật Lao động giao cho cơ quan nào quyết |
| MH-16 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 1031 | 2402 | Lộ trình tăng tuổi nghỉ hưu được quy định ở đâu và nghị định nào hướng dẫn chi tiết theo t |
| MH-17 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1251 | 2632 | Nội quy lao động phải đăng ký ở đâu và doanh nghiệp bao nhiêu lao động thì bắt buộc có nội |
| MH-18 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 1 | 1138 | 4327 | Hồ sơ và thời hạn nộp hồ sơ hưởng trợ cấp thất nghiệp được quy định ở luật nào và nghị địn |
| MH-19 | multi_hop | 2 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1137 | 6442 | Người nước ngoài làm việc tại Việt Nam cần giấy phép lao động theo quy định nào, thời hạn  |
| MH-20 | multi_hop | 2 | ✅ | 1.00 | 1.00 | - | 4 | 1228 | 16669 | Tranh chấp lao động cá nhân có bắt buộc qua hoà giải viên lao động trước khi khởi kiện ra  |
| MH-21 | multi_hop | 3 | ✅ | 0.67 | 0.00 | 0.00 | 2 | 1169 | 15756 | Công ty tôi ở Hà Nội trả lương 4.500.000 đồng/tháng cho công việc giản đơn làm đủ giờ. Như |
| MH-22 | multi_hop | 3 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 4954 | 3583 | Tôi làm thêm 4 giờ vào đêm ngày mùng 1 Tết. Tiền lương giờ làm thêm đó được cộng dồn những |
| MH-23 | multi_hop | 3 | ❌ | 0.50 | 1.00 | 0.00 | 5 | 1124 | 3079 | Nhân viên đi trễ nhiều lần, công ty trừ 500.000 đồng tiền lương mỗi lần thay cho kỷ luật.  |
| MH-24 | multi_hop | 3 | ❌ | 0.33 | 1.00 | 1.00 | 2 | 8062 | 6011 | Công ty sa thải tôi khi tôi đang nuôi con 8 tháng tuổi. Tôi có thể đòi những quyền lợi gì  |
| MH-25 | multi_hop | 3 | ✅ | 0.67 | 1.00 | 1.00 | 3 | 7442 | 2060 | Tôi làm việc 6 năm rồi nghỉ việc đúng luật. Công ty phải thanh toán những khoản gì và tron |
| MH-26 | multi_hop | 3 | ❌ | 0.50 | 1.00 | - | 2 | 1034 | 6941 | Công ty nợ bảo hiểm xã hội 8 tháng nên tôi không chốt được sổ khi nghỉ việc. Công ty vi ph |
| MH-27 | multi_hop | 3 | ❌ | 0.50 | 1.00 | 1.00 | 4 | 1121 | 3505 | Tôi đóng bảo hiểm thất nghiệp 30 tháng rồi mất việc. Tôi được hưởng trợ cấp bao nhiêu thán |
| MH-28 | multi_hop | 3 | ❌ | 0.50 | 1.00 | 1.00 | - | 1222 | 3141 | Hết 2 tháng thử việc công ty không ký hợp đồng chính thức mà bắt thử việc tiếp lần hai. Cô |
| MH-29 | multi_hop | 3 | ✅ | 1.00 | 1.00 | 1.00 | 4 | 1379 | 75629 | Công ty chuyển tôi sang làm công việc khác so với hợp đồng và trả lương thấp hơn. Luật quy |
| MH-30 | multi_hop | 3 | ✅ | 1.00 | 1.00 | - | 5 | 1176 | 19556 | Doanh nghiệp huy động người lao động làm thêm quá 300 giờ trong một năm thì vi phạm quy đị |
| MA-01 | multi_abstract | 4 | ✅ | 1.00 | 1.00 | 1.00 | 3 | 4632 | 4507 | Phân biệt trợ cấp thôi việc và trợ cấp mất việc làm: điều kiện áp dụng và mức hưởng khác n |
| MA-02 | multi_abstract | 4 | ❌ | 0.50 | 1.00 | 1.00 | 2 | 6712 | 46738 | So sánh quyền đơn phương chấm dứt hợp đồng lao động của người lao động và của người sử dụn |
| MA-03 | multi_abstract | 4 | ✅ | 1.00 | 1.00 | - | - | 7859 | 10424 | So sánh chế độ thai sản và chế độ ốm đau: đối tượng, điều kiện hưởng và mức hưởng khác nha |
| MA-04 | multi_abstract | 4 | ❌ | 0.33 | 1.00 | 1.00 | 4 | 1207 | 5178 | Thang lương, bảng lương, định mức lao động và quy chế thưởng liên quan với nhau như thế nà |
| MA-05 | multi_abstract | 4 | ✅ | 1.00 | 1.00 | 1.00 | 5 | 4815 | 5968 | So sánh chế độ tiền lương khi làm thêm giờ ngày thường, ngày nghỉ hằng tuần, ngày lễ tết v |
| MA-06 | multi_abstract | 5 | ✅ | 0.67 | 1.00 | 1.00 | - | 1142 | 4726 | Người lao động ở vùng II làm đủ 26 ngày công, lương thoả thuận 4.800.000 đồng, có thêm 10  |
| MA-07 | multi_abstract | 5 | ❌ | 0.25 | 1.00 | 1.00 | - | 6841 | 6729 | Doanh nghiệp 50 lao động chưa có nội quy lao động, chưa xây thang bảng lương và chưa công  |
| MA-08 | multi_abstract | 5 | ✅ | 0.67 | 1.00 | 1.00 | - | 7430 | 4315 | Liệt kê đầy đủ các khoản tiền người lao động được nhận khi chấm dứt hợp đồng lao động hợp  |
| MA-09 | multi_abstract | 5 | ❌ | 0.00 | 1.00 | - | 1 | 6865 | 7082 | Doanh nghiệp mới thành lập cần hoàn tất những nghĩa vụ pháp lý nào về lao động trước khi c |
| MA-10 | multi_abstract | 6 | ❌ | 0.00 | 0.50 | 1.00 | 1 | 7697 | 7162 | Tổng hợp toàn bộ nghĩa vụ của doanh nghiệp liên quan đến tiền lương và tiền thưởng theo ph |
| MA-11 | multi_abstract | 6 | ✅ | 0.67 | 1.00 | 0.00 | - | 6559 | 8819 | Tổng hợp các hành vi bị nghiêm cấm đối với người sử dụng lao động trong pháp luật lao động |
| MA-12 | multi_abstract | 6 | ✅ | 0.67 | 1.00 | 1.00 | 1 | 5826 | 4884 | Tổng hợp các mốc thời hiệu quan trọng trong quan hệ lao động: xử lý kỷ luật, khiếu nại và  |
| MA-13 | multi_abstract | 6 | ✅ | 0.67 | 1.00 | - | - | 8228 | 9433 | Tổng hợp trách nhiệm của doanh nghiệp về an toàn, vệ sinh lao động từ phòng ngừa, huấn luy |
| MA-14 | multi_abstract | 6 | ✅ | 1.00 | 1.00 | - | 3 | 9033 | 6131 | Tổng hợp các chế độ bảo hiểm xã hội bắt buộc mà người lao động được hưởng và điều kiện chu |
| MA-15 | multi_abstract | 6 | ✅ | 1.00 | 1.00 | - | - | 6278 | 7392 | Tổng hợp các chính sách bảo vệ riêng dành cho lao động nữ và lao động chưa thành niên tron |

## 5. Câu chưa đạt và căn cứ còn thiếu

- **MH-06** (multi_hop): thiếu `41/2024/QH15 Điều 64` — Điều kiện hưởng lương hưu và cách tính mức lương hưu hằng tháng theo Luật Bảo hiểm xã hội 2024?
- **MH-07** (multi_hop): thiếu `41/2024/QH15 Điều 50` — Lao động nữ sinh con được nghỉ chế độ thai sản bao lâu và cần đóng bảo hiểm xã hội bao nhiêu tháng?
- **MH-11** (multi_hop): thiếu `45/2019/QH14 Điều 24` — Bắt người lao động thử việc quá một lần cho một công việc thì bị xử phạt ra sao?
- **MH-15** (multi_hop): thiếu `293/2025/NĐ-CP Điều 3` — Mức lương tối thiểu do văn bản nào quy định và Bộ luật Lao động giao cho cơ quan nào quyết định?
- **MH-23** (multi_hop): thiếu `45/2019/QH14 Điều 127/102` — Nhân viên đi trễ nhiều lần, công ty trừ 500.000 đồng tiền lương mỗi lần thay cho kỷ luật. Việc này có hợp pháp không và công ty phải khắc phục ra sao?
- **MH-24** (multi_hop): thiếu `45/2019/QH14 Điều 41/73, 45/2019/QH14 Điều 190/194` — Công ty sa thải tôi khi tôi đang nuôi con 8 tháng tuổi. Tôi có thể đòi những quyền lợi gì và khởi kiện trong thời hiệu bao lâu?
- **MH-26** (multi_hop): thiếu `45/2019/QH14 Điều 48` — Công ty nợ bảo hiểm xã hội 8 tháng nên tôi không chốt được sổ khi nghỉ việc. Công ty vi phạm gì, bị xử lý ra sao và tôi phải làm gì?
- **MH-27** (multi_hop): thiếu `74/2025/QH15 Điều 40/41/43` — Tôi đóng bảo hiểm thất nghiệp 30 tháng rồi mất việc. Tôi được hưởng trợ cấp bao nhiêu tháng, mức bao nhiêu và nộp hồ sơ ở đâu?
- **MH-28** (multi_hop): thiếu `45/2019/QH14 Điều 24/25/27` — Hết 2 tháng thử việc công ty không ký hợp đồng chính thức mà bắt thử việc tiếp lần hai. Công ty sai ở đâu, bị phạt bao nhiêu và tôi được hưởng gì?
- **MA-02** (multi_abstract): thiếu `45/2019/QH14 Điều 35` — So sánh quyền đơn phương chấm dứt hợp đồng lao động của người lao động và của người sử dụng lao động.
- **MA-04** (multi_abstract): thiếu `45/2019/QH14 Điều 104, 12/2022/NĐ-CP Điều 17` — Thang lương, bảng lương, định mức lao động và quy chế thưởng liên quan với nhau như thế nào trong nghĩa vụ của doanh nghiệp?
- **MA-07** (multi_abstract): thiếu `45/2019/QH14 Điều 118/119, 45/2019/QH14 Điều 93, 45/2019/QH14 Điều 104` — Doanh nghiệp 50 lao động chưa có nội quy lao động, chưa xây thang bảng lương và chưa công bố quy chế thưởng. Hãy lập hồ sơ rủi ro pháp lý tổng thể kèm mức phạt và biện pháp khắc phục.
- **MA-09** (multi_abstract): thiếu `45/2019/QH14 Điều 12/118/119, 45/2019/QH14 Điều 93, 145/2020/NĐ-CP Điều 4/69` — Doanh nghiệp mới thành lập cần hoàn tất những nghĩa vụ pháp lý nào về lao động trước khi chính thức sử dụng lao động?
- **MA-10** (multi_abstract): thiếu `45/2019/QH14 Điều 90/91, 45/2019/QH14 Điều 93/94, 45/2019/QH14 Điều 95/96/97, 45/2019/QH14 Điều 104, 12/2022/NĐ-CP Điều 17` — Tổng hợp toàn bộ nghĩa vụ của doanh nghiệp liên quan đến tiền lương và tiền thưởng theo pháp luật lao động Việt Nam, kèm chế tài khi vi phạm.
