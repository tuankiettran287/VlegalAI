import { FormEvent, useState } from "react";
import { ArrowRight, Scale, ShieldCheck } from "lucide-react";

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
      <section className="onboarding-copy" aria-labelledby="onboarding-title">
        <div className="onboarding-brand">
          <span><Scale size={22} /></span>
          VLegal AI
        </div>
        <p className="onboarding-step">Bước cuối trước khi bắt đầu</p>
        <h1 id="onboarding-title">Tôi nên gọi bạn là gì?</h1>
        <p className="onboarding-intro">
          Nhập tên hoặc biệt danh bạn thấy thoải mái. VLegal sẽ dùng tên này để
          chào bạn trong cuộc trò chuyện mới.
        </p>

        <form className="onboarding-form" onSubmit={submit}>
          <label htmlFor="preferred-name">Tên hoặc biệt danh</label>
          <div className="onboarding-input-row">
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
            <button type="submit" disabled={saving || !preferredName.trim()}>
              {saving ? "Đang lưu…" : "Bắt đầu trò chuyện"}
              {!saving && <ArrowRight size={17} />}
            </button>
          </div>
          {error ? (
            <p className="onboarding-error" id="onboarding-error" role="alert">{error}</p>
          ) : (
            <p className="onboarding-help" id="onboarding-help">Bạn có thể dùng tối đa 60 ký tự.</p>
          )}
        </form>

        <div className="onboarding-account">
          <span className="onboarding-avatar">
            {user.avatar_url
              ? <img src={user.avatar_url} alt="" />
              : user.display_name.charAt(0).toUpperCase()}
          </span>
          <span>
            <strong>Đã đăng nhập bằng Google</strong>
            <small>{user.email}</small>
          </span>
          <ShieldCheck size={18} />
        </div>
      </section>

      <aside className="onboarding-aside" aria-hidden="true">
        <div className="onboarding-orbit one" />
        <div className="onboarding-orbit two" />
        <div className="onboarding-quote">
          <span>VLegal ghi nhớ cách xưng hô,</span>
          <strong>để mỗi cuộc trao đổi bắt đầu tự nhiên hơn.</strong>
        </div>
      </aside>
    </main>
  );
}
