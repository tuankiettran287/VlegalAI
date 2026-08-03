import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ClipboardCheck,
  FileDiff,
  FilePenLine,
  FileSearch,
  ImagePlus,
  LogIn,
  MessageSquareText,
  MousePointerClick,
  Scale,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";

import { GoogleAction, GoogleMark } from "./LandingPage";

type GuidePageProps = {
  authAvailable: boolean;
  loginUrl: string;
  authenticated: boolean;
};

export default function GuidePage({
  authAvailable,
  loginUrl,
  authenticated,
}: GuidePageProps) {
  return (
    <main className="lp-page lp-guide-page">
      <header className="lp-nav" aria-label="Điều hướng hướng dẫn VLegal AI">
        <div className="lp-nav-inner">
          <a className="lp-brand" href="/" aria-label="VLegal AI — Trang đầu">
            <span className="lp-brand-mark" aria-hidden="true"><Scale size={21} /></span>
            <span><strong>VLegal</strong><small>Legal intelligence</small></span>
          </a>

          <nav className="lp-nav-links" aria-label="Mục lục hướng dẫn">
            <a href="#guide-login">Đăng nhập</a>
            <a href="#guide-ask">Đặt câu hỏi</a>
            <a href="#guide-read">Kiểm tra nguồn</a>
            <a href="#guide-contract">Hợp đồng</a>
          </nav>

          <div className="lp-guide-nav-actions">
            <a className="lp-back-link" href="/"><ArrowLeft size={15} /> Trang chủ</a>
            {authenticated ? (
              <a className="lp-login compact" href="/">Mở ứng dụng <ArrowRight size={15} /></a>
            ) : (
              <GoogleAction authAvailable={authAvailable} loginUrl={loginUrl} compact />
            )}
          </div>
        </div>
      </header>

      <section className="lp-guide-hero" aria-labelledby="lp-guide-title">
        <p><BookOpen size={15} /> Trung tâm hướng dẫn</p>
        <h1 id="lp-guide-title">Bắt đầu với VLegal.</h1>
        <span>
          Bốn bước ngắn từ đăng nhập đến kiểm tra căn cứ và làm việc với hợp đồng.
          Không cần cài đặt hoặc tạo thêm mật khẩu.
        </span>
      </section>

      <section className="lp-guide lp-guide-standalone" aria-label="Hướng dẫn sử dụng VLegal">
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
                <h2>Bắt đầu bằng tài khoản Google.</h2>
                <p>Chọn <strong>Tiếp tục với Google</strong>. Ở lần đăng nhập đầu tiên, nhập tên hoặc biệt danh bạn muốn VLegal sử dụng khi trò chuyện.</p>
                <ul>
                  <li><Check size={14} /> Không cần tạo hoặc ghi nhớ mật khẩu mới.</li>
                  <li><Check size={14} /> Lịch sử hội thoại và tài liệu được gắn với tài khoản của bạn.</li>
                </ul>
              </div>
              <div className="lp-guide-visual login-visual">
                <GoogleMark /><strong>Tiếp tục với Google</strong><ArrowRight size={16} />
              </div>
            </article>

            <article id="guide-ask">
              <div className="lp-guide-number">02</div>
              <div className="lp-guide-copy">
                <p className="lp-guide-kicker"><MessageSquareText size={14} /> Hỏi và đính kèm</p>
                <h2>Mô tả đủ bối cảnh, không cần nói như luật sư.</h2>
                <p>Nêu vai trò, sự việc, mốc thời gian và điều bạn muốn biết. Dùng nút <strong>+</strong> để tải ảnh hoặc tài liệu; bạn cũng có thể dán ảnh trực tiếp bằng <strong>Ctrl + V</strong>.</p>
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
                <h2>Đừng chỉ đọc kết luận — hãy mở căn cứ.</h2>
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
                <h2>Chọn đúng công cụ cho tài liệu của bạn.</h2>
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
    </main>
  );
}
