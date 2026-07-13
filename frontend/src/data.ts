import type { Article, RetrievalMode, Template } from "./types";

export const retrievalModes: Array<{ value: RetrievalMode; label: string }> = [
  { value: "rag", label: "RAG" },
  { value: "graphrag", label: "GraphRAG" },
  { value: "hybrid_rag", label: "Hybrid RAG" },
  { value: "local_graphrag", label: "Local" },
];

export const templates: Template[] = [
  { id: "employment", name: "Hợp đồng lao động", category: "Lao động" },
  { id: "probation", name: "Hợp đồng thử việc", category: "Lao động" },
  { id: "nda_salary", name: "Cam kết bảo mật tiền lương", category: "Lao động" },
  { id: "termination", name: "Quyết định thôi việc", category: "Lao động" },
  { id: "service", name: "Hợp đồng dịch vụ", category: "Dịch vụ" },
  { id: "agency", name: "Hợp đồng đại lý phân phối", category: "Thương mại" },
  { id: "lease_office", name: "Hợp đồng thuê văn phòng", category: "Bất động sản" },
  { id: "sale_goods", name: "Hợp đồng mua bán hàng hóa", category: "Thương mại" },
  { id: "loan", name: "Hợp đồng vay tiền", category: "Dân sự" },
  { id: "power_attorney", name: "Hợp đồng ủy quyền", category: "Dân sự" },
];

export const articles: Article[] = [
  {
    id: "mau-hop-dong-lao-dong-2026",
    title: "Mẫu hợp đồng lao động năm 2026 và các điều khoản cần kiểm tra",
    excerpt:
      "Các điểm cần rà soát về loại hợp đồng, tiền lương, thử việc, thời giờ làm việc, BHXH và chấm dứt hợp đồng.",
    category: "Lao động",
    date: "25/06/2026",
    views: 128,
  },
  {
    id: "bien-ban-thanh-ly-hop-dong",
    title: "Biên bản thanh lý hợp đồng: nội dung bắt buộc và lỗi thường gặp",
    excerpt:
      "Gợi ý cấu trúc biên bản thanh lý, phạm vi nghiệm thu, nghĩa vụ còn lại và chứng cứ thanh toán.",
    category: "Hợp đồng mẫu",
    date: "24/06/2026",
    views: 119,
  },
  {
    id: "phu-luc-hop-dong-lao-dong",
    title: "Phụ lục hợp đồng lao động: khi nào được sửa điều khoản chính",
    excerpt:
      "Cách dùng phụ lục để điều chỉnh công việc, lương, thời hạn hoặc điều kiện làm việc mà vẫn hạn chế rủi ro.",
    category: "Lao động",
    date: "22/06/2026",
    views: 147,
  },
  {
    id: "chon-cong-ty-hay-ho-kinh-doanh",
    title: "Thành lập công ty hay hộ kinh doanh: chọn thế nào cho phù hợp",
    excerpt:
      "So sánh trách nhiệm pháp lý, thuế, khả năng mở rộng và thủ tục vận hành của từng mô hình.",
    category: "Doanh nghiệp",
    date: "20/06/2026",
    views: 162,
  },
  {
    id: "hop-dong-dich-vu-quang-cao",
    title: "Hợp đồng dịch vụ quảng cáo: điều khoản nghiệm thu và bản quyền",
    excerpt:
      "Những điểm nên ghi rõ về sản phẩm bàn giao, quyền sử dụng hình ảnh, thanh toán và xử lý thay đổi brief.",
    category: "Hợp đồng mẫu",
    date: "19/06/2026",
    views: 123,
  },
];

export const sampleQuestions = [
  "Cách tính lương làm thêm giờ theo luật hiện hành?",
  "Người lao động nghỉ việc cần báo trước bao nhiêu ngày?",
  "Điều kiện hưởng trợ cấp thôi việc là gì?",
  "Doanh nghiệp đơn phương chấm dứt hợp đồng khi nào hợp pháp?",
];
