import { useRef } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ClipboardCheck,
  FileDiff,
  FilePenLine,
  FileSearch,
  ImagePlus,
  LogIn,
  MessageSquareText,
  MousePointerClick,
  Paperclip,
  Play,
  Scale,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  ThumbsUp,
  Upload,
  Video,
} from "lucide-react";

type LandingPageProps = {
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

const videoChapters = [
  { time: "00:00", seconds: 0, title: "Bắt đầu với VLegal", description: "Tổng quan không gian trợ lý pháp lý." },
  { time: "00:04", seconds: 4, title: "Đăng nhập Google", description: "Vào ứng dụng và đặt tên xưng hô." },
  { time: "00:09", seconds: 9, title: "Hỏi và đính kèm", description: "Nhập tình huống, dán ảnh hoặc tải tài liệu." },
  { time: "00:16", seconds: 16, title: "Kiểm tra căn cứ", description: "Đọc câu trả lời và mở nguồn pháp luật." },
  { time: "00:23", seconds: 23, title: "Công cụ hợp đồng", description: "Tạo, review và so sánh hợp đồng." },
];

const trustPoints = [
  "Dẫn nguồn ngay trong câu trả lời",
  "Đối chiếu tình trạng hiệu lực",
  "Cho phép đánh giá và tạo lại kết quả",
];

function GoogleAction({ authAvailable, loginUrl, compact = false }: LandingPageProps & { compact?: boolean }) {
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
  const videoRef = useRef<HTMLVideoElement>(null);

  const playChapter = (seconds: number) => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = seconds;
    void videoRef.current.play();
  };

  return (
    <main className="lp-page">
      <header className="lp-nav" aria-label="Điều hướng VLegal AI">
        <a className="lp-brand" href="#top" aria-label="VLegal AI — Trang đầu">
          <span className="lp-brand-mark" aria-hidden="true"><Scale size={21} /></span>
          <span><strong>VLegal</strong><small>Legal intelligence</small></span>
        </a>

        <nav className="lp-nav-links" aria-label="Nội dung trang">
          <a href="#demo">Video hướng dẫn</a>
          <a href="#guide">Cách sử dụng</a>
          <a href="#capabilities">Tính năng</a>
          <a href="#trust">Minh bạch</a>
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

      <section className="lp-signal" aria-label="Nguyên tắc trải nghiệm VLegal">
        <span>01</span><strong>Hỏi bằng ngôn ngữ tự nhiên</strong>
        <span>02</span><strong>Đính kèm ảnh và tài liệu</strong>
        <span>03</span><strong>Kiểm tra lại mọi căn cứ</strong>
      </section>

      <section className="lp-demo" id="demo" aria-labelledby="lp-demo-title">
        <header className="lp-section-heading lp-demo-heading">
          <div><p><Video size={14} /> Video hướng dẫn</p><h2 id="lp-demo-title">Làm quen với VLegal trong 30 giây.</h2></div>
          <span>
            Video được dựng trực tiếp từ luồng sử dụng của VLegal: đăng nhập, đặt câu hỏi,
            tải tài liệu, kiểm tra nguồn và dùng công cụ hợp đồng.
          </span>
        </header>

        <div className="lp-demo-shell">
          <div className="lp-video-frame">
            <div className="lp-video-toolbar"><span><i /> VLegal walkthrough</span><small>00:30</small></div>
            <video
              ref={videoRef}
              controls
              playsInline
              preload="metadata"
              poster="/vlegal-guide-poster.jpg"
              aria-label="Video hướng dẫn sử dụng VLegal AI"
            >
              <source src="/vlegal-guide.mp4" type="video/mp4" />
              <track kind="captions" src="/vlegal-guide.vi.vtt" srcLang="vi" label="Tiếng Việt" default />
              Trình duyệt của bạn chưa hỗ trợ phát video. Vui lòng xem phần hướng dẫn bên dưới.
            </video>
          </div>

          <div className="lp-video-chapters" aria-label="Các chương trong video">
            <div><small>NỘI DUNG VIDEO</small><strong>Chọn một bước để xem</strong></div>
            {videoChapters.map((chapter, index) => (
              <button type="button" key={chapter.time} onClick={() => playChapter(chapter.seconds)}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <span><strong>{chapter.title}</strong><small>{chapter.description}</small></span>
                <time>{chapter.time}</time>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-guide" id="guide" aria-labelledby="lp-guide-title">
        <header className="lp-section-heading">
          <div><p><BookOpen size={14} /> Tài liệu sử dụng</p><h2 id="lp-guide-title">Từ đăng nhập đến câu trả lời đầu tiên.</h2></div>
          <span>
            Hướng dẫn này đi cùng bạn qua toàn bộ luồng chính. Không cần cài đặt và không cần tạo thêm mật khẩu.
          </span>
        </header>

        <div className="lp-guide-layout">
          <aside className="lp-guide-index" aria-label="Mục lục hướng dẫn">
            <small>BẮT ĐẦU NHANH</small>
            <a href="#guide-login"><span>01</span> Đăng nhập và hồ sơ</a>
            <a href="#guide-ask"><span>02</span> Hỏi và đính kèm</a>
            <a href="#guide-read"><span>03</span> Đọc và kiểm tra</a>
            <a href="#guide-contract"><span>04</span> Làm việc với hợp đồng</a>
            <div className="lp-guide-index-note">
              <ShieldCheck size={17} />
              <span><strong>Lưu ý</strong>Không nhập thông tin bí mật không cần thiết cho việc phân tích.</span>
            </div>
          </aside>

          <div className="lp-guide-content">
            <article id="guide-login">
              <div className="lp-guide-number">01</div>
              <div className="lp-guide-copy">
                <p className="lp-guide-kicker"><LogIn size={14} /> Đăng nhập và hồ sơ</p>
                <h3>Bắt đầu bằng tài khoản Google.</h3>
                <p>Chọn <strong>Tiếp tục với Google</strong>. Ở lần đăng nhập đầu tiên, nhập tên hoặc biệt danh bạn muốn VLegal sử dụng khi trò chuyện.</p>
                <ul>
                  <li><Check size={14} /> Không cần tạo hoặc ghi nhớ mật khẩu mới.</li>
                  <li><Check size={14} /> Lịch sử hội thoại và tài liệu được gắn với tài khoản của bạn.</li>
                </ul>
              </div>
              <div className="lp-guide-visual login-visual">
                <span className="lp-google-mark">G</span><strong>Tiếp tục với Google</strong><ArrowRight size={16} />
              </div>
            </article>

            <article id="guide-ask">
              <div className="lp-guide-number">02</div>
              <div className="lp-guide-copy">
                <p className="lp-guide-kicker"><MessageSquareText size={14} /> Hỏi và đính kèm</p>
                <h3>Mô tả đủ bối cảnh, không cần nói như luật sư.</h3>
                <p>Nêu vai trò của bạn, sự việc đã xảy ra, mốc thời gian và điều bạn muốn biết. Dùng nút <strong>+</strong> để tải ảnh hoặc tài liệu; bạn cũng có thể dán ảnh trực tiếp bằng <strong>Ctrl + V</strong>.</p>
                <div className="lp-prompt-example">
                  <small>VÍ DỤ CẤU TRÚC CÂU HỎI</small>
                  <p>“Tôi là người lao động, công ty thông báo chấm dứt hợp đồng từ ngày… Tôi cần biết quyền lợi và các bước nên thực hiện.”</p>
                </div>
              </div>
              <div className="lp-guide-visual upload-visual">
                <span><ImagePlus size={18} /><strong>Ảnh</strong><small>JPEG · PNG · WebP</small></span>
                <span><Upload size={18} /><strong>Tài liệu</strong><small>PDF · DOCX · TXT · MD</small></span>
              </div>
            </article>

            <article id="guide-read">
              <div className="lp-guide-number">03</div>
              <div className="lp-guide-copy">
                <p className="lp-guide-kicker"><SearchCheck size={14} /> Đọc và kiểm tra</p>
                <h3>Đừng chỉ đọc kết luận — hãy mở căn cứ.</h3>
                <p>Các ký hiệu <strong>[S1], [S2]…</strong> nối nhận định với nguồn. Mở khối “Căn cứ được sử dụng” để xem văn bản, điều khoản và đường dẫn gốc.</p>
                <ul>
                  <li><Check size={14} /> Xem trạng thái hiệu lực và thời điểm kiểm tra.</li>
                  <li><Check size={14} /> Chọn Hữu ích hoặc Chưa tốt để cải thiện câu trả lời.</li>
                </ul>
              </div>
              <div className="lp-guide-visual source-visual">
                <span className="source-badge">S1</span>
                <span><strong>Bộ luật Lao động 2019</strong><small><ShieldCheck size={12} /> Còn hiệu lực</small></span>
                <MousePointerClick size={17} />
              </div>
            </article>

            <article id="guide-contract">
              <div className="lp-guide-number">04</div>
              <div className="lp-guide-copy">
                <p className="lp-guide-kicker"><FileSearch size={14} /> Công cụ hợp đồng</p>
                <h3>Chọn đúng công cụ cho tài liệu của bạn.</h3>
                <p><strong>Tạo hợp đồng</strong> cho bản nháp mới; <strong>Review hợp đồng</strong> để tìm rủi ro trong một bản; <strong>So sánh hợp đồng</strong> để đối chiếu hai phiên bản.</p>
                <p className="lp-guide-tip"><Sparkles size={14} /> Kết quả AI là điểm bắt đầu để rà soát, không thay thế tư vấn chuyên môn cho quyết định quan trọng.</p>
              </div>
              <div className="lp-guide-visual tools-visual">
                <span><FilePenLine size={17} /> Tạo</span>
                <span><ClipboardCheck size={17} /> Review</span>
                <span><FileDiff size={17} /> So sánh</span>
              </div>
            </article>
          </div>
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

      <section className="lp-trust" id="trust">
        <div className="lp-trust-copy">
          <p><ShieldCheck size={14} /> Minh bạch từ thiết kế</p>
          <h2>Câu trả lời tốt phải có thể kiểm tra lại.</h2>
          <span>VLegal cho bạn thấy căn cứ, trạng thái hiệu lực và cách phản hồi khi kết quả chưa đáp ứng nhu cầu.</span>
        </div>
        <div className="lp-trust-list">
          <span><BookOpen size={18} /><strong>Nguồn đi cùng nhận định</strong><small>Không tách căn cứ khỏi nội dung trả lời.</small></span>
          <span><ShieldCheck size={18} /><strong>Hiệu lực được đối chiếu</strong><small>Nêu rõ khi trạng thái chưa thể xác minh.</small></span>
          <span><ThumbsUp size={18} /><strong>Phản hồi có tác dụng</strong><small>Đánh giá giúp tạo lại và cải thiện kết quả.</small></span>
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
