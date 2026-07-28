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
    title: "Hỏi đáp pháp luật",
    description: "Nhận câu trả lời có căn cứ, diễn giải rõ và kiểm tra được nguồn.",
  },
  {
    icon: FilePenLine,
    title: "Soạn hợp đồng",
    description: "Tạo bản nháp hoặc hoàn thiện tài liệu sẵn có theo yêu cầu.",
  },
  {
    icon: ClipboardCheck,
    title: "Review rủi ro",
    description: "Nhận diện điều khoản bất lợi, thiếu sót và hướng chỉnh sửa.",
  },
  {
    icon: FileDiff,
    title: "So sánh phiên bản",
    description: "Làm rõ nội dung thêm, xóa, sửa và tác động pháp lý.",
  },
];

export default function LandingPage({ authAvailable, loginUrl }: LandingPageProps) {
  return (
    <main className="landing-page">
      <header className="landing-nav" aria-label="Giới thiệu VLegal AI">
        <div className="landing-brand">
          <span className="landing-brand-mark" aria-hidden="true"><Scale size={22} /></span>
          <span>
            <strong>VLegal AI</strong>
            <small>Legal intelligence workspace</small>
          </span>
        </div>
        <div className="landing-nav-actions">
          <span className="landing-nav-note"><ShieldCheck size={15} /> Căn cứ minh bạch</span>
          {authAvailable && (
            <a className="landing-nav-login" href={loginUrl}>
              Đăng nhập <ArrowRight size={16} />
            </a>
          )}
        </div>
      </header>

      <section className="landing-hero">
        <div className="landing-hero-copy">
          <p className="landing-eyebrow"><Sparkles size={15} /> Trợ lý pháp lý Việt Nam</p>
          <h1>Pháp lý rõ ràng.<br /><em>Quyết định vững vàng.</em></h1>
          <p className="landing-intro">
            Tra cứu, phân tích hợp đồng và xử lý tình huống pháp lý trong một
            không gian làm việc có dẫn nguồn, kiểm tra hiệu lực và giải thích dễ hiểu.
          </p>

          <div className="landing-actions">
            {authAvailable ? (
              <a className="landing-google-button" href={loginUrl}>
                <span className="landing-google-mark" aria-hidden="true">G</span>
                Tiếp tục với Google
                <ArrowRight size={17} />
              </a>
            ) : (
              <button className="landing-google-button" type="button" disabled>
                <span className="landing-google-mark" aria-hidden="true">G</span>
                Đăng nhập đang tạm gián đoạn
              </button>
            )}
            <p className="landing-trust-line">
              <CheckCircle2 size={17} />
              Không cần tạo mật khẩu mới
            </p>
          </div>

          <div className="landing-proof" aria-label="Cam kết của VLegal AI">
            <span><ShieldCheck size={15} /> Kiểm tra hiệu lực</span>
            <span><BookOpen size={15} /> Dẫn nguồn rõ ràng</span>
            <span><Check size={15} /> Dữ liệu được bảo vệ</span>
          </div>
        </div>

        <div className="landing-product-preview" aria-label="Minh họa câu trả lời của VLegal AI">
          <div className="preview-window">
            <header>
              <div className="preview-window-brand">
                <span><Scale size={17} /></span>
                <div><strong>Trợ lý pháp lý</strong><small>Đối chiếu căn cứ tự động</small></div>
              </div>
              <span className="preview-status"><i /> Sẵn sàng</span>
            </header>
            <div className="preview-content">
              <div className="preview-question">
                Người lao động có quyền từ chối công việc khi nhận thấy nguy cơ mất an toàn không?
              </div>
              <article className="preview-answer">
                <div className="preview-answer-icon"><Scale size={16} /></div>
                <div>
                  <span className="preview-answer-label">Phân tích có căn cứ</span>
                  <p>
                    Người lao động có quyền từ chối hoặc rời nơi làm việc khi thấy rõ
                    nguy cơ trực tiếp đe dọa tính mạng, sức khỏe.
                  </p>
                  <ul>
                    <li><Check size={13} /> Thông báo ngay cho người quản lý trực tiếp</li>
                    <li><Check size={13} /> Không bị xem là vi phạm kỷ luật trong trường hợp hợp lệ</li>
                  </ul>
                  <div className="preview-source">
                    <BookOpen size={14} />
                    <span><strong>[S1]</strong> Bộ luật Lao động 2019</span>
                    <span className="preview-verified"><ShieldCheck size={13} /> Còn hiệu lực</span>
                  </div>
                </div>
              </article>
            </div>
            <footer>
              <span>Hỏi tiếp về tình huống của bạn…</span>
              <span className="preview-send" aria-hidden="true">
                <ArrowRight size={17} />
              </span>
            </footer>
          </div>
          <div className="preview-note">
            <ShieldCheck size={17} />
            <span><strong>Minh bạch ngay từ câu trả lời</strong> Luôn hiển thị căn cứ đã sử dụng.</span>
          </div>
        </div>
      </section>

      <section className="landing-capabilities" aria-labelledby="landing-capabilities-title">
        <header>
          <p>Không gian pháp lý hợp nhất</p>
          <h2 id="landing-capabilities-title">Từ câu hỏi đến tài liệu hoàn chỉnh.</h2>
        </header>
        <div className="landing-capability-grid">
          {capabilities.map(({ icon: Icon, title, description }, index) => (
            <article key={title}>
              <div className="landing-capability-head">
                <span><Icon size={19} /></span>
                <small>0{index + 1}</small>
              </div>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-support" aria-labelledby="landing-support-title">
        <div className="landing-support-heading">
          <p>Thiết kế để bạn an tâm kiểm tra</p>
          <h2 id="landing-support-title">AI hỗ trợ phân tích. Quyết định vẫn nằm trong tay bạn.</h2>
        </div>
        <div className="landing-principles">
          <article>
            <BookOpen size={20} />
            <strong>Nguồn có thể kiểm tra</strong>
            <p>Mỗi nhận định quan trọng đi cùng văn bản và điều khoản liên quan.</p>
          </article>
          <article>
            <ShieldCheck size={20} />
            <strong>Hiệu lực được đối chiếu</strong>
            <p>Ưu tiên căn cứ còn giá trị tại thời điểm bạn thực hiện tra cứu.</p>
          </article>
          <article>
            <CheckCircle2 size={20} />
            <strong>Hướng hành động rõ</strong>
            <p>Tóm tắt điểm cần lưu ý và gợi ý bước tiếp theo bằng ngôn ngữ dễ hiểu.</p>
          </article>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="landing-brand">
          <span className="landing-brand-mark" aria-hidden="true"><Scale size={18} /></span>
          <span><strong>VLegal AI</strong><small>Trợ lý pháp lý Việt Nam</small></span>
        </div>
        <p>Kết quả do AI hỗ trợ không thay thế ý kiến tư vấn chuyên môn.</p>
      </footer>
    </main>
  );
}
