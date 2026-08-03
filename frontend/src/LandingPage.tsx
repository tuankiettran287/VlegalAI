import {
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileDiff,
  FilePenLine,
  MessageSquareText,
  Play,
  Scale,
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

export function GoogleMark() {
  return (
    <span className="lp-google-mark" aria-hidden="true">
      <svg viewBox="0 0 18 18" role="presentation">
        <path fill="#4285F4" d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.258h2.909c1.702-1.567 2.683-3.878 2.683-6.614Z" />
        <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.181l-2.909-2.258c-.806.54-1.835.859-3.047.859-2.344 0-4.328-1.585-5.037-3.714H.956v2.332A8.999 8.999 0 0 0 9 18Z" />
        <path fill="#FBBC05" d="M3.963 10.706A5.41 5.41 0 0 1 3.681 9c0-.592.102-1.168.282-1.706V4.962H.956A9.003 9.003 0 0 0 0 9c0 1.45.347 2.824.956 4.038l3.007-2.332Z" />
        <path fill="#EA4335" d="M9 3.58c1.322 0 2.508.454 3.441 1.345l2.582-2.582C13.463.891 11.427 0 9 0A8.999 8.999 0 0 0 .956 4.962l3.007 2.332C4.672 5.165 6.656 3.58 9 3.58Z" />
      </svg>
    </span>
  );
}

export function GoogleAction({ authAvailable, loginUrl, compact = false }: LandingPageProps & { compact?: boolean }) {
  if (!authAvailable) {
    return (
      <button className={compact ? "lp-login compact" : "lp-login"} type="button" disabled>
        <GoogleMark />
        Đăng nhập tạm gián đoạn
      </button>
    );
  }

  return (
    <a className={compact ? "lp-login compact" : "lp-login"} href={loginUrl}>
      <GoogleMark />
      {compact ? "Đăng nhập" : "Tiếp tục với Google"}
      <ArrowRight size={compact ? 15 : 17} />
    </a>
  );
}

export default function LandingPage({ authAvailable, loginUrl }: LandingPageProps) {
  return (
    <main className="lp-page">
      <header className="lp-nav" aria-label="Điều hướng VLegal AI">
        <div className="lp-nav-inner">
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
        </div>
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

        <div className="lp-hero-media" id="demo" aria-labelledby="lp-hero-video-title">
          <div className="lp-hero-video-card">
            <div className="lp-hero-video-header">
              <span><i /> Hướng dẫn sử dụng VLegal</span>
              <small>30 giây</small>
            </div>
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
            <div className="lp-hero-video-footer">
              <span><Video size={15} /><strong id="lp-hero-video-title">Xem cách đặt câu hỏi và kiểm tra căn cứ</strong></span>
              <a href="/huong-dan">Hướng dẫn đầy đủ <ArrowRight size={15} /></a>
            </div>
          </div>
          <span className="lp-hero-video-note"><CheckCircle2 size={15} /> Không cần cài đặt · bắt đầu ngay trên trình duyệt</span>
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
    </main>
  );
}
