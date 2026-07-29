import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ClipboardCheck,
  FileDiff,
  FilePenLine,
  MessageSquareText,
  Scale,
  SearchCheck,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

type LandingPageProps = {
  authAvailable: boolean;
  loginUrl: string;
};

const capabilities = [
  {
    icon: MessageSquareText,
    number: "01",
    title: "Hỏi đáp pháp luật",
    description: "Nhận câu trả lời rõ ràng, có căn cứ và biết chính xác nguồn nào đã được sử dụng.",
    accent: "Tra cứu",
  },
  {
    icon: FilePenLine,
    number: "02",
    title: "Soạn thảo hợp đồng",
    description: "Tạo bản nháp có cấu trúc hoặc hoàn thiện hợp đồng từ nội dung bạn đã chuẩn bị.",
    accent: "Soạn thảo",
  },
  {
    icon: ClipboardCheck,
    number: "03",
    title: "Review rủi ro",
    description: "Phát hiện điều khoản bất lợi, thiếu sót và những điểm cần thương lượng trước khi ký.",
    accent: "Kiểm tra",
  },
  {
    icon: FileDiff,
    number: "04",
    title: "So sánh phiên bản",
    description: "Làm rõ nội dung thêm, xóa, chỉnh sửa và tác động pháp lý giữa hai văn bản.",
    accent: "Đối chiếu",
  },
];

const workingSteps = [
  {
    number: "01",
    title: "Đặt câu hỏi",
    description: "Mô tả vấn đề bằng ngôn ngữ tự nhiên, kể cả khi bạn chưa biết thuật ngữ pháp lý.",
  },
  {
    number: "02",
    title: "Đối chiếu căn cứ",
    description: "VLegal tìm nội dung liên quan, kiểm tra hiệu lực và sắp xếp nguồn theo mức độ phù hợp.",
  },
  {
    number: "03",
    title: "Nhận hướng xử lý",
    description: "Kết quả được diễn giải dễ hiểu, nêu điểm cần lưu ý và gợi ý bước tiếp theo.",
  },
];

