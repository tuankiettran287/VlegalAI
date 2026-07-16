import {
  FormEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  AlignLeft,
  Archive,
  ArrowLeft,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Clock3,
  Copy,
  ExternalLink,
  FileDiff,
  FilePenLine,
  FileText,
  FolderClock,
  History,
  Library,
  LogIn,
  LogOut,
  Menu,
  MessageSquareText,
  Moon,
  PenTool,
  Plus,
  RefreshCw,
  Scale,
  Search,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  Sun,
  Trash2,
  Upload,
  UserRound,
  X,
} from "lucide-react";
import {
  ApiError,
  articleApi,
  artifactApi,
  askLegalQuestion,
  authApi,
  compareContracts,
  conversationApi,
  draftContract,
  getTemplates,
  prepareSignature,
  reviewContract,
  sendFeedback,
  type CompareResponse,
  type DraftResponse,
  type ReviewResponse,
  type SignatureResponse,
} from "./api";
import { sampleQuestions, templateFallback } from "./data";
import type {
  Article,
  Artifact,
  ChatMessage,
  Conversation,
  Risk,
  Source,
  Template,
  User,
  VerificationReport,
  WebSource,
} from "./types";

const routes = [
  { path: "/", label: "Hỏi đáp pháp luật", icon: MessageSquareText },
  { path: "/tao-hop-dong", label: "Tạo hợp đồng", icon: FilePenLine },
  { path: "/review-hop-dong", label: "Review hợp đồng", icon: ClipboardCheck },
  { path: "/so-sanh-hop-dong", label: "So sánh hợp đồng", icon: FileDiff },
  { path: "/ky-van-ban", label: "Ký văn bản", icon: PenTool },
  { path: "/bai-viet", label: "Bài viết", icon: BookOpen },
  { path: "/thu-vien", label: "Lịch sử & tài liệu", icon: Library },
];

function uid() {
  return globalThis.crypto?.randomUUID?.() || String(Date.now() + Math.random());
}

const GUEST_CHAT_STORAGE_KEY = "vlegal-guest-chat-v1";

function readGuestMessages(): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(sessionStorage.getItem(GUEST_CHAT_STORAGE_KEY) || "[]") as ChatMessage[];
    return parsed
      .filter((item) => item && typeof item.id === "string" && typeof item.content === "string" && ["user", "assistant"].includes(item.role))
      .slice(-24);
  } catch {
    return [];
  }
}

