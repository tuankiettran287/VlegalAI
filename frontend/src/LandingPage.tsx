import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  FileDiff,
  FilePenLine,
  MessageSquareText,
  Paperclip,
  Play,
  Scale,
  ShieldCheck,
  Sparkles,
  Video,
} from "lucide-react";

export type LandingPageProps = {
  authAvailable: boolean;
  loginUrl: string;
};

const capabilities = [
  {
    icon: MessageSquareText,
    number: "01",
    title: "Hỏi đáp có căn cứ",
    description: "Phân tích tình huống bằng ngôn ngữ dễ hiểu và cho biết nguồn nào được dùng cho từng nhận định.",
    accent: "Tra cứu",
  },
  {
    icon: FilePenLine,
    number: "02",
    title: "Tạo hợp đồng",
    description: "Biến yêu cầu kinh doanh thành bản nháp có cấu trúc để tiếp tục hiệu chỉnh và thương lượng.",
    accent: "Soạn thảo",
  },
  {
    icon: ClipboardCheck,
    number: "03",
    title: "Review rủi ro",
    description: "Tìm điều khoản bất lợi, điểm còn thiếu và gợi ý nội dung cần làm rõ trước khi ký.",
    accent: "Rà soát",
  },
  {
    icon: FileDiff,
    number: "04",
    title: "So sánh phiên bản",
    description: "Nhận ra nội dung thêm, xóa, chỉnh sửa cùng tác động đáng chú ý giữa hai văn bản.",
    accent: "Đối chiếu",
  },
];

const trustPoints = [
  "Dẫn nguồn ngay trong câu trả lời",
  "Đối chiếu tình trạng hiệu lực",
  "Cho phép đánh giá và tạo lại kết quả",
];

export function GoogleAction({ authAvailable, loginUrl, compact = false }: LandingPageProps & { compact?: boolean }) {
  if (!authAvailable) {
    return (
      <button className={compact ? "lp-login compact" : "lp-login"} type="button" disabled>
        <span className="lp-google-mark" aria-hidden="true">G</span>
        Đăng nhập tạm gián đoạn
      </button>
    );
  }

  return (
    <a className={compact ? "lp-login compact" : "lp-login"} href={loginUrl}>
      <span className="lp-google-mark" aria-hidden="true">G</span>
      {compact ? "Đăng nhập" : "Tiếp tục với Google"}
      <ArrowRight size={compact ? 15 : 17} />
    </a>
  );
}