export default function LandingPage({ authAvailable, loginUrl }: LandingPageProps) {
  return (
    <main className="lp-page">
      <header className="lp-nav" aria-label="Điều hướng VLegal AI">
        <a className="lp-brand" href="#top" aria-label="VLegal AI — Trang đầu">
          <span className="lp-brand-mark" aria-hidden="true"><Scale size={22} /></span>
          <span>
            <strong>VLegal</strong>
            <small>Trợ lý pháp lý AI</small>
          </span>
        </a>

        <nav className="lp-nav-links" aria-label="Nội dung trang">
          <a href="#capabilities">Khả năng</a>
          <a href="#workflow">Cách hoạt động</a>
          <a href="#trust">Minh bạch</a>
        </nav>

        {authAvailable ? (
          <a className="lp-nav-login" href={loginUrl}>
            Đăng nhập <ArrowRight size={16} />
          </a>
        ) : (
          <span className="lp-nav-offline">Đăng nhập tạm gián đoạn</span>
        )}
      </header>

      <section className="lp-hero" id="top">
        <div className="lp-hero-copy">
          <p className="lp-eyebrow"><Sparkles size={15} /> Legal intelligence for Vietnam</p>
          <h1>
            Hiểu luật rõ hơn.
            <span>Hành động tự tin hơn.</span>
          </h1>
          <p className="lp-hero-intro">
            VLegal giúp bạn tra cứu pháp luật, phân tích tình huống và xử lý hợp đồng
            trong một không gian làm việc có dẫn nguồn, kiểm tra hiệu lực và giải thích dễ hiểu.
          </p>

          <div className="lp-hero-actions">
            {authAvailable ? (
              <a className="lp-google-button" href={loginUrl}>
                <span className="lp-google-mark" aria-hidden="true">G</span>
                Tiếp tục với Google
                <ArrowRight size={17} />
              </a>
            ) : (
              <button className="lp-google-button" type="button" disabled>
                <span className="lp-google-mark" aria-hidden="true">G</span>
                Đăng nhập đang tạm gián đoạn
              </button>
            )}
            <a className="lp-secondary-link" href="#capabilities">
              Khám phá VLegal <ArrowRight size={15} />
            </a>
          </div>

          <div className="lp-hero-proof" aria-label="Cam kết của VLegal AI">
            <span><ShieldCheck size={15} /> Kiểm tra hiệu lực</span>
            <span><BookOpen size={15} /> Dẫn nguồn rõ ràng</span>
            <span><CheckCircle2 size={15} /> Không cần tạo mật khẩu</span>
          </div>
        </div>

        <div className="lp-product-scene" aria-label="Minh họa giao diện hỏi đáp của VLegal AI">
          <div className="lp-product-glow" aria-hidden="true" />
          <div className="lp-product-window">
            <header>
              <div className="lp-preview-brand">
                <span><Scale size={17} /></span>
                <div>
                  <strong>Trợ lý pháp lý</strong>
                  <small>Tự động đối chiếu căn cứ liên quan</small>
                </div>
              </div>
              <span className="lp-preview-status"><i /> Đang hoạt động</span>
            </header>

            <div className="lp-preview-body">
              <div className="lp-preview-question">
                Người lao động có quyền từ chối công việc khi thấy nguy cơ mất an toàn không?
              </div>
              <article className="lp-preview-answer">
                <div className="lp-preview-answer-mark"><Scale size={16} /></div>
                <div>
                  <span className="lp-preview-label"><SearchCheck size={13} /> Phân tích có căn cứ</span>
                  <p>
                    Có. Người lao động có quyền từ chối hoặc rời nơi làm việc khi thấy rõ
                    nguy cơ trực tiếp đe dọa tính mạng, sức khỏe.
                  </p>
                  <ul>
                    <li><Check size={13} /> Thông báo ngay cho người quản lý trực tiếp.</li>
                    <li><Check size={13} /> Không bị xem là vi phạm kỷ luật nếu nguy cơ là có căn cứ.</li>
                  </ul>
                </div>
              </article>
              <div className="lp-preview-source">
                <span><BookOpen size={14} /><strong>[S1]</strong> Bộ luật Lao động 2019</span>
                <span><ShieldCheck size={13} /> Còn hiệu lực</span>
              </div>
            </div>

            <footer>
              <span>Hỏi tiếp về tình huống của bạn…</span>
              <i aria-hidden="true"><ArrowRight size={17} /></i>
            </footer>
          </div>

          <div className="lp-floating-card lp-floating-source">
            <ShieldCheck size={17} />
            <span><strong>Nguồn có thể kiểm tra</strong>Căn cứ hiển thị ngay trong câu trả lời</span>
          </div>
          <div className="lp-floating-card lp-floating-status">
            <i aria-hidden="true" />
            <span><strong>Đã đối chiếu</strong>Hiệu lực văn bản</span>
          </div>
        </div>
      </section>

      <section className="lp-metrics" aria-label="Các tiêu chuẩn của VLegal AI">
        <article>
          <strong>01</strong>
          <span>Không trả lời mơ hồ</span>
          <p>Nêu rõ điều biết được và phần dữ liệu chưa có sẵn.</p>
        </article>
        <article>
          <strong>02</strong>
          <span>Nguồn đi cùng nhận định</span>
          <p>Giúp bạn tự đọc lại văn bản và kiểm tra kết luận.</p>
        </article>
        <article>
          <strong>03</strong>
          <span>Thiết kế cho pháp luật Việt Nam</span>
          <p>Tập trung vào ngữ cảnh, thuật ngữ và hệ thống văn bản Việt Nam.</p>
        </article>
      </section>

      <section className="lp-capabilities" id="capabilities" aria-labelledby="lp-capabilities-title">
        <header className="lp-section-heading">
          <p>Một không gian pháp lý hợp nhất</p>
          <h2 id="lp-capabilities-title">Từ câu hỏi đầu tiên đến quyết định cuối cùng.</h2>
          <span>
            Tra cứu, soạn thảo và rà soát trong cùng một trải nghiệm nhất quán,
            không cần chuyển qua nhiều công cụ rời rạc.
          </span>
        </header>

        <div className="lp-capability-grid">
          {capabilities.map(({ icon: Icon, number, title, description, accent }) => (
            <article key={title}>
              <div className="lp-capability-top">
                <span className="lp-capability-icon"><Icon size={20} /></span>
                <small>{number}</small>
              </div>
              <span className="lp-capability-accent">{accent}</span>
              <h3>{title}</h3>
              <p>{description}</p>
              <i aria-hidden="true"><ArrowRight size={16} /></i>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-workflow" id="workflow" aria-labelledby="lp-workflow-title">
        <div className="lp-workflow-copy">
          <p>Đơn giản từ đầu đến cuối</p>
          <h2 id="lp-workflow-title">Bạn hỏi như cách bạn vẫn nói.</h2>
          <span>
            Không cần biết trước số điều luật. VLegal giúp làm rõ câu hỏi,
            tìm căn cứ phù hợp và trình bày lại thành hướng xử lý có thể hành động.
          </span>
        </div>
        <ol className="lp-workflow-list">
          {workingSteps.map((step) => (
            <li key={step.number}>
              <span>{step.number}</span>
              <div><strong>{step.title}</strong><p>{step.description}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="lp-trust" id="trust">
        <div className="lp-trust-mark" aria-hidden="true"><Scale size={28} /></div>
        <p>AI hỗ trợ phân tích. Quyết định vẫn nằm trong tay bạn.</p>
        <h2>Câu trả lời tốt không chỉ nhanh — mà còn phải kiểm tra được.</h2>
        <div className="lp-trust-points">
          <span><CheckCircle2 size={16} /> Đối chiếu tình trạng hiệu lực</span>
          <span><CheckCircle2 size={16} /> Trích dẫn nguồn đã sử dụng</span>
          <span><CheckCircle2 size={16} /> Bảo vệ dữ liệu người dùng</span>
        </div>
        {authAvailable && (
          <a className="lp-trust-cta" href={loginUrl}>
            Bắt đầu với Google <ArrowRight size={17} />
          </a>
        )}
      </section>

      <footer className="lp-footer">
        <a className="lp-brand" href="#top" aria-label="VLegal AI — Về đầu trang">
          <span className="lp-brand-mark" aria-hidden="true"><Scale size={18} /></span>
          <span><strong>VLegal</strong><small>Trợ lý pháp lý AI</small></span>
        </a>
        <p>Kết quả do AI hỗ trợ không thay thế ý kiến tư vấn chuyên môn.</p>
        <span>© 2026 VLegal AI</span>
      </footer>
    </main>
  );
}