function writeGuestMessages(messages: ChatMessage[]) {
  if (typeof window === "undefined") return;
  const completed = messages.filter((item) => !item.pending).slice(-24);
  try {
    if (!completed.length) {
      sessionStorage.removeItem(GUEST_CHAT_STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(GUEST_CHAT_STORAGE_KEY, JSON.stringify(completed));
  } catch {
    const compact = completed.map(({ id, role, content, created_at }) => ({ id, role, content, created_at }));
    try {
      sessionStorage.setItem(GUEST_CHAT_STORAGE_KEY, JSON.stringify(compact));
    } catch {
      // Storage can be disabled by browser privacy settings; the in-memory chat still works.
    }
  }
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function markdown(value: string) {
  return escapeHtml(value || "")
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/^[-•] (.*)$/gm, "<div class='md-list-item'>• $1</div>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br />");
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function usePath() {
  const [path, setPath] = useState(() => window.location.pathname.replace(/\/$/, "") || "/");
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname.replace(/\/$/, "") || "/");
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const navigate = useCallback((nextPath: string) => {
    if (window.location.pathname.replace(/\/$/, "") === nextPath) return;
    window.history.pushState({}, "", nextPath);
    setPath(nextPath);
  }, []);
  return [path, navigate] as const;
}

async function readTextFile(file: File) {
  const text = await file.text();
  return text.slice(0, 120000);
}

function ErrorNotice({ error, onClose }: { error: string; onClose?: () => void }) {
  return (
    <div className="error-notice" role="alert">
      <ShieldCheck size={18} />
      <span>{error}</span>
      {onClose && (
        <button type="button" onClick={onClose} aria-label="Đóng thông báo">
          <X size={15} />
        </button>
      )}
    </div>
  );
}

function VerificationBadge({ report }: { report?: VerificationReport }) {
  if (!report) return null;
  const current = report.checked && report.all_current;
  return (
    <details className={`verification ${current ? "verified" : "attention"}`}>
      <summary>
        {current ? <CheckCircle2 size={15} /> : <RefreshCw size={15} />}
        <span>{current ? "Đã kiểm tra hiệu lực" : "Có văn bản cần lưu ý"}</span>
        {report.checked_at && <time>{formatDate(report.checked_at)}</time>}
        <ChevronDown size={14} />
      </summary>
      <div className="verification-body">
        <p>{report.note}</p>
        {report.items.map((item) => (
          <div className="law-status-row" key={`${item.code}-${item.checked_at}`}>
            <div>
              <strong>{item.code}</strong>
              <span>{item.title}</span>
            </div>
            <span className={`status-chip ${item.status.toLowerCase()}`}>{{
              IN_FORCE: "Còn hiệu lực",
              PARTIALLY_IN_FORCE: "Hiệu lực một phần",
              AMENDED: "Đã sửa đổi",
              EXPIRED: "Hết hiệu lực",
              REPLACED: "Đã thay thế",
              UNKNOWN: "Chưa rõ",
            }[item.status]}</span>
            {item.index_updated && <small>Đã cập nhật dữ liệu</small>}
            {item.source_url && (
              <a href={item.source_url} target="_blank" rel="noreferrer" aria-label={`Mở nguồn ${item.code}`}>
                <ExternalLink size={14} />
              </a>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

function SourcePanel({ sources }: { sources?: Source[] }) {
  if (!sources?.length) return null;
  return (
    <details className="source-panel">
      <summary>
        <FileText size={16} />
        <span>{sources.length} căn cứ được sử dụng</span>
        <ChevronDown size={16} />
      </summary>
      <div className="source-list">
        {sources.map((source) => (
          <article className="source-item" key={`${source.source_id}-${source.citation}`}>
            <div className="source-title">
              <span className="source-id">{source.source_id}</span>
              <strong>{source.citation || source.title}</strong>
              {source.source_url && (
                <a href={source.source_url} target="_blank" rel="noreferrer" aria-label="Mở nguồn chính thức">
                  <ExternalLink size={14} />
                </a>
              )}
            </div>
            <p>{source.text}</p>
          </article>
        ))}
      </div>
    </details>
  );
}

function ResultPanel({
  title,
  text,
  sources,
  verification,
  children,
}: {
  title: string;
  text: string;
  sources?: Source[];
  verification?: VerificationReport;
  children?: ReactNode;
}) {
  return (
    <section className="result-panel">
      <header className="result-header">
        <div>
          <span className="eyebrow">Kết quả AI</span>
          <h2>{title}</h2>
        </div>
        <button className="icon-button" type="button" onClick={() => navigator.clipboard?.writeText(text)} aria-label="Sao chép">
          <Copy size={17} />
        </button>
      </header>
      <VerificationBadge report={verification} />
      <div className="markdown" dangerouslySetInnerHTML={{ __html: markdown(text) }} />
      {children}
      <SourcePanel sources={sources} />
    </section>
  );
}

function PageHeader({ title, subtitle, action }: { title: string; subtitle: string; action?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">VLegal workspace</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </header>
  );
}

function DocumentInput({ title, value, onChange }: { title: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="document-input">
      <span>{title}</span>
      <textarea value={value} onChange={(event) => onChange(event.target.value)} placeholder={`Dán nội dung ${title.toLowerCase()}...`} />
      <div className="document-input-footer">
        <label className="ghost-button file-button">
          <Upload size={16} /> Tải .txt/.md
          <input
            type="file"
            accept=".txt,.md"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (file) onChange(await readTextFile(file));
            }}
          />
        </label>
        <span>{value.length.toLocaleString("vi-VN")} ký tự</span>
      </div>
    </label>
  );
}

function ChatPage({ user, authAvailable }: { user: User | null; authAvailable: boolean }) {
  const authenticated = Boolean(user);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(() => (authenticated ? [] : readGuestMessages()));
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [error, setError] = useState("");

  const reloadHistory = useCallback(() => {
    if (!authenticated) {
      setConversations([]);
      return;
    }
    conversationApi.list().then(setConversations).catch((reason) => setError((reason as Error).message));
  }, [authenticated]);

  useEffect(() => reloadHistory(), [reloadHistory]);
  useEffect(() => {
    if (!authenticated) writeGuestMessages(messages);
  }, [authenticated, messages]);

  const openConversation = async (id: string) => {
    if (!authenticated) return;
    setError("");
    const data = await conversationApi.get(id);
    setConversationId(id);
    setMessages(data.messages);
  };

  const newConversation = () => {
    setConversationId(null);
    setMessages([]);
    setInput("");
    if (!authenticated) sessionStorage.removeItem(GUEST_CHAT_STORAGE_KEY);
  };

  const submit = async (question = input) => {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setError("");
    setLoading(true);
    const userMessage: ChatMessage = { id: uid(), role: "user", content: trimmed };
    const pendingId = uid();
    setMessages((current) => [
      ...current,
      userMessage,
      { id: pendingId, role: "assistant", content: "Đang đối chiếu hiệu lực văn bản và xây dựng câu trả lời…", pending: true },
    ]);
    setInput("");
    try {
      const history = messages
        .filter((message) => !message.pending)
        .slice(-12)
        .map(({ role, content }) => ({ role, content: content.slice(0, 4000) }));
      const data = await askLegalQuestion(trimmed, authenticated ? conversationId : null, history);
      setConversationId(data.conversation_id || null);
      setMessages((current) =>
        current.map((message) =>
          message.id === pendingId
            ? {
                id: data.message_id,
                conversation_id: data.conversation_id || undefined,
                role: "assistant",
                content: data.answer,
                sources: data.sources,
                verification: data.verification,
              }
            : message,
        ),
      );
      if (authenticated) reloadHistory();
    } catch (reason) {
      const message = (reason as Error).message;
      setMessages((current) => current.filter((item) => item.id !== pendingId));
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className={historyOpen ? "chat-page" : "chat-page history-collapsed"}>
      <aside id="chat-history-panel" className={historyOpen ? "chat-history" : "chat-history hidden"}>
        <div className="history-head">
          <strong>{authenticated ? "Lịch sử hỏi đáp" : "Phiên trò chuyện tạm"}</strong>
          <button className="icon-button compact" type="button" onClick={newConversation} aria-label="Tạo cuộc trò chuyện">
            <Plus size={16} />
          </button>
        </div>
        <div className="conversation-list">
          {authenticated && conversations.map((item) => (
            <div className={item.id === conversationId ? "conversation-row active" : "conversation-row"} key={item.id}>
              <button type="button" onClick={() => openConversation(item.id)}>
                <MessageSquareText size={15} />
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.message_count} tin · {formatDate(item.updated_at)}</small>
                </span>
              </button>
              <button
                className="row-action"
                type="button"
                onClick={async () => {
                  await conversationApi.remove(item.id);
                  if (conversationId === item.id) newConversation();
                  reloadHistory();
                }}
                aria-label="Xóa cuộc trò chuyện"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {authenticated && !conversations.length && <p className="empty-copy">Các cuộc trò chuyện đã lưu sẽ xuất hiện tại đây.</p>}
          {!authenticated && (
            <div className="guest-session-card">
              <Clock3 size={18} />
              <strong>Phiên trò chuyện tạm</strong>
              <p>Nội dung chỉ được giữ trong tab hiện tại và sẽ tự xóa khi bạn kết thúc phiên.</p>
              {authAvailable && <a href={authApi.loginUrl("/")}><LogIn size={14} /> Đăng nhập để lưu lịch sử</a>}
            </div>
          )}
        </div>
      </aside>

      <div className="chat-main">
        <header className="chat-topbar">
          <button
            className="icon-button compact"
            type="button"
            onClick={() => setHistoryOpen((value) => !value)}
            aria-label={historyOpen ? "Ẩn lịch sử trò chuyện" : "Hiện lịch sử trò chuyện"}
            aria-controls="chat-history-panel"
            aria-expanded={historyOpen}
          >
            <History size={17} />
          </button>
          <div className="chat-title">
            <strong>Trợ lý pháp lý</strong>
            <span><ShieldCheck size={12} /> {authenticated ? "Tự động đối chiếu căn cứ liên quan" : "Đang dùng phiên trò chuyện tạm"}</span>
          </div>
          <div className="chat-topbar-actions">
            {!authenticated && authAvailable && <a className="google-login-inline" href={authApi.loginUrl("/")}><LogIn size={15} /> Đăng nhập Google</a>}
            <button className="ghost-button" type="button" onClick={newConversation}>
              <Plus size={16} /> Cuộc trò chuyện mới
            </button>
          </div>
        </header>

        <div className="chat-scroll">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-mark"><Scale size={30} /></div>
              <span className="eyebrow">Tra cứu pháp lý có kiểm chứng</span>
              <h1>Hiểu đúng quy định.<br />Ra quyết định tự tin hơn.</h1>
              <p>{authenticated ? "Mỗi câu trả lời được đối chiếu với căn cứ liên quan, kiểm tra hiệu lực và lưu lại để bạn tiếp tục xử lý sau." : "Bạn có thể bắt đầu ngay mà không cần đăng nhập. Nội dung hiện tại chỉ được giữ tạm trong trình duyệt."}</p>
              <div className="welcome-proof" aria-label="Cam kết chất lượng câu trả lời">
                <span><ShieldCheck size={15} /> Kiểm tra hiệu lực</span>
                <span><BookOpen size={15} /> Kèm căn cứ</span>
                <span><CheckCircle2 size={15} /> Áp dụng toàn bộ luật liên quan</span>
              </div>
              <div className="suggestion-grid">
                {sampleQuestions.map((question) => (
                  <button key={question} type="button" onClick={() => submit(question)}>
                    <Sparkles size={17} />
                    <span>{question}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages">
              {messages.map((message) => (
                <article className={`message ${message.role}`} key={message.id}>
                  {message.role === "assistant" && <div className="avatar"><Scale size={16} /></div>}
                  <div className="bubble">
                    <div dangerouslySetInnerHTML={{ __html: markdown(message.content) }} />
                    {message.pending && <div className="loading-line" />}
                    <VerificationBadge report={message.verification} />
                    <SourcePanel sources={message.sources} />
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
        {error && <div className="chat-error"><ErrorNotice error={error} onClose={() => setError("")} /></div>}
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <div className="policy-line"><CheckCircle2 size={14} /> Câu trả lời có căn cứ và được kiểm tra hiệu lực{!authenticated && " · phiên tạm thời"}</div>
          <div className="input-wrap">
            <textarea
              value={input}
              maxLength={5000}
              rows={1}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              placeholder="Nhập tình huống hoặc câu hỏi pháp lý…"
            />
            <span className="counter">{input.length}/5000</span>
            <button className="primary-icon" type="submit" disabled={!input.trim() || loading} aria-label="Gửi câu hỏi">
              <SendHorizontal size={18} />
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}

function ContractPage() {
  const [templates, setTemplates] = useState<Template[]>(templateFallback);
  const [selected, setSelected] = useState<Template>(templateFallback[0]);
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<DraftResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getTemplates().then((data) => {
      if (data.items.length) {
        setTemplates(data.items);
        setSelected(data.items[0]);
      }
    }).catch(() => undefined);
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!prompt.trim()) return;
    setLoading(true);
    setError("");
    try {
      setResult(await draftContract({ prompt, template_id: selected.id, template_name: selected.name }));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="tool-page">
      <PageHeader title="Tạo hợp đồng" subtitle="Tạo bản nháp theo yêu cầu, tự đối chiếu các quy định liên quan và kiểm tra hiệu lực trước khi hoàn thiện." />
      {error && <ErrorNotice error={error} onClose={() => setError("")} />}
      <div className="workspace-grid">
        <form className="workspace-card tool-form" onSubmit={submit}>
          <div className="section-title"><span>1</span><div><h2>Chọn loại hợp đồng</h2><p>Có thể đổi loại sau khi đã nhập yêu cầu.</p></div></div>
          <div className="template-grid-inline">
            {templates.map((item) => (
              <button key={item.id} className={selected.id === item.id ? "template-option active" : "template-option"} type="button" onClick={() => setSelected(item)}>
                <FileText size={17} /><span><strong>{item.name}</strong><small>{item.category}</small></span>
                {selected.id === item.id && <Check size={15} />}
              </button>
            ))}
          </div>
          <div className="section-title"><span>2</span><div><h2>Mô tả yêu cầu</h2><p>Nêu các bên, mục đích, giá trị, thời hạn và điều kiện đặc biệt.</p></div></div>
          <textarea className="large-textarea" value={prompt} onChange={(event) => setPrompt(event.target.value)} maxLength={30000} placeholder="Ví dụ: Soạn hợp đồng dịch vụ phát triển phần mềm giữa công ty A và công ty B, nghiệm thu theo 3 giai đoạn…" />
          <div className="form-footer">
            <span className="policy-line"><ShieldCheck size={14} /> Tự kiểm tra luật hiện hành</span>
            <button className="primary-button" type="submit" disabled={loading || prompt.trim().length < 8}>
              {loading ? <><RefreshCw className="spin" size={16} /> Đang soạn…</> : <><Sparkles size={16} /> Tạo bản nháp</>}
            </button>
          </div>
        </form>
        <ResultPanel
          title={result?.title || "Bản nháp sẽ xuất hiện tại đây"}
          text={result?.draft || "Mô tả yêu cầu càng cụ thể, bản nháp càng sát giao dịch. Kết quả được lưu tự động vào Thư viện tài liệu."}
          sources={result?.sources}
          verification={result?.verification}
        >
          {result?.checklist && (
            <div className="checklist-box"><h3>Checklist trước khi ký</h3>{result.checklist.map((item) => <p key={item}><CheckCircle2 size={15} />{item}</p>)}</div>
          )}
        </ResultPanel>
      </div>
    </section>
  );
}

function RiskList({ risks }: { risks?: Risk[] }) {
  if (!risks?.length) return null;
  return <div className="risk-list">{risks.map((risk, index) => (
    <article className={`risk-card ${risk.level}`} key={`${risk.title}-${index}`}>
      <span>{risk.level === "high" ? "Cao" : risk.level === "medium" ? "Trung bình" : "Thấp"}</span>
      <h3>{risk.title}</h3><p>{risk.detail}</p><strong>{risk.recommendation}</strong>
    </article>
  ))}</div>;
}

function ReviewPage() {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  return (
    <section className="tool-page">
      <PageHeader title="Review hợp đồng" subtitle="Phát hiện điều khoản bất lợi, thiếu sót và đề xuất cách sửa dựa trên căn cứ đang có hiệu lực." />
      {error && <ErrorNotice error={error} onClose={() => setError("")} />}
      <div className="workspace-grid">
        <form className="workspace-card tool-form" onSubmit={async (event) => {
          event.preventDefault(); setLoading(true); setError("");
          try { setResult(await reviewContract({ title: title || undefined, text })); }
          catch (reason) { setError((reason as Error).message); }
          finally { setLoading(false); }
        }}>
          <label className="field"><span>Tên tài liệu</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Hợp đồng dịch vụ 2026" /></label>
          <DocumentInput title="Nội dung hợp đồng" value={text} onChange={setText} />
          <button className="primary-button align-right" type="submit" disabled={loading || text.trim().length < 20}>
            {loading ? "Đang phân tích…" : "Phân tích hợp đồng"}
          </button>
        </form>
        <ResultPanel title="Kết quả review" text={result?.summary || "Kết quả tổng quan, danh sách rủi ro và khuyến nghị sẽ hiển thị tại đây."} sources={result?.sources} verification={result?.verification}>
          <RiskList risks={result?.risks} />
          {result?.recommendations?.length ? <div className="recommendations"><h3>Khuyến nghị</h3>{result.recommendations.map((item) => <p key={item}><Check size={15} />{item}</p>)}</div> : null}
        </ResultPanel>
      </div>
    </section>
  );
}

function ComparePage() {
  const [original, setOriginal] = useState("");
  const [revised, setRevised] = useState("");
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  return (
    <section className="tool-page">
      <PageHeader title="So sánh hợp đồng" subtitle="So sánh ngữ nghĩa, tác động pháp lý và rủi ro phát sinh giữa hai phiên bản." />
      {error && <ErrorNotice error={error} onClose={() => setError("")} />}
      <form className="compare-grid" onSubmit={async (event) => {
        event.preventDefault(); setLoading(true); setError("");
        try { setResult(await compareContracts({ original_text: original, revised_text: revised })); }
        catch (reason) { setError((reason as Error).message); }
        finally { setLoading(false); }
      }}>
        <DocumentInput title="Bản gốc" value={original} onChange={setOriginal} />
        <DocumentInput title="Bản sửa đổi" value={revised} onChange={setRevised} />
        <button className="primary-button compare-submit" type="submit" disabled={loading || original.length < 20 || revised.length < 20}>
          <FileDiff size={16} /> {loading ? "Đang so sánh…" : "So sánh hai phiên bản"}
        </button>
      </form>
      {result && <ResultPanel title={`Mức tương đồng ${result.similarity}%`} text={result.summary} sources={result.sources} verification={result.verification}>
        <div className="diff-list">{result.differences.map((item, index) => <article key={`${item.type}-${index}`}><span>{item.type}</span><div><small>Trước</small><p>{item.before}</p></div><div><small>Sau</small><p>{item.after}</p></div><strong>{item.legal_impact}</strong></article>)}</div>
        <RiskList risks={result.risks} />
      </ResultPanel>}
    </section>
  );
}

function SignaturePage() {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [signers, setSigners] = useState("");
  const [result, setResult] = useState<SignatureResponse | null>(null);
  const [error, setError] = useState("");
  return (
    <section className="tool-page">
      <PageHeader title="Ký văn bản" subtitle="Chuẩn bị gói ký, tạo dấu vân tay SHA-256 và lưu nhật ký nghiệp vụ trước khi chuyển sang nhà cung cấp chữ ký số." />
      {error && <ErrorNotice error={error} onClose={() => setError("")} />}
      <div className="workspace-grid">
        <form className="workspace-card tool-form" onSubmit={async (event) => {
          event.preventDefault(); setError("");
          try { setResult(await prepareSignature({ title, document_text: text, signers: signers.split("\n").filter(Boolean) })); }
          catch (reason) { setError((reason as Error).message); }
        }}>
          <label className="field"><span>Tên văn bản</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Biên bản thỏa thuận" /></label>
          <DocumentInput title="Văn bản cần ký" value={text} onChange={setText} />
          <label className="field"><span>Người ký — mỗi người một dòng</span><textarea value={signers} onChange={(event) => setSigners(event.target.value)} placeholder="Nguyễn Văn A&#10;Trần Thị B" /></label>
          <button className="primary-button align-right" type="submit" disabled={title.length < 2 || text.length < 5}><PenTool size={16} /> Tạo gói ký</button>
        </form>
        <section className="result-panel signature-result">
          <span className="eyebrow">Gói ký</span><h2>{result?.title || "Chưa tạo gói ký"}</h2>
          {result ? <><div className="hash-box"><small>SHA-256</small>{result.document_hash}</div><div className="signer-list">{result.signers.map((name) => <span key={name}><UserRound size={14} />{name}</span>)}</div><div className="timeline">{result.audit_log.map((item) => <div key={`${item.time}-${item.event}`}><Clock3 size={15} /><span><strong>{item.event}</strong><small>{item.actor} · {formatDate(item.time)}</small></span></div>)}</div></> : <p className="empty-copy">Nhập văn bản và danh sách người ký để tạo mã hồ sơ có thể theo dõi.</p>}
        </section>
      </div>
    </section>
  );
}

function ArticlesPage() {
  const [query, setQuery] = useState("");
  const [articles, setArticles] = useState<Article[]>([]);
  const [webSummary, setWebSummary] = useState("");
  const [webSources, setWebSources] = useState<WebSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback((value = "") => articleApi.list(value).then((data) => setArticles(data.items)).catch((reason) => setError((reason as Error).message)), []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <section className="tool-page articles-page">
      <PageHeader title="Bài viết & nghiên cứu" subtitle="Đọc nội dung đã biên tập hoặc tìm hiểu chủ đề pháp lý từ các nguồn công khai có dẫn chứng rõ ràng." />
      {error && <ErrorNotice error={error} onClose={() => setError("")} />}
      <form className="web-search-card" onSubmit={async (event) => {
        event.preventDefault(); if (!query.trim()) return; setLoading(true); setError("");
        try { const data = await articleApi.webSearch(query); setWebSummary(data.summary); setWebSources(data.sources); load(query); }
        catch (reason) { setError((reason as Error).message); }
        finally { setLoading(false); }
      }}>
        <Search size={20} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm chủ đề pháp lý trên web…" />
        <button className="primary-button" type="submit" disabled={loading || query.length < 2}>{loading ? "Đang tìm…" : "Tìm trên web"}</button>
      </form>
      {webSummary && <section className="research-result"><span className="eyebrow">Tổng hợp từ internet</span><div className="markdown" dangerouslySetInnerHTML={{ __html: markdown(webSummary) }} /><div className="web-source-grid">{webSources.map((source) => <a key={source.id} href={source.url} target="_blank" rel="noreferrer"><span>{source.id}</span><strong>{source.title}</strong><ExternalLink size={14} /></a>)}</div></section>}
      <div className="article-list">{articles.map((article) => <article className="article-card" key={article.id}><div className="article-icon"><BookOpen size={23} /><span>{article.category}</span></div><div><small>{formatDate(article.published_at || article.created_at)} · {article.views} lượt xem</small><h2>{article.title}</h2><p>{article.excerpt}</p>{article.source_url && <a href={article.source_url} target="_blank" rel="noreferrer">Nguồn tham khảo <ExternalLink size={13} /></a>}</div></article>)}{!articles.length && <div className="empty-state"><BookOpen size={28} /><h3>Chưa có bài viết</h3><p>Hãy tìm một chủ đề trên web để bắt đầu nghiên cứu.</p></div>}</div>
    </section>
  );
}

function LibraryPage() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [tab, setTab] = useState<"documents" | "chats">("documents");
  const reload = useCallback(() => Promise.all([artifactApi.list().then(setArtifacts), conversationApi.list().then(setConversations)]), []);
  useEffect(() => { reload().catch(() => undefined); }, [reload]);
  return (
    <section className="tool-page library-page">
      <PageHeader title="Lịch sử & tài liệu" subtitle="Quản lý toàn bộ cuộc trò chuyện, bản nháp, kết quả review và so sánh đã được lưu an toàn." />
      <div className="tab-bar"><button className={tab === "documents" ? "active" : ""} onClick={() => setTab("documents")}><FileText size={16} />Tài liệu ({artifacts.length})</button><button className={tab === "chats" ? "active" : ""} onClick={() => setTab("chats")}><MessageSquareText size={16} />Hỏi đáp ({conversations.length})</button></div>
      <div className="library-list">
        {tab === "documents" ? artifacts.map((item) => <article key={item.id}><div className="library-icon"><FileText size={19} /></div><div><small>{item.kind.replaceAll("_", " ")} · {formatDate(item.updated_at)}</small><h3>{item.title}</h3><p>{item.content.slice(0, 180)}</p></div><button className="icon-button" type="button" onClick={async () => { await artifactApi.remove(item.id); reload(); }} aria-label="Xóa tài liệu"><Trash2 size={15} /></button></article>) : conversations.map((item) => <article key={item.id}><div className="library-icon"><MessageSquareText size={19} /></div><div><small>{item.message_count} tin nhắn · {formatDate(item.updated_at)}</small><h3>{item.title}</h3><p>Cuộc trò chuyện pháp lý đã lưu.</p></div><button className="icon-button" type="button" onClick={async () => { await conversationApi.update(item.id, { status: "ARCHIVED" }); reload(); }} aria-label="Lưu trữ"><Archive size={15} /></button></article>)}
        {((tab === "documents" && !artifacts.length) || (tab === "chats" && !conversations.length)) && <div className="empty-state"><FolderClock size={30} /><h3>Chưa có dữ liệu</h3><p>Kết quả AI của bạn sẽ tự động được lưu tại đây.</p></div>}
      </div>
    </section>
  );
}

function FeedbackModal({ open, page, onClose }: { open: boolean; page: string; onClose: () => void }) {
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  if (!open) return null;
  return <div className="modal-backdrop"><form className="modal feedback-modal" onSubmit={async (event) => { event.preventDefault(); await sendFeedback({ message, page }); setSent(true); setMessage(""); }}><header><div><span className="eyebrow">Phản hồi</span><h2>Giúp VLegal tốt hơn</h2></div><button className="icon-button" type="button" onClick={onClose}><X size={17} /></button></header>{sent && <div className="success-notice"><CheckCircle2 size={16} />Đã ghi nhận góp ý.</div>}<textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Nội dung góp ý…" /><footer><button className="ghost-button" type="button" onClick={onClose}>Đóng</button><button className="primary-button" type="submit" disabled={message.length < 3}>Gửi góp ý</button></footer></form></div>;
}

function SignInGate({ available, returnTo, onContinue }: { available: boolean; returnTo: string; onContinue: () => void }) {
  return <div className="signin-page"><div className="signin-card"><div className="brand-mark"><Scale size={29} /></div><span className="eyebrow">Không gian cá nhân</span><h1>{available ? "Đăng nhập để tiếp tục" : "Tính năng này đang tạm gián đoạn"}</h1><p>{available ? "Dùng tài khoản Google để lưu lịch sử, quản lý tài liệu và sử dụng các công cụ hợp đồng." : "Bạn vẫn có thể hỏi đáp pháp luật trong phiên trò chuyện tạm thời."}</p>{available && <a className="primary-button signin-button google-signin" href={authApi.loginUrl(returnTo)}><span className="google-mark">G</span>Tiếp tục với Google</a>}<button className="guest-continue" type="button" onClick={onContinue}>Quay lại hỏi đáp</button><small>Phiên khách chỉ được lưu tạm trong trình duyệt và không gắn với tài khoản.</small></div></div>;
}

function App() {
  const [path, navigate] = usePath();
  const [collapsed, setCollapsed] = useState(() => typeof window !== "undefined" && window.innerWidth <= 900);
  const [dark, setDark] = useState(() => typeof window !== "undefined" && localStorage.getItem("vlegal-theme") === "dark");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authAvailable, setAuthAvailable] = useState(true);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("vlegal-theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    Promise.allSettled([authApi.capabilities(), authApi.me()]).then(([capabilityResult, userResult]) => {
      // Chỉ ẩn nút khi backend xác nhận SSO chưa được cấu hình.
      // Nếu backend tạm mất kết nối, giữ nút để không biến lỗi mạng thành trạng thái "tắt tính năng".
      setAuthAvailable(capabilityResult.status === "rejected" || capabilityResult.value.google_login);
      if (userResult.status === "fulfilled") setUser(userResult.value);
      if (userResult.status === "rejected" && userResult.reason instanceof ApiError && userResult.reason.status !== 401) {
        setUser(null);
      }
    }).finally(() => setAuthLoading(false));
  }, []);

  const activeRoute = useMemo(() => routes.find((route) => route.path === path) || routes[0], [path]);
  const page = useMemo(() => {
    if (!user && path !== "/") return <SignInGate available={authAvailable} returnTo={path} onContinue={() => navigate("/")} />;
    if (path === "/tao-hop-dong") return <ContractPage />;
    if (path === "/review-hop-dong" || path === "/phan-tich-hop-dong") return <ReviewPage />;
    if (path === "/so-sanh-hop-dong") return <ComparePage />;
    if (path === "/ky-van-ban") return <SignaturePage />;
    if (path === "/bai-viet") return <ArticlesPage />;
    if (path === "/thu-vien") return <LibraryPage />;
    return <ChatPage user={user} authAvailable={authAvailable} />;
  }, [authAvailable, navigate, path, user]);

  if (authLoading) return <div className="app-loading"><Scale size={34} /><span>Đang mở VLegal AI…</span></div>;

  return (
    <div className="app-shell">
      <aside className={collapsed ? "sidebar collapsed" : "sidebar"}>
        <div className="brand-row"><button className="brand" type="button" title={collapsed ? "Mở thanh điều hướng" : "Về trang chủ"} aria-label={collapsed ? "Mở thanh điều hướng" : "Về trang chủ"} onClick={() => { if (collapsed) { setCollapsed(false); return; } if (path !== "/") navigate("/"); }}><span className="brand-mark"><Scale size={22} /></span><span><strong>VLegal</strong><small>Trợ lý pháp lý</small></span></button><button className="icon-button" type="button" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Mở thanh điều hướng" : "Thu gọn thanh điều hướng"}><AlignLeft size={18} /></button></div>
        <nav className="nav-list"><span className="nav-label">Không gian làm việc</span>{routes.map((route) => { const Icon = route.icon; return <button key={route.path} type="button" className={activeRoute.path === route.path ? "active" : ""} onClick={() => { navigate(route.path); if (window.innerWidth <= 900) setCollapsed(true); }}><Icon size={19} /><span>{route.label}</span></button>; })}</nav>
        <div className="trust-card"><ShieldCheck size={17} /><span><strong>Căn cứ minh bạch</strong><small>Kiểm tra hiệu lực trước khi trả lời</small></span></div>
        <div className="sidebar-actions"><button type="button" onClick={() => setFeedbackOpen(true)}><Bot size={17} /><span>Gửi góp ý</span></button><button type="button" onClick={() => setDark((value) => !value)}>{dark ? <Sun size={17} /> : <Moon size={17} />}<span>{dark ? "Giao diện sáng" : "Giao diện tối"}</span></button>{user ? <div className="user-card"><span className="user-avatar">{user.avatar_url ? <img src={user.avatar_url} alt="" /> : user.display_name.charAt(0).toUpperCase()}</span><span><strong>{user.display_name}</strong><small>{user.email}</small></span><button type="button" onClick={async () => { await authApi.logout(); window.location.reload(); }} aria-label="Đăng xuất"><LogOut size={16} /></button></div> : <div className="user-card guest-user-card"><span className="user-avatar"><UserRound size={17} /></span><span><strong>Khách</strong><small>Phiên tạm thời</small></span>{authAvailable && <a href={authApi.loginUrl(path)} aria-label="Đăng nhập bằng Google"><LogIn size={16} /></a>}</div>}</div>
      </aside>
      <div className="content-shell"><header className="mobile-topbar"><button className="icon-button" type="button" onClick={() => setCollapsed((value) => !value)}><Menu size={19} /></button><strong>{activeRoute.label}</strong><button className="icon-button" type="button" onClick={() => setDark((value) => !value)}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button></header><main className="content">{page}</main></div>
      <FeedbackModal open={feedbackOpen} page={path} onClose={() => setFeedbackOpen(false)} />
    </div>
  );
}

export default App;
