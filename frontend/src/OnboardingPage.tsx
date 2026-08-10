import { FormEvent, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  MessageSquareText,
  Scale,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";

import type { User } from "./types";

type OnboardingPageProps = {
  user: User;
  onComplete: (preferredName: string) => Promise<void>;
};

export default function OnboardingPage({ user, onComplete }: OnboardingPageProps) {
  const [preferredName, setPreferredName] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const normalized = preferredName.trim().replace(/\s+/g, " ");
    if (!normalized) {
      setError("Hãy nhập tên hoặc biệt danh bạn muốn sử dụng.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onComplete(normalized);
    } catch (reason) {
      setError((reason as Error).message);
      setSaving(false);
    }
  };

  return (
    <main className="onboarding-page">
      <div className="onboarding-shell">
        <section className="onboarding-copy" aria-labelledby="onboarding-title">
          <div className="onboarding-brand">
            <span><Scale size={22} /></span>
            <div>
              <strong>VLegal</strong>
              <small>Legal Intelligence</small>
            </div>
          </div>

          <div className="onboarding-content">
            <p className="onboarding-step"><Sparkles size={14} /> Bước cuối trước khi bắt đầu</p>
            <h1 id="onboarding-title">Tôi nên gọi bạn là <em>gì?</em></h1>
            <p className="onboarding-intro">
              Nhập tên hoặc biệt danh bạn thấy thoải mái. VLegal sẽ dùng tên này để
              chào bạn trong những cuộc trò chuyện tiếp theo.
            </p>

            <form className="onboarding-form" onSubmit={submit}>
              <label htmlFor="preferred-name">Tên hoặc biệt danh</label>
              <div className="onboarding-input-row">
                <div className="onboarding-input-control">
                  <UserRound size={19} aria-hidden="true" />
                  <input
                    id="preferred-name"
                    name="preferred-name"
                    value={preferredName}
                    maxLength={60}
                    autoComplete="nickname"
                    autoFocus
                    placeholder="Ví dụ: Minh, An, Luật sư Mây…"
                    onChange={(event) => setPreferredName(event.target.value)}
                    aria-describedby={error ? "onboarding-error" : "onboarding-help"}
                  />
                  <span className="onboarding-count" aria-hidden="true">{preferredName.length}/60</span>
                </div>
                <button type="submit" disabled={saving || !preferredName.trim()}>
                  {saving ? "Đang lưu…" : "Tiếp tục"}
                  {!saving && <ArrowRight size={18} />}
                </button>
              </div>
              {error ? (
                <p className="onboarding-error" id="onboarding-error" role="alert">{error}</p>
              ) : (
                <p className="onboarding-help" id="onboarding-help">
                  Đây là tên VLegal sẽ dùng để trò chuyện với bạn.
                </p>
              )}
            </form>
          </div>

          <div className="onboarding-account">
            <span className="onboarding-avatar">
              {user.avatar_url
                ? <img src={user.avatar_url} alt="" />
                : user.display_name.charAt(0).toUpperCase()}
            </span>
            <span className="onboarding-account-copy">
              <strong>{user.display_name}</strong>
              <small>{user.email}</small>
            </span>
            <span className="onboarding-verified" title="Đã xác thực bằng Google">
              <ShieldCheck size={18} />
            </span>
          </div>
        </section>

        <aside className="onboarding-aside" aria-hidden="true">
          <div className="onboarding-orbit one" />
          <div className="onboarding-orbit two" />
          <div className="onboarding-aside-badge"><MessageSquareText size={17} /> Không gian của bạn</div>
          <div className="onboarding-quote">
            <span>CÁ NHÂN HÓA TRẢI NGHIỆM</span>
            <strong>Một cách xưng hô phù hợp giúp cuộc trao đổi tự nhiên hơn.</strong>
            <p>VLegal ghi nhớ tên bạn chọn và dùng tên đó khi bắt đầu cuộc trò chuyện mới.</p>
          </div>
          <div className="onboarding-benefits">
            <div><CheckCircle2 size={17} /><span><strong>Xưng hô tự nhiên</strong><small>Thân thiện trong từng câu trả lời</small></span></div>
            <div><ShieldCheck size={17} /><span><strong>Thông tin được bảo vệ</strong><small>Gắn với tài khoản Google của bạn</small></span></div>
          </div>
        </aside>
      </div>
    </main>
  );
}
