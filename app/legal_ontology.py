"""Data-driven ontology for the LaborCare legal GraphRAG.

Everything the graph builder knows about *meaning* lives here: the layer map,
the node/relation catalogue, the retrieval weights and the Vietnamese lexicons
used to lift raw legal text into semantic nodes.

Keeping the ontology in one declarative module means the graph can be extended
by editing data (add a concept, add a trigger phrase) instead of editing the
extraction code in ``app.legal_graphrag``.

Matching contract
-----------------
Every lexicon entry carries ``patterns``: accent-insensitive lowercase
substrings. The builder normalises node text once with
``strip_accents(text).lower()`` and tests membership, so "TIỀN LƯƠNG",
"tiền lương" and "tien luong" all match the pattern ``"tien luong"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------

LAYERS: dict[int, dict[str, str]] = {
    0: {
        "name": "Nguồn & Hiệu lực",
        "purpose": "Văn bản gốc, cơ quan ban hành, ngày hiệu lực, quan hệ sửa đổi/thay thế.",
    },
    1: {
        "name": "Cấu trúc văn bản",
        "purpose": "Chương / Mục / Điều / Khoản / Điểm và dẫn chiếu chéo giữa các điều luật.",
    },
    2: {
        "name": "Thuật ngữ & Chủ đề",
        "purpose": "Định nghĩa pháp lý khai thác tự động và bản đồ chủ đề phủ toàn bộ corpus.",
    },
    3: {
        "name": "Tiền lương & Tiền thưởng",
        "purpose": "Cấu thành thu nhập, hình thức/kỳ hạn trả lương, lương tối thiểu vùng, tỷ lệ hưởng, khấu trừ, thưởng.",
    },
    4: {
        "name": "Chủ thể & Quan hệ lao động",
        "purpose": "Chủ thể, loại hợp đồng, hành vi - sự kiện, quyền lợi và nghĩa vụ.",
    },
    5: {
        "name": "Quy trình & Thủ tục",
        "purpose": "Thủ tục hành chính, hồ sơ, điều kiện, cơ quan giải quyết, thời hạn xử lý.",
    },
    6: {
        "name": "Thời gian & Thời hiệu",
        "purpose": "Sự kiện kích hoạt, mốc thời gian luật định, trạng thái pháp lý theo thời gian.",
    },
    7: {
        "name": "Chế tài & Rủi ro",
        "purpose": "Hành vi vi phạm, khung phạt tiền, xử phạt bổ sung, biện pháp khắc phục, mức độ rủi ro.",
    },
    8: {
        "name": "Vòng đời NLĐ & Doanh nghiệp",
        "purpose": "Chuỗi giai đoạn tuần tự và nghĩa vụ phát sinh tại mỗi giai đoạn.",
    },
    9: {
        "name": "Án lệ & Thực tiễn xét xử",
        "purpose": "Án lệ, tình tiết cốt lõi, phán quyết (mở rộng khi bổ sung kho bản án).",
    },
}


# ---------------------------------------------------------------------------
# Node catalogue: node_type -> (layer, description)
# ---------------------------------------------------------------------------

NODE_TYPES: dict[str, tuple[int, str]] = {
    # Layer 0
    "VănBản": (0, "Một văn bản quy phạm pháp luật trong kho dữ liệu."),
    "CơQuanBanHành": (0, "Chủ thể ban hành văn bản."),
    "HiệuLựcVănBản": (0, "Mốc ngày văn bản có hiệu lực thi hành."),
    # Layer 1
    "Chương": (1, "Chương của văn bản."),
    "Mục": (1, "Mục trong chương."),
    "Điều": (1, "Điều luật - đơn vị trích dẫn chính."),
    "Khoản": (1, "Khoản trong điều."),
    "Điểm": (1, "Điểm trong khoản."),
    "PhụLục_Bảng": (1, "Bảng biểu / phụ lục được gắn lại vào điều khoản chứa nó."),
    # Layer 2
    "ThuậtNgữ": (2, "Thuật ngữ pháp lý được định nghĩa trong văn bản."),
    "ChủĐề": (2, "Chủ đề pháp lý dùng làm hub điều hướng cho toàn bộ corpus."),
    # Layer 3 - tiền lương & tiền thưởng
    "KhoảnThuNhập": (3, "Một khoản cấu thành thu nhập của người lao động."),
    "LoạiThưởng": (3, "Hình thái thưởng và quy chế thưởng."),
    "HìnhThứcTrảLương": (3, "Cách thức trả lương (thời gian, sản phẩm, khoán, tiền mặt, chuyển khoản)."),
    "KỳHạnTrảLương": (3, "Chu kỳ trả lương theo giờ/ngày/tuần/tháng/sản phẩm."),
    "MứcLươngTốiThiểu": (3, "Mức lương tối thiểu tháng/giờ theo từng vùng, kèm số tiền."),
    "CănCứTínhLương": (3, "Cơ sở dùng để tính một khoản tiền lương."),
    "TỷLệHưởng": (3, "Tỷ lệ phần trăm luật định (150%, 200%, 300%, 30%...)."),
    "CáchTính_CôngThức": (3, "Phương pháp tính một chế độ hoặc khoản tiền."),
    "ThamSố_ConSố": (3, "Tham số định lượng cấu thành công thức."),
    "SốTiền": (3, "Số tiền tuyệt đối bằng Đồng Việt Nam."),
    # Layer 4
    "ChủThể": (4, "Chủ thể tham gia quan hệ lao động hoặc quan hệ hành chính."),
    "HợpĐồngLaoĐộng": (4, "Loại hợp đồng lao động."),
    "HànhVi_SựKiện": (4, "Hành vi hoặc sự kiện thực tế trong quan hệ lao động."),
    "ChếĐộ_QuyềnLợi": (4, "Chế độ, quyền lợi mà chủ thể được hưởng."),
    "NghĩaVụ": (4, "Nghĩa vụ pháp lý của một chủ thể."),
    # Layer 5
    "ThủTục_ChếĐộ": (5, "Thủ tục hành chính hoặc quy trình giải quyết chế độ."),
    "HồSơ_GiấyTờ": (5, "Thành phần hồ sơ, giấy tờ."),
    "ĐiềuKiện": (5, "Điều kiện cần đáp ứng."),
    "CơQuanGiảiQuyết": (5, "Cơ quan có thẩm quyền tiếp nhận / giải quyết."),
    "ThờiHạn_ThủTục": (5, "Thời hạn xử lý của thủ tục."),
    # Layer 6
    "SựKiệnKíchHoạt": (6, "Sự kiện bắt đầu tính thời hạn / thời hiệu."),
    "MốcThờiGian_LuậtĐịnh": (6, "Khoảng thời gian luật định đã chuẩn hoá."),
    "TrạngTháiPhápLý": (6, "Trạng thái pháp lý sau khi mốc thời gian trôi qua."),
    # Layer 7
    "HànhViViPhạm": (7, "Hành vi vi phạm bị xử phạt."),
    "MứcPhạtTiền": (7, "Khung phạt tiền từ mức tối thiểu đến mức tối đa."),
    "HìnhThứcXửPhạtBổSung": (7, "Hình thức xử phạt bổ sung (tước giấy phép, đình chỉ, tịch thu)."),
    "BiệnPhápKhắcPhục": (7, "Biện pháp khắc phục hậu quả."),
    "MứcĐộRủiRo": (7, "Thang đo rủi ro pháp lý cho doanh nghiệp."),
    # Layer 8
    "GiaiĐoạn_NLĐ": (8, "Giai đoạn trong vòng đời người lao động."),
    "GiaiĐoạn_DoanhNghiệp": (8, "Giai đoạn trong vòng đời doanh nghiệp."),
    # Layer 9
    "ÁnLệ": (9, "Án lệ hoặc bản án được viện dẫn."),
    "TìnhTiếtCốtLõi": (9, "Tình tiết cốt lõi của vụ việc."),
    "PhánQuyết": (9, "Phán quyết của toà án."),
}


# ---------------------------------------------------------------------------
# Relation catalogue: relation -> (english, layer, retrieval weight, description)
#
# ``weight`` is the score multiplier applied when the retriever walks that edge
# during graph expansion. 1.0 would mean "as relevant as the seed chunk".
# ---------------------------------------------------------------------------

RELATIONS: dict[str, tuple[str, int, float, str]] = {
    # Layer 0 / 1 - structure & lifecycle of documents
    "THUỘC_VỀ": ("BELONGS_TO", 1, 0.45, "Liên kết thứ bậc Điểm → Khoản → Điều → Mục → Chương → VănBản."),
    "BAN_HÀNH": ("ISSUED_BY", 0, 0.20, "CơQuanBanHành → VănBản."),
    "CÓ_HIỆU_LỰC_TỪ": ("EFFECTIVE_FROM", 0, 0.60, "VănBản → HiệuLựcVănBản."),
    "HƯỚNG_DẪN": ("GUIDES", 0, 0.68, "Nghị định/Thông tư hướng dẫn Luật/Bộ luật."),
    "SỬA_ĐỔI": ("AMENDS", 0, 0.66, "Văn bản sửa đổi, bổ sung văn bản khác."),
    "THAY_THẾ": ("REPLACES", 0, 0.66, "Văn bản thay thế văn bản khác."),
    "DẪN_CHIẾU_ĐẾN": ("CITES", 1, 0.74, "Điều/Khoản/Điểm dẫn chiếu tới điều khoản khác (kể cả liên văn bản)."),
    "CÓ_BẢNG_BIỂU": ("HAS_TABLE", 1, 0.80, "Điều/Khoản → bảng biểu, phụ lục đính kèm."),
    # Layer 2
    "ĐƯỢC_ĐỊNH_NGHĨA_LÀ": ("DEFINED_AS", 2, 0.88, "ThuậtNgữ → điều khoản định nghĩa chính thức."),
    "ĐỀ_CẬP_ĐẾN": ("MENTIONS", 2, 0.34, "ThuậtNgữ → điều khoản có sử dụng thuật ngữ."),
    "THUỘC_CHỦ_ĐỀ": ("HAS_TOPIC", 2, 0.42, "Điều/VănBản → ChủĐề."),
    "LIÊN_QUAN_CHỦ_ĐỀ": ("RELATED_TOPIC", 2, 0.30, "ChủĐề ↔ ChủĐề."),
    # Layer 3 - tiền lương & tiền thưởng
    "QUY_ĐỊNH_TẠI": ("REGULATED_AT", 3, 0.86, "Thực thể ngữ nghĩa → điều khoản quy định về nó."),
    "CẤU_THÀNH_LƯƠNG": ("COMPRISES_WAGE", 3, 0.86, "Khoản thu nhập con → khoản thu nhập tổng (phụ cấp → tiền lương)."),
    "CÓ_MỨC_HƯỞNG": ("HAS_RATE", 3, 0.88, "KhoảnThuNhập → TỷLệHưởng (ví dụ làm thêm ngày lễ = 300%)."),
    "TRẢ_THEO_HÌNH_THỨC": ("PAID_IN_FORM", 3, 0.76, "KhoảnThuNhập → HìnhThứcTrảLương."),
    "CÓ_KỲ_HẠN_TRẢ": ("HAS_PAY_PERIOD", 3, 0.78, "KhoảnThuNhập → KỳHạnTrảLương."),
    "ÁP_DỤNG_VÙNG": ("APPLIES_REGION", 3, 0.84, "MứcLươngTốiThiểu → vùng áp dụng và số tiền."),
    "CĂN_CỨ_TÍNH": ("CALCULATED_FROM", 3, 0.84, "KhoảnThuNhập/CáchTính → CănCứTínhLương."),
    "BỊ_KHẤU_TRỪ_TỪ": ("DEDUCTED_FROM", 3, 0.82, "Khoản khấu trừ → khoản thu nhập bị trừ."),
    "ÁP_DỤNG_CHO": ("APPLIES_TO", 3, 0.78, "CáchTính_CôngThức → điều khoản quy định."),
    "CÓ_THAM_SỐ": ("HAS_PARAMETER", 3, 0.72, "CáchTính_CôngThức → ThamSố_ConSố."),
    "CÓ_SỐ_TIỀN": ("HAS_AMOUNT", 3, 0.80, "Thực thể → SốTiền tuyệt đối."),
    # Layer 4
    "KÝ_KẾT": ("SIGNS", 4, 0.66, "ChủThể → HợpĐồngLaoĐộng."),
    "THỰC_HIỆN": ("PERFORMS", 4, 0.70, "ChủThể → HànhVi_SựKiện."),
    "CÓ_QUYỀN_HƯỞNG": ("ENTITLED_TO", 4, 0.84, "ChủThể → ChếĐộ_QuyềnLợi."),
    "CÓ_NGHĨA_VỤ": ("HAS_OBLIGATION", 4, 0.80, "ChủThể → NghĩaVụ."),
    "BỊ_NGHIÊM_CẤM": ("PROHIBITED_BY", 4, 0.90, "HànhVi_SựKiện bị cấm → điều khoản cấm."),
    # Layer 5
    "YÊU_CẦU_ĐIỀU_KIỆN": ("REQUIRES_CONDITION", 5, 0.84, "ThủTục_ChếĐộ → ĐiềuKiện."),
    "BAO_GỒM_HỒ_SƠ": ("INCLUDES_DOSSIER", 5, 0.82, "ThủTục_ChếĐộ → HồSơ_GiấyTờ."),
    "NỘP_TẠI": ("SUBMITTED_AT", 5, 0.72, "ThủTục_ChếĐộ → CơQuanGiảiQuyết."),
    "CÓ_THỜI_HẠN_LÀ": ("HAS_DURATION", 5, 0.78, "ThủTục_ChếĐộ → ThờiHạn_ThủTục."),
    # Layer 6
    "BẮT_ĐẦU_TÍNH_THỜI_HIỆU": ("STARTS_LIMITATION", 6, 0.80, "SựKiệnKíchHoạt → MốcThờiGian_LuậtĐịnh."),
    "CHUYỂN_TRẠNG_THÁI": ("TRANSITIONS_STATE", 6, 0.76, "MốcThờiGian_LuậtĐịnh → TrạngTháiPhápLý."),
    # Layer 7
    "BỊ_XỬ_PHẠT": ("SANCTIONED_BY", 7, 0.90, "HànhViViPhạm → MứcPhạtTiền."),
    "GÂY_RA_RỦI_RO": ("CAUSES_RISK", 7, 0.86, "HànhViViPhạm → MứcĐộRủiRo."),
    "KHẮC_PHỤC_BẰNG": ("MITIGATED_BY", 7, 0.84, "HànhViViPhạm → BiệnPhápKhắcPhục."),
    "BỊ_XỬ_PHẠT_BỔ_SUNG": ("HAS_EXTRA_SANCTION", 7, 0.80, "HànhViViPhạm → HìnhThứcXửPhạtBổSung."),
    # Layer 8
    "GIAI_ĐOẠN_TIẾP_THEO": ("NEXT_STAGE", 8, 0.62, "Giai đoạn trước → giai đoạn sau."),
    "KÍCH_HOẠT_NGHĨA_VỤ": ("TRIGGERS_OBLIGATION", 8, 0.72, "Giai đoạn → điều khoản/nghĩa vụ phát sinh."),
    # Layer 9
    "ÁP_DỤNG_ĐIỀU_LUẬT": ("APPLIES_ARTICLE", 9, 0.86, "ÁnLệ → điều khoản được áp dụng."),
    "CÓ_TÌNH_TIẾT_TƯƠNG_TỰ": ("SIMILAR_FACTS", 9, 0.88, "ÁnLệ → TìnhTiếtCốtLõi."),
    "DẪN_ĐẾN_PHÁN_QUYẾT": ("LEADS_TO_RULING", 9, 0.86, "TìnhTiếtCốtLõi → PhánQuyết."),
}

#: relation -> retrieval weight, consumed by the graph expansion step.
RELATION_WEIGHTS: dict[str, float] = {name: spec[2] for name, spec in RELATIONS.items()}

#: Relations that carry meaning when traversed backwards during expansion.
REVERSIBLE_RELATIONS: frozenset[str] = frozenset(
    {
        "HƯỚNG_DẪN",
        "SỬA_ĐỔI",
        "THAY_THẾ",
        "ĐƯỢC_ĐỊNH_NGHĨA_LÀ",
        "QUY_ĐỊNH_TẠI",
        "BỊ_NGHIÊM_CẤM",
        "THUỘC_CHỦ_ĐỀ",
        "CÓ_BẢNG_BIỂU",
        "ÁP_DỤNG_CHO",
        "BỊ_XỬ_PHẠT",
        "CÓ_MỨC_HƯỞNG",
        "ÁP_DỤNG_VÙNG",
    }
)


@dataclass(frozen=True, slots=True)
class Concept:
    """One lexicon entry that can be lifted out of legal text."""

    key: str
    label: str
    patterns: tuple[str, ...]
    description: str = ""
    topics: tuple[str, ...] = field(default=())

    def matches(self, ascii_text: str) -> bool:
        return any(pattern in ascii_text for pattern in self.patterns)


def _c(key: str, label: str, patterns: str | list[str], description: str = "", topics: tuple[str, ...] = ()) -> Concept:
    pats = (patterns,) if isinstance(patterns, str) else tuple(patterns)
    return Concept(key=key, label=label, patterns=pats, description=description or label, topics=topics)


# ---------------------------------------------------------------------------
# Layer 2 - topic taxonomy (covers the whole corpus, not only labour law)
# ---------------------------------------------------------------------------

TOPICS: tuple[Concept, ...] = (
    _c("hop-dong-lao-dong", "Hợp đồng lao động",
       ["hop dong lao dong", "giao ket hop dong", "phu luc hop dong lao dong", "hop dong thu viec"],
       "Giao kết, thực hiện, sửa đổi, tạm hoãn và chấm dứt hợp đồng lao động."),
    _c("tien-luong-tien-thuong", "Tiền lương & Tiền thưởng",
       ["tien luong", "muc luong", "tra luong", "tien thuong", "thang luong", "bang luong",
        "phu cap luong", "luong toi thieu", "quy che thuong", "khau tru tien luong"],
       "Cấu thành tiền lương, nguyên tắc và hình thức trả lương, lương tối thiểu, thưởng."),
    _c("thoi-gio-lam-viec", "Thời giờ làm việc & nghỉ ngơi",
       ["thoi gio lam viec", "thoi gio nghi ngoi", "lam them gio", "nghi hang nam",
        "nghi le", "lam viec ban dem", "nghi hang tuan"],
       "Giờ làm việc bình thường, làm thêm, nghỉ phép, nghỉ lễ tết."),
    _c("ky-luat-lao-dong", "Kỷ luật lao động & Trách nhiệm vật chất",
       ["ky luat lao dong", "xu ly ky luat", "sa thai", "noi quy lao dong", "trach nhiem vat chat",
        "boi thuong thiet hai"],
       "Nội quy, hình thức kỷ luật, sa thải, bồi thường thiệt hại."),
    _c("an-toan-ve-sinh-lao-dong", "An toàn, vệ sinh lao động",
       ["an toan lao dong", "ve sinh lao dong", "tai nan lao dong", "benh nghe nghiep",
        "phuong tien bao ve ca nhan", "quan trac moi truong lao dong"],
       "Phòng ngừa, khai báo, điều tra tai nạn lao động và bệnh nghề nghiệp."),
    _c("bao-hiem-xa-hoi", "Bảo hiểm xã hội",
       ["bao hiem xa hoi", "bhxh", "che do thai san", "che do om dau", "che do huu tri",
        "tu tuat", "bhxh mot lan", "bao hiem xa hoi tu nguyen"],
       "BHXH bắt buộc, tự nguyện, các chế độ ốm đau, thai sản, hưu trí, tử tuất."),
    _c("bao-hiem-y-te", "Bảo hiểm y tế",
       ["bao hiem y te", "bhyt", "kham benh, chua benh", "the bao hiem y te"],
       "Đối tượng, mức đóng, mức hưởng bảo hiểm y tế."),
    _c("viec-lam-that-nghiep", "Việc làm & Bảo hiểm thất nghiệp",
       ["bao hiem that nghiep", "tro cap that nghiep", "dich vu viec lam", "ho tro viec lam",
        "trung tam dich vu viec lam", "ho tro hoc nghe"],
       "Chính sách việc làm, bảo hiểm thất nghiệp, trợ cấp và hỗ trợ học nghề."),
    _c("cong-doan-doi-thoai", "Công đoàn & Đối thoại, thương lượng tập thể",
       ["cong doan", "to chuc dai dien nguoi lao dong", "thuong luong tap the",
        "thoa uoc lao dong tap the", "doi thoai tai noi lam viec"],
       "Tổ chức đại diện NLĐ, đối thoại, thương lượng và thoả ước tập thể."),
    _c("lao-dong-dac-thu", "Lao động đặc thù",
       ["lao dong nu", "lao dong chua thanh nien", "nguoi khuyet tat", "lao dong cao tuoi",
        "lao dong giup viec gia dinh", "lao dong la nguoi cao tuoi"],
       "Lao động nữ, chưa thành niên, cao tuổi, khuyết tật, giúp việc gia đình."),
    _c("lao-dong-nuoc-ngoai", "Lao động nước ngoài & đi làm việc ở nước ngoài",
       ["nguoi lao dong nuoc ngoai", "giay phep lao dong", "di lam viec o nuoc ngoai",
        "hop dong dua nguoi lao dong", "lam viec tai viet nam theo hop dong"],
       "Giấy phép lao động cho người nước ngoài và NLĐ Việt Nam đi làm việc ở nước ngoài."),
    _c("tranh-chap-lao-dong", "Tranh chấp lao động & Đình công",
       ["tranh chap lao dong", "hoa giai vien lao dong", "hoi dong trong tai lao dong",
        "dinh cong", "giai quyet tranh chap"],
       "Cơ chế hoà giải, trọng tài, toà án và đình công hợp pháp."),
    _c("xu-phat-hanh-chinh", "Xử phạt vi phạm hành chính",
       ["vi pham hanh chinh", "xu phat vi pham hanh chinh", "phat tien tu", "muc phat tien",
        "bien phap khac phuc hau qua", "tham quyen xu phat"],
       "Hành vi vi phạm, thẩm quyền, mức phạt và biện pháp khắc phục hậu quả."),
    _c("khieu-nai-to-cao", "Khiếu nại & Tố cáo",
       ["khieu nai", "to cao", "giai quyet khieu nai", "giai quyet to cao", "nguoi to cao"],
       "Trình tự, thẩm quyền giải quyết khiếu nại và tố cáo."),
    _c("to-tung-thi-hanh-an", "Tố tụng & Thi hành án",
       ["to tung dan su", "to tung hanh chinh", "thi hanh an dan su", "khoi kien",
        "toa an nhan dan", "an phi", "thoi hieu khoi kien"],
       "Tố tụng dân sự, hành chính, án phí và thi hành án dân sự."),
    _c("trong-tai-hoa-giai", "Trọng tài & Hoà giải",
       ["trong tai thuong mai", "hoa giai tai toa an", "thoa thuan trong tai", "hoa giai vien"],
       "Trọng tài thương mại và hoà giải, đối thoại tại toà án."),
    _c("can-bo-cong-chuc-vien-chuc", "Cán bộ, công chức, viên chức",
       ["can bo, cong chuc", "cong chuc", "vien chuc", "hop dong lam viec", "tuyen dung cong chuc"],
       "Chế độ công vụ, tuyển dụng, sử dụng và quản lý cán bộ, công chức, viên chức."),
    _c("giao-duc-nghe-nghiep", "Giáo dục & Giáo dục nghề nghiệp",
       ["giao duc nghe nghiep", "hoc nghe", "dao tao nghe", "co so giao duc", "nguoi hoc",
        "hop dong dao tao nghe"],
       "Học nghề, đào tạo nghề, cơ sở giáo dục nghề nghiệp."),
    _c("binh-dang-gioi", "Bình đẳng giới & Chống phân biệt đối xử",
       ["binh dang gioi", "phan biet doi xu", "quay roi tinh duc", "bao dam binh dang"],
       "Bình đẳng giới trong lao động và cấm phân biệt đối xử."),
    _c("tro-giup-phap-ly", "Trợ giúp pháp lý",
       ["tro giup phap ly", "nguoi duoc tro giup phap ly", "tro giup vien phap ly"],
       "Đối tượng, phạm vi và tổ chức thực hiện trợ giúp pháp lý."),
    _c("huu-tri-tuoi-nghi-huu", "Hưu trí & Tuổi nghỉ hưu",
       ["tuoi nghi huu", "luong huu", "nghi huu truoc tuoi", "suy giam kha nang lao dong",
        "che do huu tri"],
       "Điều kiện hưởng lương hưu và lộ trình tuổi nghỉ hưu."),
    _c("cham-dut-hdld", "Chấm dứt HĐLĐ & Trợ cấp thôi việc",
       ["cham dut hop dong lao dong", "don phuong cham dut", "tro cap thoi viec",
        "tro cap mat viec lam", "thong bao cham dut"],
       "Các trường hợp chấm dứt, nghĩa vụ thông báo và trợ cấp khi chấm dứt."),
)


# ---------------------------------------------------------------------------
# Layer 3 - tiền lương & tiền thưởng (the wage/bonus knowledge core)
# ---------------------------------------------------------------------------

#: Khoản thu nhập. ``parent`` links a component to the aggregate it belongs to.
WAGE_COMPONENTS: tuple[tuple[Concept, str | None], ...] = (
    (_c("tien-luong", "Tiền lương", ["tien luong"],
        "Số tiền NSDLĐ trả cho NLĐ theo thoả thuận để thực hiện công việc, gồm mức lương theo công việc "
        "hoặc chức danh, phụ cấp lương và các khoản bổ sung khác."), None),
    (_c("muc-luong-theo-cong-viec", "Mức lương theo công việc hoặc chức danh",
        ["muc luong theo cong viec", "muc luong theo chuc danh", "luong theo chuc danh"],
        "Thành phần cốt lõi của tiền lương, không được thấp hơn mức lương tối thiểu."), "tien-luong"),
    (_c("phu-cap-luong", "Phụ cấp lương", ["phu cap luong", "cac khoan phu cap"],
        "Khoản bù đắp yếu tố về điều kiện lao động, tính chất phức tạp, điều kiện sinh hoạt."), "tien-luong"),
    (_c("khoan-bo-sung-khac", "Các khoản bổ sung khác", ["khoan bo sung khac", "cac khoan bo sung"],
        "Khoản tiền ngoài mức lương và phụ cấp, thoả thuận trong hợp đồng lao động."), "tien-luong"),
    (_c("muc-luong-toi-thieu", "Mức lương tối thiểu",
        ["muc luong toi thieu", "luong toi thieu vung", "luong toi thieu thang", "luong toi thieu gio"],
        "Mức lương thấp nhất trả cho NLĐ làm công việc giản đơn nhất trong điều kiện bình thường."), None),
    (_c("tien-luong-lam-them-gio", "Tiền lương làm thêm giờ",
        [
            "tien luong lam them gio",
            "luong lam them gio",
            "lam them gio duoc tra luong",
            "luong tang ca",
            "tang ca",
            "lam ngoai gio",
        ],
        "Tiền lương trả cho giờ làm thêm, tính theo đơn giá tiền lương hoặc tiền lương thực trả."), "tien-luong"),
    (_c("tien-luong-ban-dem", "Tiền lương làm việc vào ban đêm",
        [
            "lam viec vao ban dem",
            "tien luong lam viec vao ban dem",
            "luong ban dem",
            "ca dem",
            "lam dem",
            "ban dem",
        ],
        "Khoản trả thêm cho thời gian làm việc ban đêm."), "tien-luong"),
    (_c("tien-luong-ngung-viec", "Tiền lương ngừng việc",
        ["tien luong ngung viec", "luong ngung viec", "phai ngung viec"],
        "Tiền lương trả cho NLĐ trong thời gian phải ngừng việc."), "tien-luong"),
    (_c("tam-ung-tien-luong", "Tạm ứng tiền lương", ["tam ung tien luong", "tam ung luong"],
        "Khoản tiền lương ứng trước theo thoả thuận, không bị tính lãi."), "tien-luong"),
    (_c("khau-tru-tien-luong", "Khấu trừ tiền lương", ["khau tru tien luong", "khau tru luong"],
        "Khoản trừ vào lương để bồi thường thiệt hại, tối đa 30% tiền lương thực trả hằng tháng."), "tien-luong"),
    (_c("tien-luong-thu-viec", "Tiền lương thử việc", ["tien luong thu viec", "luong thu viec"],
        "Tiền lương trong thời gian thử việc do hai bên thoả thuận."), "tien-luong"),
    (_c("tien-luong-ngay-nghi", "Tiền lương ngày nghỉ có hưởng lương",
        ["ngay nghi co huong luong", "nghi hang nam huong nguyen luong", "nghi le, tet huong nguyen luong"],
        "Tiền lương cho ngày nghỉ lễ, tết, nghỉ hằng năm, nghỉ việc riêng có hưởng lương."), "tien-luong"),
    (_c("tien-luong-dong-bhxh", "Tiền lương làm căn cứ đóng bảo hiểm xã hội",
        ["tien luong lam can cu dong bao hiem xa hoi", "tien luong thang dong bao hiem xa hoi",
         "tien luong dong bao hiem xa hoi"],
        "Cơ sở tính mức đóng và mức hưởng các chế độ BHXH."), None),
    (_c("tien-thuong", "Tiền thưởng", ["tien thuong", "thuong cho nguoi lao dong", "thuong la so tien"],
        "Tiền, tài sản hoặc hình thức khác NSDLĐ thưởng cho NLĐ căn cứ kết quả sản xuất kinh doanh "
        "và mức độ hoàn thành công việc."), None),
    (_c("luong-huu", "Lương hưu", ["luong huu", "muc luong huu hang thang"],
        "Khoản chi trả hằng tháng cho người đủ điều kiện hưởng chế độ hưu trí."), None),
    (_c("tro-cap-thoi-viec", "Trợ cấp thôi việc", ["tro cap thoi viec"],
        "Trợ cấp cho NLĐ làm việc thường xuyên từ đủ 12 tháng khi chấm dứt HĐLĐ hợp pháp."), None),
    (_c("tro-cap-mat-viec-lam", "Trợ cấp mất việc làm", ["tro cap mat viec lam"],
        "Trợ cấp khi NLĐ mất việc do thay đổi cơ cấu, công nghệ hoặc lý do kinh tế."), None),
    (_c("tro-cap-that-nghiep", "Trợ cấp thất nghiệp", ["tro cap that nghiep"],
        "Chế độ bảo hiểm thất nghiệp trả theo tháng khi NLĐ mất việc và đủ điều kiện."), None),
    (_c("tro-cap-thai-san", "Trợ cấp thai sản", ["tro cap thai san", "che do thai san", "muc huong che do thai san"],
        "Chế độ BHXH khi NLĐ sinh con, nhận nuôi con nuôi hoặc thực hiện biện pháp tránh thai."), None),
    (_c("tro-cap-om-dau", "Trợ cấp ốm đau", ["che do om dau", "tro cap om dau", "muc huong che do om dau"],
        "Chế độ BHXH cho thời gian nghỉ việc vì ốm đau, tai nạn ngoài giờ làm việc."), None),
    (_c("tro-cap-tai-nan-lao-dong", "Trợ cấp tai nạn lao động, bệnh nghề nghiệp",
        ["tro cap tai nan lao dong", "tro cap benh nghe nghiep", "che do tai nan lao dong"],
        "Trợ cấp một lần hoặc hằng tháng theo mức suy giảm khả năng lao động."), None),
    (_c("boi-thuong-cham-dut-trai-luat", "Bồi thường do chấm dứt HĐLĐ trái pháp luật",
        ["don phuong cham dut hop dong lao dong trai phap luat", "boi thuong it nhat 02 thang tien luong",
         "nhan nguoi lao dong tro lai lam viec"],
        "Nghĩa vụ tài chính của bên chấm dứt hợp đồng lao động trái pháp luật."), None),
)

BONUS_TYPES: tuple[Concept, ...] = (
    _c("quy-che-thuong", "Quy chế thưởng", ["quy che thuong"],
       "Văn bản do NSDLĐ quyết định và công bố công khai sau khi tham khảo ý kiến tổ chức đại diện NLĐ."),
    _c("thuong-bang-tien", "Thưởng bằng tiền", ["thuong la so tien", "thuong bang tien"],
       "Hình thái thưởng phổ biến nhất - trả bằng tiền."),
    _c("thuong-bang-tai-san", "Thưởng bằng tài sản hoặc hình thức khác",
       ["hoac tai san hoac bang cac hinh thuc khac", "thuong bang tai san"],
       "Thưởng bằng hiện vật hoặc hình thức khác ngoài tiền."),
    _c("thuong-theo-ket-qua-kinh-doanh", "Thưởng theo kết quả sản xuất, kinh doanh",
       ["ket qua san xuat, kinh doanh", "muc do hoan thanh cong viec"],
       "Căn cứ xác định thưởng theo Điều 104 Bộ luật Lao động."),
    _c("thuong-sang-kien", "Thưởng sáng kiến, thi đua, khen thưởng",
       ["khen thuong", "sang kien", "thi dua"],
       "Các chế độ khuyến khích ngoài lương do NSDLĐ hoặc pháp luật chuyên ngành quy định."),
)

PAY_FORMS: tuple[Concept, ...] = (
    _c("tra-luong-theo-thoi-gian", "Trả lương theo thời gian",
       ["tra luong theo thoi gian", "hinh thuc tra luong theo thoi gian", "huong luong theo thoi gian"],
       "Trả lương theo giờ, ngày, tuần hoặc tháng làm việc."),
    _c("tra-luong-theo-san-pham", "Trả lương theo sản phẩm",
       ["tra luong theo san pham", "huong luong theo san pham", "luong theo san pham"],
       "Trả lương căn cứ số lượng, chất lượng sản phẩm hoàn thành."),
    _c("tra-luong-khoan", "Trả lương khoán", ["luong khoan", "tra luong khoan", "theo khoan"],
       "Trả lương theo khối lượng công việc khoán."),
    _c("tra-luong-tien-mat", "Trả lương bằng tiền mặt", ["tra bang tien mat", "luong duoc tra bang tien mat"],
       "Trả trực tiếp bằng tiền mặt cho NLĐ."),
    _c("tra-luong-qua-tai-khoan", "Trả lương qua tài khoản ngân hàng",
       ["qua tai khoan ca nhan cua nguoi lao dong", "tra luong qua tai khoan", "mo tai khoan tai ngan hang"],
       "Chuyển khoản; NSDLĐ chịu phí mở tài khoản và phí chuyển tiền."),
)

PAY_PERIODS: tuple[Concept, ...] = (
    _c("ky-han-theo-gio-ngay-tuan", "Kỳ hạn trả lương theo giờ, ngày, tuần",
       ["huong luong theo gio, ngay, tuan", "tra gop mot lan", "khong qua 15 ngay phai duoc tra gop"],
       "Trả sau giờ/ngày/tuần làm việc hoặc trả gộp, tối đa 15 ngày một lần."),
    _c("ky-han-theo-thang", "Kỳ hạn trả lương theo tháng",
       ["huong luong theo thang", "mot thang mot lan", "nua thang mot lan"],
       "Trả một tháng một lần hoặc nửa tháng một lần, ấn định thời điểm có tính chu kỳ."),
    _c("ky-han-theo-san-pham-khoan", "Kỳ hạn trả lương theo sản phẩm, khoán",
       ["huong luong theo san pham, theo khoan", "hang thang duoc tam ung tien luong theo khoi luong"],
       "Theo thoả thuận; công việc nhiều tháng thì hằng tháng tạm ứng theo khối lượng đã làm."),
    _c("cham-tra-luong", "Chậm trả lương",
       ["cham tra luong", "tra luong khong dung han", "cham hon 15 ngay"],
       "Trả lương chậm; từ 15 ngày trở lên NSDLĐ phải đền bù theo lãi suất huy động."),
)

WAGE_BASES: tuple[Concept, ...] = (
    _c("don-gia-tien-luong", "Đơn giá tiền lương", ["don gia tien luong"],
       "Căn cứ tính tiền lương làm thêm giờ và làm việc ban đêm."),
    _c("tien-luong-thuc-tra", "Tiền lương thực trả theo công việc đang làm",
       ["tien luong thuc tra theo cong viec dang lam", "tien luong thuc tra"],
       "Cơ sở tính tiền lương làm thêm giờ, làm việc ban đêm và mức khấu trừ."),
    _c("tien-luong-binh-quan", "Tiền lương bình quân",
       ["tien luong binh quan", "binh quan cua 06 thang lien ke", "muc binh quan tien luong"],
       "Bình quân tiền lương của các tháng liền kề - căn cứ tính trợ cấp và lương hưu."),
    _c("thang-luong-bang-luong", "Thang lương, bảng lương",
       ["thang luong, bang luong", "xay dung thang luong", "bang luong va dinh muc lao dong"],
       "Hệ thống thang, bảng lương do NSDLĐ xây dựng làm cơ sở thoả thuận và trả lương."),
    _c("dinh-muc-lao-dong", "Định mức lao động", ["dinh muc lao dong", "muc lao dong phai la muc trung binh"],
       "Mức lao động trung bình bảo đảm số đông NLĐ thực hiện được."),
    _c("bang-ke-tra-luong", "Bảng kê trả lương", ["bang ke tra luong"],
       "Bảng kê ghi rõ tiền lương, lương làm thêm giờ, lương ban đêm và các khoản khấu trừ."),
    _c("hoi-dong-tien-luong-quoc-gia", "Hội đồng tiền lương quốc gia", ["hoi dong tien luong quoc gia"],
       "Cơ quan tư vấn cho Chính phủ về mức lương tối thiểu và chính sách tiền lương."),
)

#: Wage entities that should be linked to a rate whenever a percentage is found
#: in the same clause. Maps a component key to the phrases that qualify the rate.
WAGE_RATE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tien-luong-lam-them-gio", ("lam them gio", "vao ngay thuong", "ngay nghi hang tuan", "ngay nghi le")),
    ("tien-luong-ban-dem", ("lam viec vao ban dem", "ban dem",)),
    ("khau-tru-tien-luong", ("khau tru",)),
    ("tro-cap-that-nghiep", ("tro cap that nghiep",)),
    ("tro-cap-thai-san", ("che do thai san", "thai san")),
    ("tro-cap-om-dau", ("che do om dau", "om dau")),
    ("luong-huu", ("luong huu", "ty le huong luong huu")),
    ("tien-luong-ngung-viec", ("ngung viec",)),
)

WAGE_FORMULAS: tuple[Concept, ...] = (
    _c("cach-tinh-luong-lam-them", "Cách tính tiền lương làm thêm giờ",
       ["tien luong lam them gio", "lam them gio duoc tra luong tinh theo"],
       "150% ngày thường, 200% ngày nghỉ hằng tuần, 300% ngày lễ tết."),
    _c("cach-tinh-luong-ban-dem", "Cách tính tiền lương làm việc vào ban đêm",
       ["lam viec vao ban dem thi duoc tra them"],
       "Trả thêm ít nhất 30% đơn giá tiền lương, cộng thêm 20% nếu làm thêm giờ vào ban đêm."),
    _c("cach-tinh-tro-cap-thoi-viec", "Cách tính trợ cấp thôi việc",
       ["tro cap thoi viec"], "Mỗi năm làm việc trả nửa tháng tiền lương."),
    _c("cach-tinh-tro-cap-mat-viec", "Cách tính trợ cấp mất việc làm",
       ["tro cap mat viec lam"], "Mỗi năm làm việc trả 01 tháng tiền lương, ít nhất bằng 02 tháng."),
    _c("cach-tinh-che-do-thai-san", "Cách tính mức hưởng chế độ thai sản",
       ["muc huong che do thai san"], "100% mức bình quân tiền lương tháng đóng BHXH."),
    _c("cach-tinh-che-do-om-dau", "Cách tính mức hưởng chế độ ốm đau",
       ["muc huong che do om dau"], "Tính theo tỷ lệ phần trăm mức tiền lương tháng đóng BHXH."),
    _c("cach-tinh-luong-huu", "Cách tính lương hưu",
       ["muc luong huu hang thang", "ty le huong luong huu"],
       "Tỷ lệ hưởng nhân với mức bình quân tiền lương tháng đóng BHXH."),
    _c("cach-tinh-tro-cap-that-nghiep", "Cách tính trợ cấp thất nghiệp",
       ["muc huong tro cap that nghiep"], "60% mức bình quân tiền lương tháng đóng BHTN của 06 tháng liền kề."),
    _c("cach-tinh-luong-toi-thieu-quy-doi", "Cách quy đổi mức lương tối thiểu",
       ["muc luong quy doi theo thang", "quy doi theo gio"],
       "Quy đổi lương tuần/ngày/sản phẩm/khoán về lương tháng hoặc lương giờ."),
    _c("cach-tinh-boi-thuong-tai-nan", "Cách tính bồi thường tai nạn lao động",
       ["boi thuong cho nguoi lao dong bi tai nan lao dong", "it nhat 30 thang tien luong"],
       "Bồi thường theo mức suy giảm khả năng lao động."),
)


# ---------------------------------------------------------------------------
# Layer 4 - subjects, contracts, events, benefits, obligations
# ---------------------------------------------------------------------------

SUBJECTS: tuple[Concept, ...] = (
    _c("nguoi-lao-dong", "Người lao động", ["nguoi lao dong"], "Bên làm việc theo thoả thuận và hưởng lương."),
    _c("nguoi-su-dung-lao-dong", "Người sử dụng lao động", ["nguoi su dung lao dong"],
       "Doanh nghiệp, cơ quan, tổ chức, hộ gia đình, cá nhân có thuê mướn lao động."),
    _c("to-chuc-dai-dien-nld", "Tổ chức đại diện người lao động",
       ["to chuc dai dien nguoi lao dong", "cong doan co so", "cong doan"],
       "Công đoàn cơ sở hoặc tổ chức của NLĐ tại doanh nghiệp."),
    _c("thanh-tra-lao-dong", "Thanh tra lao động", ["thanh tra lao dong", "thanh tra nha nuoc ve lao dong"],
       "Cơ quan thanh tra chuyên ngành lao động."),
    _c("co-quan-bhxh", "Cơ quan bảo hiểm xã hội", ["co quan bao hiem xa hoi"],
       "Cơ quan tổ chức thu, chi và giải quyết chế độ BHXH."),
    _c("hoa-giai-vien-lao-dong", "Hoà giải viên lao động", ["hoa giai vien lao dong"],
       "Người được bổ nhiệm để hoà giải tranh chấp lao động."),
    _c("hoi-dong-trong-tai-lao-dong", "Hội đồng trọng tài lao động", ["hoi dong trong tai lao dong"],
       "Cơ quan giải quyết tranh chấp lao động theo yêu cầu các bên."),
    _c("nguoi-su-dung-lao-dong-nuoc-ngoai", "Người lao động nước ngoài", ["nguoi lao dong nuoc ngoai"],
       "Lao động nước ngoài làm việc tại Việt Nam."),
    _c("can-bo-cong-chuc", "Cán bộ, công chức, viên chức", ["can bo, cong chuc", "vien chuc"],
       "Đối tượng điều chỉnh của pháp luật công vụ."),
)

CONTRACT_TYPES: tuple[Concept, ...] = (
    _c("hd-khong-xac-dinh-thoi-han", "HĐLĐ không xác định thời hạn",
       ["hop dong lao dong khong xac dinh thoi han", "khong xac dinh thoi han"],
       "Hợp đồng không ấn định thời hạn, thời điểm chấm dứt hiệu lực."),
    _c("hd-xac-dinh-thoi-han", "HĐLĐ xác định thời hạn",
       ["hop dong lao dong xac dinh thoi han", "xac dinh thoi han"],
       "Hợp đồng có thời hạn không quá 36 tháng kể từ thời điểm có hiệu lực."),
    _c("hd-thu-viec", "Hợp đồng thử việc", ["hop dong thu viec", "thoa thuan noi dung thu viec"],
       "Thoả thuận việc làm thử, chỉ được thử việc một lần cho một công việc."),
    _c("hd-lao-dong-dien-tu", "HĐLĐ giao kết bằng phương tiện điện tử",
       ["hop dong lao dong dien tu", "phuong tien dien tu duoi hinh thuc thong diep du lieu"],
       "HĐLĐ dưới hình thức thông điệp dữ liệu, có giá trị như hợp đồng văn bản."),
    _c("hd-dao-tao-nghe", "Hợp đồng đào tạo nghề", ["hop dong dao tao nghe", "hop dong hoc nghe"],
       "Thoả thuận về đào tạo nghề nghiệp và cam kết làm việc sau đào tạo."),
    _c("thoa-uoc-lao-dong-tap-the", "Thoả ước lao động tập thể", ["thoa uoc lao dong tap the"],
       "Thoả thuận tập thể đạt được thông qua thương lượng tập thể."),
)

EVENTS: tuple[Concept, ...] = (
    _c("sa-thai", "Sa thải", ["sa thai"], "Hình thức xử lý kỷ luật nặng nhất."),
    _c("don-phuong-cham-dut", "Đơn phương chấm dứt HĐLĐ", ["don phuong cham dut hop dong lao dong"],
       "Một bên chấm dứt hợp đồng lao động trước thời hạn."),
    _c("tu-y-nghi-viec", "Tự ý bỏ việc", ["tu y bo viec", "tu y nghi viec"],
       "Nghỉ việc không có lý do chính đáng, căn cứ để sa thải nếu đủ số ngày."),
    _c("tam-hoan-hdld", "Tạm hoãn thực hiện HĐLĐ", ["tam hoan thuc hien hop dong lao dong"],
       "Các trường hợp tạm hoãn theo luật định."),
    _c("chuyen-lam-cong-viec-khac", "Chuyển người lao động làm công việc khác",
       ["chuyen nguoi lao dong lam cong viec khac"], "Điều chuyển tạm thời so với hợp đồng lao động."),
    _c("thai-san", "Thai sản", ["thai san", "sinh con", "mang thai"], "Sự kiện thai sản của NLĐ."),
    _c("tai-nan-lao-dong", "Tai nạn lao động", ["tai nan lao dong"],
       "Tai nạn gây tổn thương cho cơ thể NLĐ trong quá trình lao động."),
    _c("benh-nghe-nghiep", "Bệnh nghề nghiệp", ["benh nghe nghiep"], "Bệnh phát sinh do điều kiện lao động."),
    _c("dinh-cong", "Đình công", ["dinh cong"], "Ngừng việc tạm thời, tự nguyện và có tổ chức của NLĐ."),
    _c("quay-roi-tinh-duc", "Quấy rối tình dục tại nơi làm việc", ["quay roi tinh duc tai noi lam viec"],
       "Hành vi bị nghiêm cấm tại nơi làm việc."),
    _c("cuong-buc-lao-dong", "Cưỡng bức lao động", ["cuong buc lao dong"],
       "Dùng vũ lực, đe doạ hoặc thủ đoạn khác ép buộc NLĐ làm việc."),
    _c("giu-giay-to-goc", "Giữ bản chính giấy tờ tuỳ thân của NLĐ",
       ["giu ban chinh giay to tuy than", "giu ban chinh van bang"],
       "Hành vi bị nghiêm cấm khi giao kết, thực hiện HĐLĐ."),
    _c("phat-tien-thay-ky-luat", "Phạt tiền, cắt lương thay việc xử lý kỷ luật",
       ["phat tien, cat luong thay viec xu ly ky luat lao dong", "phat tien thay viec xu ly ky luat"],
       "Hành vi bị nghiêm cấm khi xử lý kỷ luật lao động."),
    _c("no-luong", "Chậm trả, nợ lương người lao động",
       ["khong tra luong", "tra luong khong day du", "cham tra luong"],
       "Doanh nghiệp không trả hoặc trả chậm tiền lương."),
)

BENEFITS: tuple[Concept, ...] = (
    _c("quyen-huong-luong-tang-ca", "Lương làm thêm giờ", ["tien luong lam them gio"], "Quyền hưởng lương làm thêm."),
    _c(
        "quyen-tu-choi-cong-viec-khong-an-toan",
        "Quyền từ chối hoặc rời bỏ nơi làm việc không bảo đảm an toàn",
        [
            "tu choi lam viec",
            "tu choi cong viec",
            "roi bo noi lam viec",
            "nguy co xay ra tai nan lao dong",
            "de doa nghiem trong tinh mang",
            "khong bao dam an toan",
        ],
        (
            "Người lao động có quyền từ chối làm công việc hoặc rời bỏ nơi "
            "làm việc khi thấy rõ nguy cơ tai nạn lao động đe dọa nghiêm "
            "trọng tính mạng hoặc sức khỏe."
        ),
    ),
    _c("quyen-tro-cap-thoi-viec", "Trợ cấp thôi việc", ["tro cap thoi viec"], "Quyền hưởng trợ cấp thôi việc."),
    _c("quyen-tro-cap-mat-viec", "Trợ cấp mất việc làm", ["tro cap mat viec lam"], "Quyền hưởng trợ cấp mất việc."),
    _c("quyen-tro-cap-that-nghiep", "Trợ cấp thất nghiệp", ["tro cap that nghiep"], "Quyền hưởng BHTN."),
    _c("quyen-che-do-thai-san", "Chế độ thai sản", ["che do thai san"], "Quyền hưởng chế độ thai sản."),
    _c("quyen-che-do-om-dau", "Chế độ ốm đau", ["che do om dau"], "Quyền hưởng chế độ ốm đau."),
    _c("quyen-che-do-huu-tri", "Chế độ hưu trí", ["che do huu tri", "luong huu"], "Quyền hưởng lương hưu."),
    _c("quyen-boi-thuong-tnld", "Bồi thường tai nạn lao động", ["boi thuong tai nan lao dong", "tro cap tai nan lao dong"],
       "Quyền được bồi thường, trợ cấp khi bị TNLĐ, BNN."),
    _c("quyen-nghi-hang-nam", "Nghỉ hằng năm hưởng nguyên lương", ["nghi hang nam", "nghi phep nam"],
       "Quyền nghỉ phép năm hưởng nguyên lương."),
    _c("quyen-bhyt", "Chế độ bảo hiểm y tế", ["bao hiem y te"], "Quyền khám chữa bệnh theo BHYT."),
    _c("quyen-tro-giup-phap-ly", "Trợ giúp pháp lý miễn phí", ["tro giup phap ly"],
       "Quyền được trợ giúp pháp lý của đối tượng theo luật định."),
)

OBLIGATIONS: tuple[Concept, ...] = (
    _c("nv-dong-bhxh", "Nghĩa vụ đóng bảo hiểm xã hội bắt buộc",
       ["dong bao hiem xa hoi bat buoc", "trach nhiem dong bao hiem xa hoi", "dong bhxh"],
       "NSDLĐ và NLĐ phải tham gia BHXH bắt buộc."),
    _c("nv-xay-dung-thang-bang-luong", "Nghĩa vụ xây dựng thang lương, bảng lương",
       ["phai xay dung thang luong, bang luong", "xay dung thang luong"],
       "NSDLĐ phải xây dựng thang, bảng lương và định mức lao động."),
    _c("nv-ban-hanh-noi-quy", "Nghĩa vụ ban hành và đăng ký nội quy lao động",
       ["noi quy lao dong", "dang ky noi quy lao dong"],
       "Sử dụng từ 10 NLĐ trở lên thì nội quy lao động phải bằng văn bản và phải đăng ký."),
    _c("nv-bao-cao-su-dung-lao-dong", "Nghĩa vụ báo cáo tình hình sử dụng lao động",
       ["bao cao tinh hinh su dung lao dong", "khai trinh viec su dung lao dong"],
       "Báo cáo định kỳ với cơ quan quản lý nhà nước về lao động."),
    _c("nv-thong-bao-cham-dut", "Nghĩa vụ báo trước khi chấm dứt HĐLĐ",
       ["phai bao truoc", "thoi han bao truoc"],
       "Thời hạn báo trước khi đơn phương chấm dứt hợp đồng lao động."),
    _c("nv-tra-luong-dung-han", "Nghĩa vụ trả lương trực tiếp, đầy đủ, đúng hạn",
       ["tra luong truc tiep, day du, dung han"],
       "Nguyên tắc trả lương của NSDLĐ."),
    _c("nv-cong-khai-quy-che-thuong", "Nghĩa vụ công bố công khai quy chế thưởng",
       ["cong bo cong khai tai noi lam viec"],
       "Quy chế thưởng phải được công bố công khai sau khi tham khảo ý kiến tổ chức đại diện NLĐ."),
    _c("nv-dam-bao-an-toan", "Nghĩa vụ bảo đảm an toàn, vệ sinh lao động",
       ["bao dam an toan, ve sinh lao dong", "trang bi phuong tien bao ve ca nhan"],
       "NSDLĐ phải bảo đảm điều kiện an toàn, vệ sinh lao động."),
)


# ---------------------------------------------------------------------------
# Layer 5 - procedures
# ---------------------------------------------------------------------------

PROCEDURES: tuple[Concept, ...] = (
    _c("tt-tro-cap-that-nghiep", "Thủ tục hưởng trợ cấp thất nghiệp",
       ["huong tro cap that nghiep", "de nghi huong tro cap that nghiep"],
       "Nộp hồ sơ tại trung tâm dịch vụ việc làm trong thời hạn luật định."),
    _c("tt-bhxh-mot-lan", "Thủ tục hưởng bảo hiểm xã hội một lần",
       ["bao hiem xa hoi mot lan", "huong bhxh mot lan"],
       "Điều kiện, hồ sơ và cơ quan giải quyết BHXH một lần."),
    _c("tt-che-do-thai-san", "Thủ tục hưởng chế độ thai sản",
       ["giai quyet huong che do thai san", "ho so huong che do thai san"],
       "Hồ sơ và thời hạn giải quyết chế độ thai sản."),
    _c("tt-che-do-om-dau", "Thủ tục hưởng chế độ ốm đau",
       ["ho so huong che do om dau", "giai quyet huong che do om dau"],
       "Hồ sơ và thời hạn giải quyết chế độ ốm đau."),
    _c("tt-huu-tri", "Thủ tục hưởng lương hưu",
       ["ho so huong luong huu", "giai quyet huong luong huu"], "Hồ sơ và trình tự giải quyết chế độ hưu trí."),
    _c("tt-dang-ky-noi-quy", "Thủ tục đăng ký nội quy lao động",
       ["dang ky noi quy lao dong", "ho so dang ky noi quy lao dong"],
       "Đăng ký nội quy lao động tại cơ quan chuyên môn về lao động cấp tỉnh."),
    _c("tt-cap-giay-phep-lao-dong", "Thủ tục cấp giấy phép lao động cho người nước ngoài",
       ["cap giay phep lao dong", "de nghi cap giay phep lao dong"],
       "Hồ sơ, thời hạn cấp và gia hạn giấy phép lao động."),
    _c("tt-giai-quyet-tranh-chap", "Thủ tục giải quyết tranh chấp lao động",
       ["giai quyet tranh chap lao dong", "yeu cau hoa giai vien lao dong"],
       "Hoà giải viên → hội đồng trọng tài → toà án."),
    _c("tt-khieu-nai-lao-dong", "Thủ tục khiếu nại về lao động",
       ["khieu nai lan dau", "khieu nai lan hai", "trinh tu khieu nai"],
       "Khiếu nại lần đầu tới NSDLĐ, lần hai tới cơ quan nhà nước có thẩm quyền."),
    _c("tt-to-cao", "Thủ tục tố cáo", ["trinh tu giai quyet to cao", "tiep nhan to cao"],
       "Tiếp nhận, thụ lý, xác minh và kết luận nội dung tố cáo."),
    _c("tt-khoi-kien-lao-dong", "Thủ tục khởi kiện vụ án lao động",
       ["khoi kien vu an lao dong", "don khoi kien"], "Khởi kiện tại toà án nhân dân có thẩm quyền."),
    _c("tt-dieu-tra-tnld", "Thủ tục khai báo, điều tra tai nạn lao động",
       ["khai bao tai nan lao dong", "dieu tra tai nan lao dong"],
       "Khai báo, điều tra, lập biên bản và thống kê tai nạn lao động."),
    _c("tt-xu-ly-ky-luat", "Thủ tục xử lý kỷ luật lao động",
       ["trinh tu, thu tuc xu ly ky luat lao dong", "hop xu ly ky luat lao dong"],
       "Trình tự họp xử lý kỷ luật lao động với sự tham gia của tổ chức đại diện NLĐ."),
    _c("tt-xu-phat-vphc", "Thủ tục xử phạt vi phạm hành chính",
       ["lap bien ban vi pham hanh chinh", "ra quyet dinh xu phat"],
       "Lập biên bản, ra quyết định và thi hành quyết định xử phạt."),
)

DOSSIERS: tuple[Concept, ...] = (
    _c("so-bhxh", "Sổ bảo hiểm xã hội", ["so bao hiem xa hoi", "so bhxh"], "Sổ ghi nhận quá trình đóng BHXH."),
    _c("qd-thoi-viec", "Quyết định thôi việc / chấm dứt HĐLĐ",
       ["quyet dinh thoi viec", "quyet dinh cham dut hop dong lao dong"], "Căn cứ chứng minh chấm dứt quan hệ lao động."),
    _c("don-de-nghi", "Đơn đề nghị hưởng chế độ", ["don de nghi huong", "don de nghi"], "Đơn theo mẫu quy định."),
    _c("noi-quy-lao-dong", "Văn bản nội quy lao động", ["noi quy lao dong"], "Nội quy lao động bằng văn bản."),
    _c("giay-chung-sinh", "Giấy khai sinh, giấy chứng sinh", ["giay chung sinh", "giay khai sinh"],
       "Chứng từ trong hồ sơ hưởng chế độ thai sản."),
    _c("giay-ra-vien", "Giấy ra viện, giấy chứng nhận nghỉ việc hưởng BHXH",
       ["giay ra vien", "giay chung nhan nghi viec huong bao hiem xa hoi"], "Chứng từ hồ sơ ốm đau, thai sản."),
    _c("bien-ban-dieu-tra-tnld", "Biên bản điều tra tai nạn lao động", ["bien ban dieu tra tai nan lao dong"],
       "Tài liệu bắt buộc trong hồ sơ hưởng chế độ TNLĐ."),
    _c("giay-phep-lao-dong", "Giấy phép lao động", ["giay phep lao dong"],
       "Điều kiện để người nước ngoài làm việc hợp pháp tại Việt Nam."),
    _c("hop-dong-lao-dong-ban-goc", "Bản hợp đồng lao động", ["ban hop dong lao dong", "hop dong lao dong da giao ket"],
       "Chứng cứ gốc về quan hệ lao động."),
    _c("can-cuoc-cong-dan", "Căn cước công dân / hộ chiếu", ["can cuoc cong dan", "the can cuoc", "ho chieu"],
       "Giấy tờ tuỳ thân trong hồ sơ hành chính."),
)

CONDITIONS: tuple[Concept, ...] = (
    _c("dk-dong-du-12-thang", "Đóng bảo hiểm từ đủ 12 tháng trở lên",
       ["dong bao hiem that nghiep tu du 12 thang", "du 12 thang tro len"],
       "Điều kiện phổ biến để hưởng BHTN và trợ cấp thôi việc."),
    _c("dk-nghi-viec-du-1-nam", "Sau 12 tháng không tiếp tục đóng bảo hiểm",
       ["sau 12 thang khong tiep tuc dong bao hiem xa hoi", "nghi viec du 1 nam"],
       "Điều kiện hưởng BHXH một lần."),
    _c("dk-tu-10-lao-dong", "Sử dụng từ 10 người lao động trở lên",
       ["su dung tu 10 nguoi lao dong tro len", "tu 10 nguoi lao dong tro len"],
       "Ngưỡng bắt buộc ban hành và đăng ký nội quy lao động bằng văn bản."),
    _c("dk-du-tuoi-nghi-huu", "Đủ tuổi nghỉ hưu theo quy định",
       ["du tuoi nghi huu", "tuoi nghi huu trong dieu kien lao dong binh thuong"],
       "Điều kiện hưởng lương hưu."),
    _c("dk-du-15-nam-dong-bhxh", "Đủ 15 năm đóng bảo hiểm xã hội trở lên",
       ["du 15 nam dong bao hiem xa hoi", "tu du 15 nam tro len"], "Điều kiện tối thiểu để hưởng lương hưu."),
    _c("dk-lam-viec-12-thang", "Làm việc thường xuyên từ đủ 12 tháng trở lên",
       ["lam viec thuong xuyen tu du 12 thang tro len"],
       "Điều kiện hưởng trợ cấp thôi việc, trợ cấp mất việc làm."),
    _c("dk-suy-giam-kha-nang", "Suy giảm khả năng lao động từ 5% trở lên",
       ["suy giam kha nang lao dong tu 5%", "suy giam kha nang lao dong"],
       "Điều kiện hưởng chế độ tai nạn lao động, bệnh nghề nghiệp."),
    _c("dk-nop-ho-so-3-thang", "Nộp hồ sơ trong thời hạn 03 tháng",
       ["trong thoi han 03 thang ke tu ngay cham dut hop dong lao dong"],
       "Thời hạn nộp hồ sơ hưởng trợ cấp thất nghiệp."),
)

AGENCIES: tuple[Concept, ...] = (
    _c("cq-bhxh", "Cơ quan Bảo hiểm xã hội", ["co quan bao hiem xa hoi"], "Giải quyết chế độ BHXH."),
    _c("cq-ttdvvl", "Trung tâm dịch vụ việc làm", ["trung tam dich vu viec lam"],
       "Tiếp nhận hồ sơ bảo hiểm thất nghiệp, tư vấn giới thiệu việc làm."),
    _c("cq-so-ldtbxh", "Cơ quan chuyên môn về lao động cấp tỉnh",
       ["so lao dong", "co quan chuyen mon ve lao dong thuoc uy ban nhan dan cap tinh"],
       "Đăng ký nội quy lao động, cấp giấy phép lao động, thanh tra lao động."),
    _c("cq-toa-an", "Toà án nhân dân", ["toa an nhan dan", "toa an"], "Giải quyết tranh chấp lao động, khởi kiện."),
    _c("cq-ubnd", "Uỷ ban nhân dân các cấp", ["uy ban nhan dan"], "Cơ quan quản lý nhà nước tại địa phương."),
    _c("cq-thanh-tra", "Thanh tra lao động", ["thanh tra lao dong", "chanh thanh tra"],
       "Thanh tra, kiểm tra và xử phạt vi phạm pháp luật lao động."),
    _c("cq-cong-doan", "Tổ chức Công đoàn", ["cong doan co so", "lien doan lao dong"],
       "Đại diện, bảo vệ quyền lợi hợp pháp của NLĐ."),
    _c("cq-thi-hanh-an", "Cơ quan thi hành án dân sự", ["co quan thi hanh an dan su", "chi cuc thi hanh an"],
       "Tổ chức thi hành bản án, quyết định đã có hiệu lực."),
)


# ---------------------------------------------------------------------------
# Layer 6 - temporal triggers and legal states
# ---------------------------------------------------------------------------

TIME_TRIGGERS: tuple[Concept, ...] = (
    _c("sk-cham-dut-hdld", "Chấm dứt hợp đồng lao động",
       ["ke tu ngay cham dut hop dong lao dong", "cham dut hop dong lao dong"],
       "Mốc bắt đầu tính nghĩa vụ thanh toán và thời hiệu."),
    _c("sk-quyet-dinh-ky-luat", "Ban hành quyết định kỷ luật",
       ["quyet dinh xu ly ky luat", "ke tu ngay phat hien hanh vi vi pham"],
       "Mốc tính thời hiệu xử lý kỷ luật lao động."),
    _c("sk-sinh-con", "Sinh con hoặc nhận nuôi con nuôi", ["ke tu ngay sinh con", "sinh con", "nhan nuoi con nuoi"],
       "Mốc tính chế độ thai sản."),
    _c("sk-tai-nan-lao-dong", "Xảy ra tai nạn lao động", ["ke tu ngay bi tai nan", "xay ra tai nan lao dong"],
       "Mốc khai báo, điều tra và giải quyết chế độ TNLĐ."),
    _c("sk-nhan-quyet-dinh-hanh-chinh", "Nhận quyết định hành chính",
       ["ke tu ngay nhan duoc quyet dinh", "ke tu ngay nhan duoc quyet dinh hanh chinh"],
       "Mốc tính thời hiệu khiếu nại, khởi kiện hành chính."),
    _c("sk-phat-hien-hanh-vi", "Phát hiện hành vi vi phạm",
       ["ke tu ngay phat hien hanh vi vi pham", "ngay phat hien vi pham"],
       "Mốc tính thời hiệu xử phạt vi phạm hành chính."),
    _c("sk-hop-dong-het-han", "Hợp đồng lao động hết hạn", ["hop dong lao dong het han", "het han hop dong"],
       "Mốc phát sinh nghĩa vụ giao kết hợp đồng mới."),
)

LEGAL_STATES: tuple[Concept, ...] = (
    _c("tt-con-thoi-hieu", "Còn thời hiệu yêu cầu / khởi kiện",
       ["con thoi hieu"], "Trạng thái vụ việc vẫn được thụ lý."),
    _c("tt-het-thoi-hieu", "Hết thời hiệu yêu cầu / khởi kiện",
       ["het thoi hieu", "thoi hieu khoi kien", "thoi hieu yeu cau"],
       "Trạng thái mất quyền yêu cầu cơ quan có thẩm quyền giải quyết."),
    _c("tt-hop-dong-vo-hieu", "Hợp đồng lao động vô hiệu",
       ["hop dong lao dong vo hieu"], "Hợp đồng bị tuyên vô hiệu toàn bộ hoặc từng phần."),
    _c("tt-cham-dut-trai-luat", "Chấm dứt hợp đồng lao động trái pháp luật",
       ["cham dut hop dong lao dong trai phap luat"], "Trạng thái làm phát sinh nghĩa vụ bồi thường."),
    _c("tt-qua-han-nop-ho-so", "Quá hạn nộp hồ sơ",
       ["qua thoi han nop ho so", "khong nop ho so dung han"], "Trạng thái mất quyền hưởng chế độ."),
)


# ---------------------------------------------------------------------------
# Layer 7 - violations, sanctions and remedies
# ---------------------------------------------------------------------------

VIOLATIONS: tuple[Concept, ...] = (
    _c("vp-khong-giao-ket-hdld", "Không giao kết HĐLĐ bằng văn bản đúng loại",
       ["khong giao ket hop dong lao dong bang van ban", "giao ket khong dung loai hop dong lao dong"],
       "Vi phạm quy định về giao kết hợp đồng lao động."),
    _c("vp-thu-viec-sai", "Vi phạm quy định về thử việc",
       ["thu viec qua 01 lan", "thu viec qua mot lan", "thoi gian thu viec vuot qua"],
       "Thử việc quá số lần hoặc quá thời gian, trả lương thử việc thấp hơn mức quy định."),
    _c("vp-tra-luong-khong-dung", "Trả lương không đúng quy định",
       ["tra luong khong dung han", "tra luong thap hon muc luong toi thieu", "khong tra hoac tra khong du tien luong"],
       "Trả lương chậm, thiếu hoặc thấp hơn mức lương tối thiểu."),
    _c("vp-khong-xay-dung-thang-luong", "Không xây dựng thang lương, bảng lương, định mức lao động",
       ["khong xay dung thang luong, bang luong", "khong xay dung dinh muc lao dong"],
       "Vi phạm nghĩa vụ tại Điều 93 Bộ luật Lao động."),
    _c("vp-khong-cong-bo-quy-che-thuong", "Không công bố công khai quy chế thưởng",
       ["khong cong bo cong khai tai noi lam viec quy che thuong", "khong cong khai quy che thuong"],
       "Vi phạm nghĩa vụ tại Điều 104 Bộ luật Lao động."),
    _c("vp-khong-dang-ky-noi-quy", "Không đăng ký nội quy lao động",
       ["khong dang ky noi quy lao dong", "khong ban hanh noi quy lao dong"],
       "Vi phạm nghĩa vụ đăng ký nội quy lao động."),
    _c("vp-khong-dong-bhxh", "Không đóng, chậm đóng, trốn đóng bảo hiểm xã hội",
       ["khong dong bao hiem xa hoi", "cham dong bao hiem xa hoi", "tron dong bao hiem xa hoi"],
       "Vi phạm nghĩa vụ tham gia BHXH bắt buộc."),
    _c("vp-phat-tien-thay-ky-luat", "Dùng hình thức phạt tiền, cắt lương thay xử lý kỷ luật",
       ["phat tien, cat luong thay viec xu ly ky luat lao dong", "dung hinh thuc phat tien"],
       "Hành vi bị nghiêm cấm khi xử lý kỷ luật lao động."),
    _c("vp-sa-thai-trai-phap-luat", "Sa thải hoặc đơn phương chấm dứt HĐLĐ trái pháp luật",
       ["sa thai nguoi lao dong trai phap luat", "don phuong cham dut hop dong lao dong trai phap luat"],
       "Chấm dứt quan hệ lao động không đúng căn cứ hoặc trình tự."),
    _c("vp-lao-dong-nu-mang-thai", "Xử lý kỷ luật, sa thải NLĐ đang mang thai, nuôi con nhỏ",
       ["nguoi lao dong dang mang thai", "nuoi con duoi 12 thang tuoi"],
       "Hành vi bị cấm đối với lao động nữ mang thai, nuôi con dưới 12 tháng tuổi."),
    _c("vp-lam-them-qua-gio", "Huy động làm thêm giờ vượt quá số giờ quy định",
       ["lam them gio vuot qua so gio", "qua 200 gio", "qua 300 gio"],
       "Vượt trần giờ làm thêm theo tháng hoặc theo năm."),
    _c("vp-giu-giay-to", "Giữ bản chính giấy tờ tuỳ thân, văn bằng của NLĐ",
       ["giu ban chinh giay to tuy than, van bang", "giu ban chinh giay to tuy than"],
       "Hành vi bị nghiêm cấm khi giao kết, thực hiện HĐLĐ."),
    _c("vp-yeu-cau-bao-dam-tien", "Buộc NLĐ thực hiện biện pháp bảo đảm bằng tiền, tài sản",
       ["thuc hien bien phap bao dam bang tien hoac tai san khac"],
       "Hành vi bị nghiêm cấm khi giao kết hợp đồng lao động."),
    _c("vp-phan-biet-doi-xu", "Phân biệt đối xử trong lao động",
       ["phan biet doi xu trong lao dong", "phan biet doi xu ve gioi"],
       "Hành vi bị nghiêm cấm theo Bộ luật Lao động và Luật Bình đẳng giới."),
    _c("vp-khong-tra-so-bhxh", "Không hoàn thành thủ tục xác nhận, trả lại sổ BHXH và giấy tờ",
       ["hoan thanh thu tuc xac nhan thoi gian dong bao hiem xa hoi", "tra lai ban chinh giay to khac"],
       "Nghĩa vụ của NSDLĐ khi chấm dứt hợp đồng lao động."),
    _c("vp-khong-lam-thu-tuc-atvsld", "Vi phạm quy định về an toàn, vệ sinh lao động",
       ["khong to chuc huan luyen an toan", "khong trang bi phuong tien bao ve ca nhan",
        "khong kham suc khoe dinh ky"],
       "Vi phạm nghĩa vụ bảo đảm an toàn, vệ sinh lao động."),
)

EXTRA_SANCTIONS: tuple[Concept, ...] = (
    _c("xp-tuoc-giay-phep", "Tước quyền sử dụng giấy phép, chứng chỉ hành nghề",
       ["tuoc quyen su dung giay phep", "tuoc quyen su dung chung chi hanh nghe"], ""),
    _c("xp-dinh-chi-hoat-dong", "Đình chỉ hoạt động có thời hạn", ["dinh chi hoat dong co thoi han", "dinh chi hoat dong"], ""),
    _c("xp-tich-thu-tang-vat", "Tịch thu tang vật, phương tiện vi phạm",
       ["tich thu tang vat", "tich thu phuong tien vi pham hanh chinh"], ""),
    _c("xp-truc-xuat", "Trục xuất", ["truc xuat"], ""),
)

REMEDIES: tuple[Concept, ...] = (
    _c("kp-truy-dong-bhxh", "Buộc truy đóng, đóng đủ bảo hiểm xã hội",
       ["buoc dong du tien bao hiem xa hoi", "truy dong bao hiem xa hoi", "buoc truy nop so tien bao hiem"], ""),
    _c("kp-tra-du-tien-luong", "Buộc trả đủ tiền lương cộng lãi cho người lao động",
       ["buoc tra du tien luong", "cong voi khoan tien lai cua so tien luong cham tra"], ""),
    _c("kp-nhan-lai-nld", "Buộc nhận người lao động trở lại làm việc",
       ["buoc nhan nguoi lao dong tro lai lam viec", "nhan nguoi lao dong tro lai lam viec"], ""),
    _c("kp-hoan-tra-giay-to", "Buộc trả lại bản chính giấy tờ tuỳ thân, văn bằng",
       ["buoc tra lai ban chinh giay to tuy than"], ""),
    _c("kp-hoan-tra-tien", "Buộc hoàn trả khoản tiền đã thu hoặc đã phạt trái luật",
       ["buoc tra lai so tien", "buoc hoan tra", "buoc nop lai so loi bat hop phap"], ""),
    _c("kp-giao-ket-dung-loai-hd", "Buộc giao kết đúng loại hợp đồng lao động",
       ["buoc giao ket dung loai hop dong lao dong"], ""),
    _c("kp-xay-dung-thang-luong", "Buộc xây dựng thang lương, bảng lương, định mức lao động",
       ["buoc xay dung thang luong", "buoc xay dung dinh muc lao dong"], ""),
    _c("kp-cong-khai-quy-che", "Buộc công bố công khai quy chế thưởng, thang bảng lương",
       ["buoc cong bo cong khai"], ""),
)

RISK_LEVELS: tuple[tuple[str, str, str], ...] = (
    ("thap", "Mức độ rủi ro: Thấp", "Nhắc nhở, cảnh cáo hoặc phạt tiền dưới 10 triệu đồng."),
    ("vua", "Mức độ rủi ro: Vừa", "Phạt tiền hành chính từ 10 đến dưới 75 triệu đồng, buộc khắc phục hậu quả."),
    ("cao", "Mức độ rủi ro: Cao", "Phạt tiền từ 75 triệu đồng trở lên hoặc kèm hình thức xử phạt bổ sung."),
    ("nghiem-trong", "Mức độ rủi ro: Nghiêm trọng",
     "Đình chỉ hoạt động, bồi thường lớn hoặc bị truy cứu trách nhiệm hình sự."),
)

#: Fine ceilings (VND) used to bucket a penalty range into a risk level.
RISK_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (10_000_000, "thap"),
    (75_000_000, "vua"),
    (150_000_000, "cao"),
)


# ---------------------------------------------------------------------------
# Layer 8 - lifecycles
# ---------------------------------------------------------------------------

LIFECYCLE_NLD: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("tuyen-dung", "Tuyển dụng", "Tìm kiếm, tuyển chọn và cung cấp thông tin trước khi giao kết HĐLĐ.",
     ("tuyen dung lao dong", "cung cap thong tin khi giao ket hop dong lao dong")),
    ("thu-viec", "Thử việc", "Làm thử, đánh giá mức độ phù hợp trước khi ký hợp đồng chính thức.",
     ("thu viec",)),
    ("ky-hdld", "Ký hợp đồng lao động", "Xác lập quan hệ lao động chính thức bằng văn bản hoặc dữ liệu điện tử.",
     ("giao ket hop dong lao dong", "ky ket hop dong lao dong")),
    ("lam-viec", "Làm việc & hưởng lương", "Thực hiện công việc, hưởng lương, thưởng, BHXH và các chế độ.",
     ("tra luong", "tien luong", "dong bao hiem xa hoi", "thoi gio lam viec")),
    ("om-dau-thai-san", "Ốm đau / Thai sản / Tai nạn lao động", "Nghỉ việc hưởng chế độ bảo hiểm xã hội.",
     ("che do om dau", "che do thai san", "tai nan lao dong")),
    ("ky-luat-tranh-chap", "Kỷ luật & Tranh chấp", "Xử lý kỷ luật lao động và giải quyết tranh chấp phát sinh.",
     ("xu ly ky luat lao dong", "tranh chap lao dong")),
    ("cham-dut-hdld", "Chấm dứt HĐLĐ", "Chấm dứt quan hệ lao động và thanh toán các khoản khi chấm dứt.",
     ("cham dut hop dong lao dong", "tro cap thoi viec")),
    ("nghi-huu", "Nghỉ hưu", "Kết thúc độ tuổi lao động và hưởng lương hưu.",
     ("tuoi nghi huu", "luong huu", "che do huu tri")),
)

LIFECYCLE_DN: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("thanh-lap", "Thành lập doanh nghiệp", "Đăng ký thành lập và bắt đầu hoạt động.",
     ("thanh lap doanh nghiep",)),
    ("khai-trinh-lao-dong", "Khai trình sử dụng lao động", "Khai trình và báo cáo tình hình sử dụng lao động.",
     ("khai trinh viec su dung lao dong", "bao cao tinh hinh su dung lao dong")),
    ("thang-bang-luong", "Xây dựng thang lương, bảng lương", "Xây dựng thang, bảng lương và định mức lao động.",
     ("thang luong, bang luong", "dinh muc lao dong")),
    ("noi-quy-lao-dong", "Ban hành & đăng ký nội quy lao động", "Ban hành nội quy và đăng ký với cơ quan có thẩm quyền.",
     ("noi quy lao dong", "dang ky noi quy lao dong")),
    ("quy-che-thuong", "Ban hành quy chế thưởng & đối thoại", "Ban hành quy chế thưởng, tổ chức đối thoại tại nơi làm việc.",
     ("quy che thuong", "doi thoai tai noi lam viec")),
    ("dong-bhxh", "Đóng bảo hiểm xã hội", "Đăng ký và đóng BHXH, BHYT, BHTN cho người lao động.",
     ("dong bao hiem xa hoi", "dong bao hiem that nghiep")),
    ("thanh-tra-xu-phat", "Thanh tra & Xử phạt", "Chịu thanh tra, kiểm tra và xử phạt vi phạm hành chính nếu có.",
     ("thanh tra lao dong", "xu phat vi pham hanh chinh")),
    ("giai-the", "Giải thể / Phá sản", "Chấm dứt hoạt động và giải quyết quyền lợi người lao động.",
     ("giai the", "pha san")),
)


# ---------------------------------------------------------------------------
# Curated seed definitions (used when a term has no in-corpus definition)
# ---------------------------------------------------------------------------

SEED_TERMS: dict[str, str] = {
    "người lao động": "Người làm việc cho người sử dụng lao động theo thoả thuận, được trả lương và chịu sự "
                      "quản lý, điều hành, giám sát của người sử dụng lao động.",
    "người sử dụng lao động": "Doanh nghiệp, cơ quan, tổ chức, hợp tác xã, hộ gia đình, cá nhân có thuê mướn, "
                              "sử dụng người lao động làm việc cho mình theo thoả thuận.",
    "hợp đồng lao động": "Sự thoả thuận giữa người lao động và người sử dụng lao động về việc làm có trả công, "
                         "tiền lương, điều kiện lao động, quyền và nghĩa vụ của mỗi bên.",
    "tiền lương": "Số tiền người sử dụng lao động trả cho người lao động theo thoả thuận để thực hiện công việc, "
                  "bao gồm mức lương theo công việc hoặc chức danh, phụ cấp lương và các khoản bổ sung khác.",
    "thưởng": "Số tiền hoặc tài sản hoặc bằng các hình thức khác mà người sử dụng lao động thưởng cho người lao "
              "động căn cứ vào kết quả sản xuất, kinh doanh, mức độ hoàn thành công việc của người lao động.",
    "mức lương tối thiểu": "Mức lương thấp nhất được trả cho người lao động làm công việc giản đơn nhất trong "
                           "điều kiện lao động bình thường nhằm bảo đảm mức sống tối thiểu của người lao động "
                           "và gia đình họ.",
}


def relation_english(relation: str) -> str:
    spec = RELATIONS.get(relation)
    return spec[0] if spec else "RELATED_TO"


def relation_weight(relation: str, default: float = 0.40) -> float:
    return RELATION_WEIGHTS.get(relation, default)


def node_layer(node_type: str) -> int:
    spec = NODE_TYPES.get(node_type)
    return spec[0] if spec else 1


__all__ = [
    "LAYERS",
    "NODE_TYPES",
    "RELATIONS",
    "RELATION_WEIGHTS",
    "REVERSIBLE_RELATIONS",
    "Concept",
    "TOPICS",
    "WAGE_COMPONENTS",
    "BONUS_TYPES",
    "PAY_FORMS",
    "PAY_PERIODS",
    "WAGE_BASES",
    "WAGE_RATE_HINTS",
    "WAGE_FORMULAS",
    "SUBJECTS",
    "CONTRACT_TYPES",
    "EVENTS",
    "BENEFITS",
    "OBLIGATIONS",
    "PROCEDURES",
    "DOSSIERS",
    "CONDITIONS",
    "AGENCIES",
    "TIME_TRIGGERS",
    "LEGAL_STATES",
    "VIOLATIONS",
    "EXTRA_SANCTIONS",
    "REMEDIES",
    "RISK_LEVELS",
    "RISK_THRESHOLDS",
    "LIFECYCLE_NLD",
    "LIFECYCLE_DN",
    "SEED_TERMS",
    "relation_english",
    "relation_weight",
    "node_layer",
]