export default function LandingPage({ authAvailable, loginUrl }: LandingPageProps) {
  return (
    <main className="lp-page">
      <header className="lp-nav" aria-label="Điều hướng VLegal AI">
        <a className="lp-brand" href="#top" aria-label="VLegal AI — Trang đầu">
          <span className="lp-brand-mark" aria-hidden="true"><Scale size={21} /></span>
          <span><strong>VLegal</strong><small>Legal intelligence</small></span>
        </a>

        <nav className="lp-nav-links" aria-label="Nội dung trang">
          <a href="#demo">Video hướng dẫn</a>
          <a href="#capabilities">Tính năng</a>
          <a href="/huong-dan">Hướng dẫn chi tiết</a>
        </nav>

        <GoogleAction authAvailable={authAvailable} loginUrl={loginUrl} compact />
      </header>

      <section className="lp-hero" id="top">
        <div className="lp-hero-copy">
          <p className="lp-eyebrow"><Sparkles size={15} /> Trợ lý pháp lý dành cho Việt Nam</p>
          <h1>
            Hiểu đúng quy định.
            <span>Vững vàng quyết định.</span>
          </h1>
          <p className="lp-hero-intro">
            Hỏi đáp pháp luật, kiểm tra hợp đồng và đối chiếu căn cứ trong một không gian làm việc
            được thiết kế để bạn hiểu điều gì đang áp dụng — và nên làm gì tiếp theo.
          </p>

          <div className="lp-hero-actions">
            <GoogleAction authAvailable={authAvailable} loginUrl={loginUrl} />
            <a className="lp-watch-link" href="#demo">
              <span><Play size={15} fill="currentColor" /></span>
              Xem hướng dẫn 30 giây
            </a>
          </div>

          <div className="lp-hero-proof" aria-label="Cam kết của VLegal AI">
            {trustPoints.map((point) => <span key={point}><CheckCircle2 size={15} /> {point}</span>)}
          </div>
        </div>

        <div className="lp-product-stage" aria-label="Minh họa không gian hỏi đáp VLegal">
          <div className="lp-stage-orbit orbit-one" aria-hidden="true" />
          <div className="lp-stage-orbit orbit-two" aria-hidden="true" />
          <div className="lp-product-window">
            <header>
              <div className="lp-window-brand"><Scale size={17} /><strong>Trợ lý pháp lý</strong></div>
              <span><i /> Đối chiếu căn cứ tự động</span>
            </header>
            <div className="lp-window-body">
              <div className="lp-window-greeting">
                <small>LEGAL INTELLIGENCE</small>
                <strong>Xin chào, bạn cần hỗ trợ điều gì?</strong>
              </div>
              <div className="lp-window-composer">
                <span>Hỏi VLegal về tình huống pháp lý của bạn…</span>
                <footer><i><Paperclip size={13} /></i><button type="button" tabIndex={-1} aria-hidden="true"><ArrowRight size={15} /></button></footer>
              </div>
              <div className="lp-window-prompt-row">
                <span>Lao động</span><span>Tiền lương</span><span>Hợp đồng</span>
              </div>
            </div>
          </div>
          <div className="lp-stage-card lp-stage-source">
            <BookOpen size={17} /><span><strong>Nguồn rõ ràng</strong>Mở trực tiếp văn bản đã dùng</span>
          </div>
          <div className="lp-stage-card lp-stage-check">
            <ShieldCheck size={17} /><span><strong>Hiệu lực được kiểm tra</strong>Giảm rủi ro dùng căn cứ cũ</span>
          </div>
        </div>
      </section>

      <section className="lp-demo" id="demo" aria-labelledby="lp-demo-title">
        <header className="lp-section-heading lp-demo-heading">
          <div><p><Video size={14} /> Video hướng dẫn</p><h2 id="lp-demo-title">Làm quen với VLegal trong 30 giây.</h2></div>
          <span>Xem nhanh luồng đăng nhập, đặt câu hỏi, đính kèm tài liệu và kiểm tra căn cứ.</span>
        </header>

        <div className="lp-demo-shell">
          <div className="lp-video-frame">
            <div className="lp-video-toolbar"><span><i /> VLegal walkthrough</span><small>00:30</small></div>
            <video
              controls
              playsInline
              preload="metadata"
              poster="/vlegal-guide-poster.jpg"
              aria-label="Video hướng dẫn sử dụng VLegal AI"
            >
              <source src="/vlegal-guide.mp4" type="video/mp4" />
              <track kind="captions" src="/vlegal-guide.vi.vtt" srcLang="vi" label="Tiếng Việt" default />
              Trình duyệt của bạn chưa hỗ trợ phát video.
            </video>
          </div>

          <aside className="lp-video-summary" aria-label="Bắt đầu nhanh với VLegal">
            <small>BẮT ĐẦU NHANH</small>
            <h3>Video đủ để bạn bắt đầu trong 30 giây.</h3>
            <span><CheckCircle2 size={16} /> Đăng nhập bằng Google</span>
            <span><CheckCircle2 size={16} /> Hỏi hoặc tải tài liệu lên</span>
            <span><CheckCircle2 size={16} /> Mở căn cứ để kiểm tra</span>
            <a href="/huong-dan">Đọc hướng dẫn đầy đủ <ArrowRight size={16} /></a>
          </aside>
        </div>
      </section>

      <section className="lp-capabilities" id="capabilities" aria-labelledby="lp-capabilities-title">
        <header className="lp-section-heading">
          <div><p><Sparkles size={14} /> Một không gian hợp nhất</p><h2 id="lp-capabilities-title">Đúng công cụ cho từng việc pháp lý.</h2></div>
          <span>Tra cứu, soạn thảo và rà soát trong cùng một trải nghiệm nhất quán.</span>
        </header>
        <div className="lp-capability-grid">
          {capabilities.map(({ icon: Icon, number, title, description, accent }) => (
            <article key={title}>
              <div className="lp-capability-top"><span><Icon size={20} /></span><small>{number}</small></div>
              <p>{accent}</p><h3>{title}</h3><span>{description}</span><i><ArrowRight size={16} /></i>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-final-cta">
        <span className="lp-final-mark"><Scale size={25} /></span>
        <p>Bắt đầu với câu hỏi của bạn</p>
        <h2>Một quyết định vững vàng bắt đầu từ căn cứ rõ ràng.</h2>
        <GoogleAction authAvailable={authAvailable} loginUrl={loginUrl} />
      </section>

      <footer className="lp-footer">
        <a className="lp-brand" href="#top" aria-label="VLegal AI — Về đầu trang">
          <span className="lp-brand-mark"><Scale size={18} /></span>
          <span><strong>VLegal</strong><small>Legal intelligence</small></span>
        </a>
        <p>Kết quả do AI hỗ trợ không thay thế ý kiến tư vấn chuyên môn.</p>
        <span>© 2026 VLegal AI</span>
      </footer>
    </main>
  );
}
