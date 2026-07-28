import { BookOpen, Check, Scale, ShieldCheck } from "lucide-react";

type LandingPageProps = {
  authAvailable: boolean;
  loginUrl: string;
};

export default function LandingPage({ authAvailable, loginUrl }: LandingPageProps) {
  return (
    <main className="landing-page">
      <header className="landing-nav" aria-label="Giới thiệu VLegal AI">
        <div className="landing-brand">
          <span className="landing-brand-mark" aria-hidden="true"><Scale size={22} /></span>
          <span>VLegal AI</span>
        </div>
        <div className="landing-nav-note">Trợ lý pháp lý Việt Nam</div>
      </header>

      <section className="landing-hero">
        <div className="landing-hero-copy">
          <p className="landing-eyebrow">Căn cứ rõ ràng · Diễn giải dễ hiểu</p>
          <h1>Hiểu luật.<br />Biết mình <em>nên làm gì.</em></h1>
          <p className="landing-intro">
            Trợ lý pháp lý Việt Nam có căn cứ, kiểm tra hiệu lực và giải thích
            bằng ngôn ngữ dễ hiểu.
          </p>

          <div className="landing-actions">
            {authAvailable ? (
              <a className="landing-google-button" href={loginUrl}>
                <span className="landing-google-mark" aria-hidden="true">G</span>
                Đăng nhập bằng Google
              </a>
            ) : (
              <button className="landing-google-button" type="button" disabled>
                <span className="landing-google-mark" aria-hidden="true">G</span>
                Đăng nhập đang tạm gián đoạn
              </button>
            )}
            <div className="landing-trust-line">
              <span aria-hidden="true"><Check size={13} /></span>
              <span>Đăng nhập an toàn qua Google, không cần tạo mật khẩu mới.</span>
            </div>
          </div>

          <ol className="landing-steps" aria-label="Ba bước bắt đầu">
            <li>Đăng nhập</li>
            <li>Chọn tên gọi</li>
            <li>Bắt đầu trò chuyện</li>
          </ol>
        </div>

        <div className="landing-desk-scene" aria-hidden="true">
          <div className="landing-green-field" />
          <div className="landing-paper-shadow" />
          <div className="landing-document">
            <span className="landing-doc-kicker">Bản giải thích pháp lý</span>
            <strong className="landing-doc-title">Từ điều luật<br />đến việc cần làm.</strong>
            <span className="landing-doc-rule" />
            <span className="landing-doc-line" />
            <span className="landing-doc-line medium" />
            <span className="landing-doc-line" />
            <span className="landing-doc-line short" />
            <span className="landing-doc-line" />
            <span className="landing-doc-note">
              <Check size={13} />
              Căn cứ được kiểm tra hiệu lực trước khi trả lời.
            </span>
          </div>
          <div className="landing-folio">
            <span>VLegal AI · 2026</span>
            <strong>Hiểu đúng căn cứ.<br />Chọn đúng bước đi.</strong>
          </div>
        </div>
      </section>

      <section className="landing-support" aria-labelledby="landing-support-title">
        <div className="landing-support-heading">
          <p>Đồng hành có căn cứ</p>
          <h2 id="landing-support-title">
            Một câu trả lời pháp lý nên giúp bạn tiến về phía trước.
          </h2>
        </div>
        <div className="landing-principles">
          <article>
            <BookOpen size={19} />
            <strong>Dẫn nguồn</strong>
            <p>Biết câu trả lời dựa trên văn bản và điều khoản nào.</p>
          </article>
          <article>
            <ShieldCheck size={19} />
            <strong>Kiểm tra hiệu lực</strong>
            <p>Ưu tiên căn cứ còn giá trị tại thời điểm bạn tra cứu.</p>
          </article>
          <article>
            <Check size={19} />
            <strong>Dễ hành động</strong>
            <p>Diễn giải rõ ràng để bạn hiểu bước tiếp theo cần làm.</p>
          </article>
        </div>
      </section>
    </main>
  );
}
