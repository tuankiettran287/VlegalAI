import {
  ClipboardEvent as ReactClipboardEvent,
  FormEvent,
  ReactNode,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
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
  ChevronRight,
  ClipboardCheck,
  Copy,
  Download,
  ExternalLink,
  FileDiff,
  FileImage,
  FilePenLine,
  FileText,
  FolderClock,
  History,
  Library,
  LogOut,
  Menu,
  MessageSquareText,
  Moon,
  PenTool,
  Plus,
  RefreshCw,
  Scale,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  Sun,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  ApiError,
  artifactApi,
  askLegalQuestion,
  authApi,
  compareContracts,
  conversationApi,
  downloadContractDocx,
  draftContract,
  extractContractDocument,
  getTemplates,
  rateChatAnswer,
  reviewContract,
  sendFeedback,
  uploadChatAttachment,
  type CompareResponse,
  type DraftResponse,
  type ReviewResponse,
} from "./api";
import { sampleQuestions, templateFallback } from "./data";
import ArticlesPage from "./ArticlesPage";
import LandingPage from "./LandingPage";
import GuidePage from "./GuidePage";
import LegalDocumentPage from "./LegalDocumentPage";
import OnboardingPage from "./OnboardingPage";
import type {
  Artifact,
  ChatAttachment,
  ChatMessage,
  Conversation,
  Risk,
  Source,
  Template,
  User,
  VerificationReport,
} from "./types";

const routes = [
  { path: "/", label: "Hỏi đáp pháp luật", icon: MessageSquareText },
  { path: "/tao-hop-dong", label: "Tạo hợp đồng", icon: FilePenLine },
  { path: "/review-hop-dong", label: "Review hợp đồng", icon: ClipboardCheck },
  { path: "/so-sanh-hop-dong", label: "So sánh hợp đồng", icon: FileDiff },
  {
    path: "/ky-van-ban",
    label: "Ký văn bản",
    icon: PenTool,
    comingSoon: true,
  },
  { path: "/bai-viet", label: "Bài viết", icon: BookOpen },
  { path: "/thu-vien", label: "Lịch sử & tài liệu", icon: Library },
];

const ACTIVE_CONVERSATION_STORAGE_KEY = "vlegal-active-conversation-id";

function readActiveConversationId() {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistActiveConversationId(id: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (id) window.sessionStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, id);
    else window.sessionStorage.removeItem(ACTIVE_CONVERSATION_STORAGE_KEY);
  } catch {
    // Browsers can disable storage; the in-memory state still keeps navigation working.
  }
}

function artifactKindLabel(kind: string) {
  const labels: Record<string, string> = {
    CONTRACT_DRAFT: "Bản nháp hợp đồng",
    CONTRACT_REVIEW: "Kết quả review hợp đồng",
    CONTRACT_COMPARE: "Kết quả so sánh hợp đồng",
    LEGAL_NOTE: "Ghi chú pháp lý",
  };
  return labels[kind] || kind.replaceAll("_", " ");
}

function uid() {
  return globalThis.crypto?.randomUUID?.() || String(Date.now() + Math.random());
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeSourceUrl(value?: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function citationTooltip(source: Source) {
  const sourceId = escapeHtml(source.source_id.toUpperCase());
  const sourceTitle = escapeHtml(source.citation || source.title || "Căn cứ pháp lý");
  const sourceText = escapeHtml(
    String(source.text || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 260),
  );
  const sourceUrl = safeSourceUrl(source.source_url);
  const accessibleLabel = escapeHtml(`Mở căn cứ ${source.source_id}: ${source.citation || source.title}`);
  const citationControl = sourceUrl
    ? `<a class="inline-citation" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" aria-label="${accessibleLabel}">[${sourceId}]</a>`
    : `<button class="inline-citation" type="button" aria-label="Xem thông tin căn cứ ${sourceId}">[${sourceId}]</button>`;
  const actionHint = sourceUrl
    ? "Bấm để mở văn bản gốc"
    : "Nguồn này chưa có liên kết chính thức";

  return `<span class="inline-citation-wrap">${citationControl}<span class="citation-tooltip" role="tooltip"><strong>${sourceId} · ${sourceTitle}</strong>${sourceText ? `<span>${sourceText}</span>` : ""}<em>${actionHint}</em></span></span>`;
}

function markdown(value: string, sources?: Source[] | null) {
  const sourceById = new Map(
    (Array.isArray(sources) ? sources : [])
      .filter((source) => source?.source_id)
      .map((source) => [source.source_id.toUpperCase(), source]),
  );

  return escapeHtml((value || "").replace(/\r\n?/g, "\n").trim())
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/^[-•] (.*)$/gm, "<div class='md-list-item'>• $1</div>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([Ss]\d+)\]/g, (match, sourceId: string) => {
      const source = sourceById.get(sourceId.toUpperCase());
      return source ? citationTooltip(source) : match;
    })
    .replace(/<\/div>\n+(?=<div class='md-list-item'>)/g, "</div>")
    .replace(/\n{2,}/g, "<span class='md-paragraph-gap'></span>")
    .replace(/\n/g, "<br />");
}

export function CitationMarkdown({
  text,
  sources,
  ariaHidden,
}: {
  text: string;
  sources?: Source[];
  ariaHidden?: boolean;
}) {
  return (
    <div
      aria-hidden={ariaHidden ? "true" : undefined}
      dangerouslySetInnerHTML={{ __html: markdown(text, sources) }}
    />
  );
}

function TypewriterMarkdown({
  text,
  sources,
  active,
  onComplete,
  onProgress,
}: {
  text: string;
  sources?: Source[];
  active: boolean;
  onComplete: () => void;
  onProgress: () => void;
}) {
  const characters = useMemo(() => Array.from(text), [text]);
  const [visibleCount, setVisibleCount] = useState(active ? 0 : characters.length);
  const animationFrameRef = useRef<number | null>(null);
  const completedRef = useRef(!active);
  const onCompleteRef = useRef(onComplete);
  const onProgressRef = useRef(onProgress);

  useEffect(() => {
    onCompleteRef.current = onComplete;
    onProgressRef.current = onProgress;
  }, [onComplete, onProgress]);

  useEffect(() => {
    if (animationFrameRef.current !== null) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    if (!active || !characters.length) {
      completedRef.current = true;
      setVisibleCount(characters.length);
      return;
    }

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisibleCount(characters.length);
      if (!completedRef.current) {
        completedRef.current = true;
        onCompleteRef.current();
      }
      return;
    }

    completedRef.current = false;
    setVisibleCount(0);
    const startedAt = performance.now();
    const duration = Math.min(6000, Math.max(700, characters.length * 14));

    const reveal = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / duration);
      const nextCount = Math.min(
        characters.length,
        Math.max(1, Math.ceil(progress * characters.length)),
      );
      setVisibleCount(nextCount);

      if (progress < 1) {
        animationFrameRef.current = requestAnimationFrame(reveal);
        return;
      }

      animationFrameRef.current = null;
      if (!completedRef.current) {
        completedRef.current = true;
        onCompleteRef.current();
      }
    };

    animationFrameRef.current = requestAnimationFrame(reveal);
    return () => {
      if (animationFrameRef.current !== null) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, [active, characters]);

  useLayoutEffect(() => {
    if (active && visibleCount > 0) onProgressRef.current();
  }, [active, visibleCount]);

  const finishImmediately = () => {
    if (animationFrameRef.current !== null) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    setVisibleCount(characters.length);
    if (!completedRef.current) {
      completedRef.current = true;
      onCompleteRef.current();
    }
  };

  const visibleText = characters.slice(0, visibleCount).join("");
  return (
    <div className={`assistant-answer${active ? " is-typing" : ""}`} aria-busy={active}>
      <CitationMarkdown text={visibleText} sources={sources} ariaHidden={active} />
      {active && (
        <div className="typing-controls">
          <span className="typing-cursor" aria-hidden="true" />
          <span className="sr-only" role="status">Đang hiển thị câu trả lời</span>
          <button type="button" onClick={finishImmediately}>Hiện ngay</button>
        </div>
      )}
    </div>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function formatFileSize(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
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

function VerificationBadge({ report }: { report?: VerificationReport | null }) {
  if (!report) return null;
  const attachmentFact = report.note === "user_attachment_factual";
  const current = report.checked && report.all_current;
  const items = Array.isArray(report.items) ? report.items : [];
  if (
    !report.checked
    && !items.length
    && (!report.note || report.note === "Dữ liệu không có sẵn")
  ) {
    return null;
  }
  return (
    <details className={`verification ${current || attachmentFact ? "verified" : "attention"}`}>
      <summary>
        {current || attachmentFact ? <CheckCircle2 size={15} /> : <RefreshCw size={15} />}
        <span>{attachmentFact ? "Đã đọc tài liệu đính kèm" : current ? "Đã kiểm tra hiệu lực" : "Có văn bản cần lưu ý"}</span>
        {report.checked_at && <time>{formatDate(report.checked_at)}</time>}
        <ChevronDown size={14} />
      </summary>
      <div className="verification-body">
        <p>{attachmentFact ? "Câu trả lời này dựa trên nội dung có thể đọc được từ tệp bạn cung cấp." : report.note}</p>
        {items.map((item) => (
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

export function SourcePanel({ sources }: { sources?: Source[] | null }) {
  if (!Array.isArray(sources) || !sources.length) return null;

  return (
    <details className="source-panel">
      <summary>
        <FileText size={16} />
        <span>{sources.length} căn cứ được sử dụng</span>
        <ChevronDown size={16} />
      </summary>
      <div className="source-list">
        {sources.map((source) => {
          const sourceUrl = safeSourceUrl(source.source_url);
          return (
            <article className="source-item" key={`${source.source_id}-${source.citation}`}>
              <div className="source-title">
                <span className="source-id">{source.source_id}</span>
                <strong>{source.citation || source.title}</strong>
                {sourceUrl && (
                  <span className="source-link-actions">
                    <a
                      className="source-open-link"
                      href={sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`Mở văn bản gốc: ${source.citation || source.title}`}
                    >
                      <span>Xem văn bản gốc</span>
                      <ExternalLink size={13} />
                    </a>
                  </span>
                )}
              </div>
              <p>{source.text}</p>
            </article>
          );
        })}
      </div>
    </details>
  );
}

function ContractDocumentPreview({ text }: { text: string }) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  return (
    <div className="contract-document-preview" aria-label="Nội dung hợp đồng">
      {lines.map((line, index) => {
        const value = line.trim();
        if (!value) return <div className="contract-document-spacer" aria-hidden="true" key={`blank-${index}`} />;
        const folded = value.toLocaleLowerCase("vi-VN");
        const isNationalHeading = value === "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM";
        const isMotto = folded === "độc lập - tự do - hạnh phúc";
        const isTitle = value === value.toLocaleUpperCase("vi-VN")
          && (folded.includes("hợp đồng") || folded.includes("thỏa thuận"));
        const isArticle = /^điều\s+\d+[a-zđ]?(?:[.:]|\s|$)/i.test(value);
        const isSignature = /\t+|\s+\|\s+/.test(value)
          && (folded.includes("người lao động") || folded.includes("người sử dụng lao động") || folded.includes("ký, ghi rõ"));
        if (isSignature) {
          const cells = value.split(/\t+|\s+\|\s+/).map((cell) => cell.trim());
          return (
            <div className="contract-document-signatures" key={`${value}-${index}`}>
              <span>{cells[0]}</span><span>{cells[1] || ""}</span>
            </div>
          );
        }
        return (
          <p
            className={[
              isNationalHeading ? "national-heading" : "",
              isMotto ? "national-motto" : "",
              isTitle ? "contract-title" : "",
              isArticle ? "contract-article" : "",
              value.startsWith("• ") ? "contract-bullet" : "",
            ].filter(Boolean).join(" ")}
            key={`${value}-${index}`}
          >
            {value}
          </p>
        );
      })}
    </div>
  );
}

function ResultPanel({
  title,
  text,
  sources,
  verification,
  format = "markdown",
  actions,
  children,
}: {
  title: string;
  text: string;
  sources?: Source[];
  verification?: VerificationReport;
  format?: "markdown" | "document";
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="result-panel">
      <header className="result-header">
        <div>
          <span className="eyebrow">Kết quả AI</span>
          <h2>{title}</h2>
        </div>
        <div className="result-actions">
          {actions}
          <button className="icon-button" type="button" onClick={() => navigator.clipboard?.writeText(text)} aria-label="Sao chép">
            <Copy size={17} />
          </button>
        </div>
      </header>
      <VerificationBadge report={verification} />
      {format === "document"
        ? <ContractDocumentPreview text={text} />
        : <div className="markdown" dangerouslySetInnerHTML={{ __html: markdown(text) }} />}
      {children}
      <SourcePanel sources={sources} />
    </section>
  );
}

function PageHeader({ title, subtitle, action }: { title: string; subtitle: string; action?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow"><i aria-hidden="true" /> Không gian nghiệp vụ</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </header>
  );
}

function DocumentInput({
  title,
  value,
  onChange,
  onError,
}: {
  title: string;
  value: string;
  onChange: (value: string) => void;
  onError?: (message: string) => void;
}) {
  const inputId = useId();
  const [uploading, setUploading] = useState(false);
  const [fileName, setFileName] = useState("");

  return (
    <div className="document-input">
      <label htmlFor={`${inputId}-text`}>{title}</label>
      <textarea
        id={`${inputId}-text`}
        value={value}
        maxLength={120000}
        onChange={(event) => {
          onChange(event.target.value);
          if (fileName) setFileName("");
        }}
        placeholder={`Dán ${title.toLowerCase()} hoặc tải file lên...`}
      />
      <div className="document-input-footer">
        <label className="ghost-button file-button">
          {uploading ? <RefreshCw className="spin" size={16} /> : <Upload size={16} />}
          {uploading ? "Đang đọc file…" : "Tải PDF/DOCX/TXT"}
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md"
            disabled={uploading}
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              setUploading(true);
              onError?.("");
              try {
                const extracted = await extractContractDocument(file);
                onChange(extracted.text);
                setFileName(
                  `${extracted.filename}${extracted.truncated ? " · đã lấy 120.000 ký tự đầu" : ""}`,
                );
              } catch (reason) {
                onError?.((reason as Error).message);
              } finally {
                setUploading(false);
                event.target.value = "";
              }
            }}
          />
        </label>
        <span title={fileName || undefined}>
          {fileName ? `${fileName} · ` : ""}
          {value.length.toLocaleString("vi-VN")} ký tự
        </span>
      </div>
    </div>
  );
}

export function ChatPage({
  onNavigate,
  userName,
  initialConversationId,
  onActiveConversationChange,
}: {
  onNavigate: (path: string) => void;
  userName: string;
  initialConversationId: string | null;
  onActiveConversationChange: (id: string | null) => void;
}) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [attachmentUploading, setAttachmentUploading] = useState(false);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [error, setError] = useState("");
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [feedbackMessageId, setFeedbackMessageId] = useState<string | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackLoadingId, setFeedbackLoadingId] = useState<string | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const imageAttachmentInputRef = useRef<HTMLInputElement>(null);
  const documentAttachmentInputRef = useRef<HTMLInputElement>(null);
  const attachmentMenuRef = useRef<HTMLDivElement>(null);
  const conversationRequestRef = useRef(0);
  const restoredConversationRef = useRef<string | null>(null);
  const hasMessages = messages.length > 0;
  const lastMessageId = messages[messages.length - 1]?.id;

  const scrollToLatest = useCallback((onlyIfPinned = true) => {
    const container = chatScrollRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (!onlyIfPinned || distanceFromBottom < 180) {
      container.scrollTop = container.scrollHeight;
    }
  }, []);

  useLayoutEffect(() => {
    scrollToLatest(false);
  }, [lastMessageId, messages.length, scrollToLatest]);

  const reloadHistory = useCallback(() => {
    conversationApi.list().then(setConversations).catch((reason) => setError((reason as Error).message));
  }, []);

  useEffect(() => reloadHistory(), [reloadHistory]);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setHistoryOpen(false);
        setAttachmentMenuOpen(false);
      }
    };
    const closeAttachmentMenu = (event: PointerEvent) => {
      const menu = attachmentMenuRef.current;
      if (menu && !menu.contains(event.target as Node)) {
        setAttachmentMenuOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("pointerdown", closeAttachmentMenu);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("pointerdown", closeAttachmentMenu);
    };
  }, []);

  const openConversation = useCallback(async (id: string) => {
    if (id === conversationId) {
      conversationRequestRef.current += 1;
      setLoadingConversationId(null);
      setHistoryOpen(false);
      onActiveConversationChange(id);
      return;
    }

    const requestId = conversationRequestRef.current + 1;
    conversationRequestRef.current = requestId;
    setError("");
    setLoadingConversationId(id);
    try {
      const data = await conversationApi.get(id);
      if (conversationRequestRef.current !== requestId) return;
      if (data.conversation.id !== id) {
        throw new Error("Dữ liệu cuộc trò chuyện không khớp. Vui lòng thử lại.");
      }
      setConversationId(id);
      onActiveConversationChange(id);
      setMessages(data.messages);
      setAttachments([]);
      setAttachmentMenuOpen(false);
      setFeedbackMessageId(null);
      setFeedbackComment("");
      setHistoryOpen(false);
    } catch (reason) {
      if (conversationRequestRef.current !== requestId) return;
      setError((reason as Error).message);
      setHistoryOpen(false);
      if (!conversationId) onActiveConversationChange(null);
    } finally {
      if (conversationRequestRef.current === requestId) {
        setLoadingConversationId(null);
      }
    }
  }, [conversationId, onActiveConversationChange]);

  useEffect(() => {
    if (
      !initialConversationId
      || initialConversationId === conversationId
      || restoredConversationRef.current === initialConversationId
    ) {
      return;
    }
    restoredConversationRef.current = initialConversationId;
    void openConversation(initialConversationId);
  }, [conversationId, initialConversationId, openConversation]);

  const newConversation = () => {
    conversationRequestRef.current += 1;
    setLoadingConversationId(null);
    setConversationId(null);
    restoredConversationRef.current = null;
    onActiveConversationChange(null);
    setMessages([]);
    setInput("");
    setAttachments([]);
    setAttachmentMenuOpen(false);
    setError("");
    setFeedbackMessageId(null);
    setFeedbackComment("");
    setCopiedMessageId(null);
  };

  const handleAttachmentFiles = async (files: FileList | File[] | null) => {
    if (!files?.length || attachmentUploading || loading) return;
    const remainingSlots = 3 - attachments.length;
    if (remainingSlots <= 0) {
      setError("Mỗi câu hỏi chỉ được đính kèm tối đa 3 tệp.");
      return;
    }
    const selected = Array.from(files);
    if (selected.length > remainingSlots) {
      setError(`Bạn chỉ có thể chọn thêm ${remainingSlots} tệp.`);
      return;
    }
    setError("");
    setAttachmentMenuOpen(false);
    setAttachmentUploading(true);
    const uploaded: ChatAttachment[] = [];
    try {
      for (const file of selected) {
        uploaded.push(await uploadChatAttachment(file));
      }
      setAttachments((current) => [...current, ...uploaded].slice(0, 3));
    } catch (reason) {
      if (uploaded.length) {
        setAttachments((current) => [...current, ...uploaded].slice(0, 3));
      }
      setError((reason as Error).message);
    } finally {
      setAttachmentUploading(false);
      if (imageAttachmentInputRef.current) imageAttachmentInputRef.current.value = "";
      if (documentAttachmentInputRef.current) documentAttachmentInputRef.current.value = "";
    }
  };

  const handleComposerPaste = (event: ReactClipboardEvent<HTMLTextAreaElement>) => {
    const pastedImages = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((file): file is File => Boolean(file));
    if (!pastedImages.length) return;

    event.preventDefault();
    const supportedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
    const unsupported = pastedImages.find((file) => !supportedTypes.has(file.type));
    if (unsupported) {
      setError("Ảnh dán vào phải có định dạng JPEG, PNG hoặc WebP.");
      return;
    }
    const extensionByType: Record<string, string> = {
      "image/jpeg": "jpg",
      "image/png": "png",
      "image/webp": "webp",
    };
    const timestamp = Date.now();
    const namedImages = pastedImages.map((file, index) => new File(
      [file],
      `anh-dan-${timestamp}-${index + 1}.${extensionByType[file.type]}`,
      { type: file.type, lastModified: file.lastModified || timestamp },
    ));
    void handleAttachmentFiles(namedImages);
  };

  const submit = async (question = input) => {
    const submittedAttachments = [...attachments];
    const displayAttachments = submittedAttachments.map((attachment) => ({
      filename: attachment.filename,
      content_type: attachment.content_type,
      kind: attachment.kind,
      size_bytes: attachment.size_bytes,
      page_count: attachment.page_count,
      truncated: attachment.truncated,
    }));
    const trimmed = question.trim() || (
      submittedAttachments.length
        ? "Hãy phân tích các tệp đính kèm và cho tôi biết những vấn đề pháp luật lao động cần lưu ý."
        : ""
    );
    if (!trimmed || loading || attachmentUploading || loadingConversationId) return;
    setError("");
    setAttachmentMenuOpen(false);
    setLoading(true);
    const userMessage: ChatMessage = {
      id: uid(),
      role: "user",
      content: trimmed,
      attachments: displayAttachments,
    };
    const pendingId = uid();
    setMessages((current) => [
      ...current.map((message) =>
        message.typing ? { ...message, typing: false } : message,
      ),
      userMessage,
      {
        id: pendingId,
        role: "assistant",
        content: "Thinking…",
        pending: true,
      },
    ]);
    setInput("");
    setAttachments([]);
    try {
      const data = await askLegalQuestion(
        trimmed,
        conversationId,
        { attachments: submittedAttachments },
      );
      const nextConversationId = data.conversation_id || null;
      setConversationId(nextConversationId);
      onActiveConversationChange(nextConversationId);
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
                typing: true,
              }
            : message,
        ),
      );
      reloadHistory();
    } catch (reason) {
      const message = (reason as Error).message;
      setMessages((current) => current.filter((item) => item.id !== pendingId));
      setAttachments((current) => current.length ? current : submittedAttachments);
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const copyAnswer = async (message: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);
      window.setTimeout(() => {
        setCopiedMessageId((current) =>
          current === message.id ? null : current
        );
      }, 1800);
    } catch {
      setError("Không thể sao chép câu trả lời. Vui lòng thử lại.");
    }
  };

  const markAnswerGood = async (message: ChatMessage) => {
    if (feedbackLoadingId || message.feedback_rating === "good") return;
    setFeedbackLoadingId(message.id);
    setError("");
    try {
      await rateChatAnswer(message.id, { rating: "good" });
      setMessages((current) =>
        current.map((item) =>
          item.id === message.id
            ? { ...item, feedback_rating: "good" }
            : item
        )
      );
      setFeedbackMessageId(null);
      setFeedbackComment("");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setFeedbackLoadingId(null);
    }
  };

  const regenerateFromFeedback = async (
    event: FormEvent,
    message: ChatMessage,
  ) => {
    event.preventDefault();
    const comment = feedbackComment.trim();
    if (
      comment.length < 3
      || feedbackLoadingId
      || loading
      || !conversationId
    ) {
      return;
    }
    const answerIndex = messages.findIndex(
      (item) => item.id === message.id
    );
    const question = messages
      .slice(0, Math.max(0, answerIndex))
      .reverse()
      .find((item) => item.role === "user");
    if (!question) {
      setError("Không tìm thấy câu hỏi gốc để tạo lại câu trả lời.");
      return;
    }

    setError("");
    setLoading(true);
    setFeedbackLoadingId(message.id);
    setMessages((current) =>
      current.map((item) =>
        item.id === message.id
          ? {
              ...item,
              feedback_rating: "bad",
              regenerating: true,
            }
          : item
      )
    );
    try {
      await rateChatAnswer(message.id, {
        rating: "bad",
        comment,
      });
      const data = await askLegalQuestion(
        question.content,
        conversationId,
        { regenerateFromMessageId: message.id },
      );
      const nextConversationId = data.conversation_id || conversationId;
      setConversationId(nextConversationId);
      onActiveConversationChange(nextConversationId);
      setMessages((current) =>
        current.map((item) =>
          item.id === message.id
            ? {
                id: data.message_id,
                conversation_id: data.conversation_id || undefined,
                role: "assistant",
                content: data.answer,
                sources: data.sources,
                verification: data.verification,
                feedback_rating: null,
                regenerating: false,
                typing: true,
              }
            : item
        )
      );
      setFeedbackMessageId(null);
      setFeedbackComment("");
      reloadHistory();
    } catch (reason) {
      setMessages((current) =>
        current.map((item) =>
          item.id === message.id
            ? { ...item, regenerating: false }
            : item
        )
      );
      setError((reason as Error).message);
    } finally {
      setFeedbackLoadingId(null);
      setLoading(false);
    }
  };

  const renderComposer = (home = false) => (
    <form
      className={home ? "composer composer-home" : "composer"}
      aria-busy={Boolean(loadingConversationId)}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="input-wrap">
        <div className="composer-meta">
          <label htmlFor="legal-question-input">{home ? "Tình huống cần tư vấn" : "Tiếp tục trao đổi"}</label>
          <span>{home ? "Mô tả càng cụ thể, kết quả càng sát nhu cầu" : "Shift + Enter để xuống dòng"}</span>
        </div>
        {attachments.length > 0 && (
          <div className="composer-attachments" aria-label="Tệp đã đính kèm">
            {attachments.map((attachment, index) => (
              <span className="attachment-chip" key={`${attachment.filename}-${index}`}>
                {attachment.kind === "image" ? <FileImage size={15} /> : <FileText size={15} />}
                <span>
                  <strong>{attachment.filename}</strong>
                  <small>{formatFileSize(attachment.size_bytes)}{attachment.truncated ? " · đã rút gọn" : ""}</small>
                </span>
                <button
                  type="button"
                  onClick={() => setAttachments((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                  aria-label={`Bỏ tệp ${attachment.filename}`}
                >
                  <X size={13} />
                </button>
              </span>
            ))}
          </div>
        )}
        <textarea
          id="legal-question-input"
          value={input}
          maxLength={5000}
          rows={1}
          disabled={Boolean(loadingConversationId)}
          onChange={(event) => setInput(event.target.value)}
          onPaste={handleComposerPaste}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={attachments.length ? "Bạn muốn hỏi điều gì về tệp này?" : "Hỏi VLegal về tình huống pháp lý của bạn…"}
        />
        <div className="composer-toolbar">
          <div className="attachment-menu-wrap" ref={attachmentMenuRef}>
            <button
              className="attachment-plus"
              type="button"
              disabled={attachmentUploading || loading || attachments.length >= 3}
              onClick={() => setAttachmentMenuOpen((current) => !current)}
              aria-label="Thêm ảnh hoặc tài liệu"
              aria-haspopup="menu"
              aria-expanded={attachmentMenuOpen}
              title="Thêm ảnh hoặc tài liệu"
            >
              {attachmentUploading
                ? <RefreshCw className="spin" size={17} />
                : <Plus size={19} />}
            </button>
            {attachmentMenuOpen && (
              <div className="attachment-menu" role="menu" aria-label="Chọn loại nội dung tải lên">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => imageAttachmentInputRef.current?.click()}
                >
                  <span className="attachment-menu-icon"><FileImage size={18} /></span>
                  <span><strong>Tải ảnh</strong><small>JPEG, PNG hoặc WebP</small></span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => documentAttachmentInputRef.current?.click()}
                >
                  <span className="attachment-menu-icon"><FileText size={18} /></span>
                  <span><strong>Tải tài liệu</strong><small>PDF, DOCX, TXT hoặc Markdown</small></span>
                </button>
                <span className="attachment-paste-hint"><Copy size={14} />Hoặc dán ảnh trực tiếp bằng Ctrl+V</span>
              </div>
            )}
            <input
              ref={imageAttachmentInputRef}
              className="attachment-input"
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => void handleAttachmentFiles(event.target.files)}
            />
            <input
              ref={documentAttachmentInputRef}
              className="attachment-input"
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md"
              onChange={(event) => void handleAttachmentFiles(event.target.files)}
            />
          </div>
          {attachmentUploading && <span className="attachment-upload-status" role="status">Đang đọc tệp…</span>}
          <span className="policy-line">
            <ShieldCheck size={14} />
            Đối chiếu căn cứ và kiểm tra hiệu lực
          </span>
          <span className="counter">{input.length}/5000</span>
          <button className="primary-icon" type="submit" disabled={(!input.trim() && !attachments.length) || loading || attachmentUploading || Boolean(loadingConversationId)} aria-label="Gửi câu hỏi">
            <SendHorizontal size={18} />
          </button>
        </div>
      </div>
    </form>
  );

  return (
    <section className={historyOpen ? "chat-page" : "chat-page history-collapsed"}>
      {historyOpen && (
        <button
          className="chat-history-backdrop"
          type="button"
          onClick={() => setHistoryOpen(false)}
          aria-label="Đóng lịch sử trò chuyện"
        />
      )}
      <aside
        id="chat-history-panel"
        className={historyOpen ? "chat-history" : "chat-history hidden"}
        aria-label="Lịch sử trò chuyện"
      >
        <div className="history-head">
          <strong>Lịch sử hỏi đáp</strong>
          <button className="icon-button compact" type="button" onClick={newConversation} aria-label="Tạo cuộc trò chuyện">
            <Plus size={16} />
          </button>
        </div>
        <div className="conversation-list">
          {conversations.map((item) => {
            const isLoading = item.id === loadingConversationId;
            const isActive = item.id === (loadingConversationId || conversationId);
            return (
              <div
                className={["conversation-row", isActive ? "active" : "", isLoading ? "loading" : ""].filter(Boolean).join(" ")}
                key={item.id}
              >
                <button
                  type="button"
                  disabled={isLoading}
                  onClick={() => openConversation(item.id)}
                  aria-current={isActive ? "true" : undefined}
                >
                  {isLoading ? <RefreshCw className="conversation-row-spinner" size={15} /> : <MessageSquareText size={15} />}
                  <span>
                    <strong>{item.title}</strong>
                    <small>{isLoading ? "Đang tải lại nội dung…" : `${item.message_count} tin · ${formatDate(item.updated_at)}`}</small>
                  </span>
                </button>
                <button
                  className="row-action"
                  type="button"
                  disabled={Boolean(loadingConversationId)}
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
            );
          })}
          {!conversations.length && <p className="empty-copy">Các cuộc trò chuyện đã lưu sẽ xuất hiện tại đây.</p>}
        </div>
      </aside>

      <div
        className={`${hasMessages ? "chat-main has-conversation" : "chat-main empty-chat"}${loadingConversationId ? " switching-conversation" : ""}`}
        aria-busy={Boolean(loadingConversationId)}
      >
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
            <span><i aria-hidden="true" /><ShieldCheck size={12} /> Tự động đối chiếu căn cứ liên quan</span>
          </div>
          <div className="chat-topbar-actions">
            <button className="ghost-button" type="button" onClick={newConversation}>
              <Plus size={16} /> Cuộc trò chuyện mới
            </button>
          </div>
        </header>

        <div className="chat-scroll" ref={chatScrollRef}>
            <div className="chat-empty" aria-hidden={hasMessages}>
              <div className="empty-state-inner">
              <header className="empty-heading">
                <span className="eyebrow"><i aria-hidden="true" /> Legal intelligence</span>
                <h1>Xin chào {userName},<br /><span>bạn cần hỗ trợ điều gì?</span></h1>
                <p>Mô tả câu hỏi hoặc tình huống pháp lý của bạn. VLegal sẽ phân tích, kiểm tra hiệu lực và dẫn nguồn để bạn dễ đối chiếu.</p>
              </header>

              {!hasMessages && renderComposer(true)}

              <div className="chat-shortcuts" aria-label="Công cụ pháp lý">
                <button type="button" onClick={() => onNavigate("/tao-hop-dong")}><FilePenLine size={16} /> Tạo hợp đồng</button>
                <button type="button" onClick={() => onNavigate("/review-hop-dong")}><ClipboardCheck size={16} /> Review hợp đồng</button>
                <button type="button" onClick={() => onNavigate("/so-sanh-hop-dong")}><FileDiff size={16} /> So sánh văn bản</button>
              </div>

              <div className="starter-grid">
                {sampleQuestions.map((question, index) => (
                  <button key={question} type="button" onClick={() => submit(question)}>
                    <span>{index === 0 ? "Lao động" : index === 1 ? "Tiền lương" : index === 2 ? "Hợp đồng" : "Tranh chấp"}</span>
                    <strong>{question}</strong>
                    <SendHorizontal size={15} />
                  </button>
                ))}
              </div>

              <p className="chat-disclaimer">
                <ShieldCheck size={13} />
                VLegal kiểm tra hiệu lực và hiển thị nguồn; kết quả không thay thế ý kiến tư vấn chuyên môn.
              </p>
              </div>
            </div>
            <div className="messages" aria-live="polite">
              {messages.map((message) => (
                <article className={`message ${message.role}`} key={message.id}>
                  {message.role === "assistant" && <div className="avatar"><Scale size={16} /></div>}
                  <div className="bubble">
                    {message.role === "user" && Boolean(message.attachments?.length) && (
                      <div className="message-attachments">
                        {message.attachments?.map((attachment, index) => (
                          <span key={`${message.id}-${attachment.filename}-${index}`}>
                            {attachment.kind === "image" ? <FileImage size={14} /> : <FileText size={14} />}
                            <span>
                              <strong>{attachment.filename}</strong>
                              <small>{formatFileSize(attachment.size_bytes)}</small>
                            </span>
                          </span>
                        ))}
                      </div>
                    )}
                    {message.role === "assistant" ? (
                      <TypewriterMarkdown
                        text={message.content}
                        sources={message.sources}
                        active={Boolean(message.typing)}
                        onProgress={scrollToLatest}
                        onComplete={() =>
                          setMessages((current) =>
                            current.map((item) =>
                              item.id === message.id && item.typing
                                ? { ...item, typing: false }
                                : item,
                            ),
                          )
                        }
                      />
                    ) : (
                      <div dangerouslySetInnerHTML={{ __html: markdown(message.content) }} />
                    )}
                    {message.pending && <div className="loading-line" />}
                    {!message.typing && <VerificationBadge report={message.verification} />}
                    {!message.typing && <SourcePanel sources={message.sources} />}
                    {message.role === "assistant" && !message.typing && !message.pending && (
                      <>
                        {message.regenerating ? (
                          <div className="answer-regenerating" role="status">
                            <RefreshCw size={14} />
                            Đang tạo lại câu trả lời theo góp ý của bạn…
                          </div>
                        ) : (
                          <div className="answer-actions" aria-label="Thao tác với câu trả lời">
                            <button
                              type="button"
                              onClick={() => void copyAnswer(message)}
                              aria-label="Sao chép câu trả lời"
                            >
                              {copiedMessageId === message.id
                                ? <Check size={14} />
                                : <Copy size={14} />}
                              <span>{copiedMessageId === message.id ? "Đã sao chép" : "Sao chép"}</span>
                            </button>
                            <button
                              className={message.feedback_rating === "good" ? "active good" : ""}
                              type="button"
                              disabled={feedbackLoadingId === message.id}
                              aria-pressed={message.feedback_rating === "good"}
                              aria-label="Câu trả lời tốt"
                              onClick={() => void markAnswerGood(message)}
                            >
                              <ThumbsUp size={14} />
                              <span>Hữu ích</span>
                            </button>
                            <button
                              className={[
                                message.feedback_rating === "bad" ? "active bad" : "",
                                feedbackMessageId === message.id ? "selected" : "",
                              ].filter(Boolean).join(" ")}
                              type="button"
                              disabled={feedbackLoadingId === message.id}
                              aria-pressed={message.feedback_rating === "bad"}
                              aria-label="Câu trả lời chưa tốt"
                              onClick={() => {
                                setFeedbackMessageId((current) =>
                                  current === message.id ? null : message.id
                                );
                                setFeedbackComment("");
                              }}
                            >
                              <ThumbsDown size={14} />
                              <span>Chưa tốt</span>
                            </button>
                          </div>
                        )}
                        {feedbackMessageId === message.id && !message.regenerating && (
                          <form
                            className="answer-feedback-form"
                            onSubmit={(event) =>
                              void regenerateFromFeedback(event, message)
                            }
                          >
                            <label htmlFor={`answer-feedback-${message.id}`}>
                              Câu trả lời cần cải thiện điều gì?
                            </label>
                            <textarea
                              id={`answer-feedback-${message.id}`}
                              value={feedbackComment}
                              maxLength={2000}
                              rows={3}
                              autoFocus
                              placeholder="Ví dụ: thiếu căn cứ cụ thể, giải thích khó hiểu, chưa trả lời đúng tình huống…"
                              onChange={(event) =>
                                setFeedbackComment(event.target.value)
                              }
                            />
                            <footer>
                              <span>{feedbackComment.length}/2000</span>
                              <button
                                type="button"
                                onClick={() => {
                                  setFeedbackMessageId(null);
                                  setFeedbackComment("");
                                }}
                              >
                                Hủy
                              </button>
                              <button
                                className="primary"
                                type="submit"
                                disabled={
                                  feedbackComment.trim().length < 3
                                  || feedbackLoadingId === message.id
                                }
                              >
                                <RefreshCw size={13} />
                                Gửi và tạo lại
                              </button>
                            </footer>
                          </form>
                        )}
                      </>
                    )}
                  </div>
                </article>
              ))}
            </div>
            {loadingConversationId && (
              <div className="conversation-switching" role="status" aria-live="polite">
                <RefreshCw size={18} />
                <span>
                  <strong>Đang mở cuộc trò chuyện</strong>
                  <small>Đang khôi phục đầy đủ tin nhắn và căn cứ…</small>
                </span>
              </div>
            )}
        </div>
        {error && <div className="chat-error"><ErrorNotice error={error} onClose={() => setError("")} /></div>}
        {hasMessages && renderComposer()}
      </div>
    </section>
  );
}

function ContractPage() {
  const [templates, setTemplates] = useState<Template[]>(templateFallback);
  const [selected, setSelected] = useState<Template>(templateFallback[0]);
  const [mode, setMode] = useState<"new" | "revise">("new");
  const [prompt, setPrompt] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [result, setResult] = useState<DraftResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
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
    const effectivePrompt = prompt.trim() || "Rà soát, chuẩn hóa và hoàn thiện hợp đồng được cung cấp.";
    if (mode === "new" && effectivePrompt.length < 8) return;
    if (mode === "revise" && sourceText.trim().length < 20) return;
    setLoading(true);
    setError("");
    try {
      setResult(await draftContract({
        prompt: effectivePrompt,
        template_id: selected.id,
        template_name: selected.name,
        source_text: mode === "revise" ? sourceText : undefined,
      }));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="tool-page">
      <PageHeader title="Tạo hợp đồng lao động" subtitle="Soạn và hoàn thiện các hợp đồng, phụ lục và thỏa thuận gắn trực tiếp với quan hệ lao động." />
      {error && <ErrorNotice error={error} onClose={() => setError("")} />}
      <div className="workspace-grid">
        <form className="workspace-card tool-form" onSubmit={submit}>
          <div className="contract-mode-toggle" role="group" aria-label="Cách tạo hợp đồng">
            <button
              type="button"
              className={mode === "new" ? "active" : ""}
              onClick={() => setMode("new")}
            >
              <FilePenLine size={16} /> Soạn hợp đồng mới
            </button>
            <button
              type="button"
              className={mode === "revise" ? "active" : ""}
              onClick={() => setMode("revise")}
            >
              <Upload size={16} /> Hoàn thiện bản có sẵn
            </button>
          </div>
          <div className="section-title"><span>1</span><div><h2>Chọn loại văn bản lao động</h2><p>Chức năng chỉ hỗ trợ các văn bản liên quan trực tiếp đến quan hệ lao động.</p></div></div>
          <div className="template-grid-inline">
            {templates.map((item) => (
              <button key={item.id} className={selected.id === item.id ? "template-option active" : "template-option"} type="button" onClick={() => setSelected(item)}>
                <FileText size={17} /><span><strong>{item.name}</strong><small>{item.category}</small></span>
                {selected.id === item.id && <Check size={15} />}
              </button>
            ))}
          </div>
          <div className="section-title">
            <span>2</span>
            <div>
              <h2>{mode === "new" ? "Mô tả yêu cầu" : "Cung cấp hợp đồng hiện có"}</h2>
              <p>
                {mode === "new"
                  ? "Nêu người sử dụng lao động, người lao động, công việc, nơi làm việc, thời hạn, lương và điều kiện đặc biệt."
                  : "Tải PDF/DOCX/TXT hoặc dán toàn bộ hợp đồng lao động cần chỉnh lý."}
              </p>
            </div>
          </div>
          {mode === "revise" && (
            <DocumentInput
              title="Hợp đồng lao động cần hoàn thiện"
              value={sourceText}
              onChange={setSourceText}
              onError={setError}
            />
          )}
          <label className="field">
            <span>{mode === "new" ? "Yêu cầu soạn thảo" : "Yêu cầu chỉnh sửa (không bắt buộc)"}</span>
            <textarea
              className="large-textarea"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              maxLength={30000}
              placeholder={
                mode === "new"
                  ? "Ví dụ: loại và thời hạn hợp đồng, vị trí, nơi làm việc, lương, phụ cấp, lịch làm việc, chế độ bảo hiểm và yêu cầu đặc biệt…"
                  : "Nêu các nội dung cần giữ lại, bổ sung hoặc ưu tiên bảo vệ…"
              }
            />
          </label>
          <div className="form-footer">
            <span className="policy-line"><ShieldCheck size={14} /> Tự kiểm tra luật hiện hành</span>
            <button
              className="primary-button"
              type="submit"
              disabled={
                loading
                || (mode === "new" && prompt.trim().length < 8)
                || (mode === "revise" && sourceText.trim().length < 20)
              }
            >
              {loading
                ? <><RefreshCw className="spin" size={16} /> Đang xử lý…</>
                : <><Sparkles size={16} /> {mode === "new" ? "Tạo bản nháp" : "Hoàn thiện hợp đồng"}</>}
            </button>
          </div>
        </form>
        <ResultPanel
          title={result?.title || "Bản nháp sẽ xuất hiện tại đây"}
          text={result?.draft || "Mô tả yêu cầu càng cụ thể, bản hợp đồng lao động càng sát nhu cầu. Kết quả được lưu tự động vào Thư viện tài liệu."}
          sources={result?.sources}
          verification={result?.verification}
          format={result ? "document" : "markdown"}
          actions={result && (
            <button
              className="ghost-button result-download-button"
              type="button"
              disabled={downloading}
              onClick={async () => {
                setDownloading(true);
                setError("");
                try {
                  await downloadContractDocx(result.artifact_id, result.title);
                } catch (reason) {
                  setError((reason as Error).message);
                } finally {
                  setDownloading(false);
                }
              }}
            >
              {downloading ? <RefreshCw className="spin" size={16} /> : <Download size={16} />}
              {downloading ? "Đang tạo DOCX…" : "Tải DOCX"}
            </button>
          )}
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
      <small>Nguồn: {risk.citations.join(", ")}</small>
    </article>
  ))}</div>;
}

function ReviewPage() {
  const [title, setTitle] = useState("");
  const [userRole, setUserRole] = useState("");
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
          try {
            setResult(await reviewContract({
              title: title || undefined,
              text,
              user_role: userRole || undefined,
            }));
          }
          catch (reason) { setError((reason as Error).message); }
          finally { setLoading(false); }
        }}>
          <label className="field"><span>Tên tài liệu</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Hợp đồng dịch vụ 2026" /></label>
          <label className="field">
            <span>Bạn là bên nào trong hợp đồng?</span>
            <input
              value={userRole}
              onChange={(event) => setUserRole(event.target.value)}
              maxLength={240}
              placeholder="Ví dụ: bên thuê dịch vụ, người lao động, bên mua…"
            />
          </label>
          <DocumentInput title="Nội dung hợp đồng" value={text} onChange={setText} onError={setError} />
          <button className="primary-button align-right" type="submit" disabled={loading || text.trim().length < 20}>
            {loading ? "Đang phân tích…" : "Phân tích hợp đồng"}
          </button>
        </form>
        <ResultPanel title="Kết quả review" text={result?.summary || "Kết quả tổng quan, danh sách rủi ro và khuyến nghị sẽ hiển thị tại đây."} sources={result?.sources} verification={result?.verification}>
          {result && (
            <>
              <div className="review-context">
                <span><small>Loại hợp đồng</small>{result.contract_type}</span>
                <span><small>Góc nhìn đánh giá</small>{result.party_perspective}</span>
              </div>
              {result.key_terms.length > 0 && (
                <section className="contract-analysis-section">
                  <h3>Thông tin và điều khoản chính</h3>
                  <div className="key-term-grid">
                    {result.key_terms.map((item, index) => (
                      <article key={`${item.label}-${index}`}>
                        <small>{item.label}</small>
                        <strong>{item.value}</strong>
                        <p>{item.assessment}</p>
                      </article>
                    ))}
                  </div>
                </section>
              )}
              {result.clause_reviews.length > 0 && (
                <section className="contract-analysis-section">
                  <h3>Rà soát theo điều khoản</h3>
                  <div className="clause-review-list">
                    {result.clause_reviews.map((item, index) => (
                      <article className={item.assessment} key={`${item.clause}-${index}`}>
                        <div>
                          <span>{
                            item.assessment === "unfavorable" ? "Bất lợi"
                              : item.assessment === "missing" ? "Còn thiếu"
                                : item.assessment === "favorable" ? "Có lợi"
                                  : "Trung tính"
                          }</span>
                          <h4>{item.clause}</h4>
                        </div>
                        <p>{item.issue}</p>
                        <strong>Đề xuất: {item.suggested_revision}</strong>
                        {item.citations.length > 0 && <small>Nguồn: {item.citations.join(", ")}</small>}
                      </article>
                    ))}
                  </div>
                </section>
              )}
              {result.missing_clauses.length > 0 && (
                <div className="recommendations">
                  <h3>Điều khoản còn thiếu</h3>
                  {result.missing_clauses.map((item) => <p key={item}><Plus size={15} />{item}</p>)}
                </div>
              )}
            </>
          )}
          <RiskList risks={result?.risks} />
          {result?.recommendations?.length ? <div className="recommendations"><h3>Khuyến nghị</h3>{result.recommendations.map((item) => <p key={item}><Check size={15} />{item}</p>)}</div> : null}
        </ResultPanel>
      </div>
    </section>
  );
}

function ComparePage() {
  const [originalTitle, setOriginalTitle] = useState("");
  const [revisedTitle, setRevisedTitle] = useState("");
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
        try {
          setResult(await compareContracts({
            original_title: originalTitle || undefined,
            revised_title: revisedTitle || undefined,
            original_text: original,
            revised_text: revised,
          }));
        }
        catch (reason) { setError((reason as Error).message); }
        finally { setLoading(false); }
      }}>
        <div className="compare-document-column">
          <label className="field">
            <span>Tên bản gốc</span>
            <input value={originalTitle} onChange={(event) => setOriginalTitle(event.target.value)} placeholder="Phiên bản đã ký hoặc bản trước thương lượng" />
          </label>
          <DocumentInput title="Bản gốc" value={original} onChange={setOriginal} onError={setError} />
        </div>
        <div className="compare-document-column">
          <label className="field">
            <span>Tên bản sửa đổi</span>
            <input value={revisedTitle} onChange={(event) => setRevisedTitle(event.target.value)} placeholder="Phiên bản đối tác gửi lại" />
          </label>
          <DocumentInput title="Bản sửa đổi" value={revised} onChange={setRevised} onError={setError} />
        </div>
        <button className="primary-button compare-submit" type="submit" disabled={loading || original.length < 20 || revised.length < 20}>
          <FileDiff size={16} /> {loading ? "Đang so sánh…" : "So sánh hai phiên bản"}
        </button>
      </form>
      {result && <ResultPanel title={`Mức tương đồng ${result.similarity}%`} text={result.summary} sources={result.sources} verification={result.verification}>
        <div className="compare-stat-grid">
          <span className="added"><strong>{result.change_counts.added}</strong>Thêm</span>
          <span className="deleted"><strong>{result.change_counts.deleted}</strong>Xóa</span>
          <span className="modified"><strong>{result.change_counts.modified}</strong>Chỉnh sửa</span>
        </div>
        {result.analysis_truncated && (
          <p className="search-warning">Tài liệu có quá nhiều nhóm thay đổi; phần tác động pháp lý và số lượng hiển thị tập trung vào các thay đổi đầu tiên đã đọc.</p>
        )}
        {result.important_changes.length > 0 && (
          <div className="recommendations">
            <h3>Thay đổi quan trọng</h3>
            {result.important_changes.map((item) => <p key={item}><CheckCircle2 size={15} />{item}</p>)}
          </div>
        )}
        <div className="diff-list">{result.differences.map((item, index) => (
          <article className={`diff-${item.type} severity-${item.severity}`} key={`${item.type}-${item.clause}-${index}`}>
            <header>
              <span>{
                item.type === "added" ? "Được thêm"
                  : item.type === "deleted" ? "Bị xóa"
                    : "Đã chỉnh sửa"
              }</span>
              <small>{item.clause} · {
                item.category === "money" ? "Số tiền"
                  : item.category === "term" ? "Thời hạn"
                    : item.category === "responsibility" ? "Trách nhiệm"
                      : item.category === "penalty" ? "Phạt vi phạm"
                        : item.category === "termination" ? "Chấm dứt"
                          : "Nội dung khác"
              }</small>
            </header>
            <div><small>Trước</small><p>{item.before || "Không có"}</p></div>
            <div><small>Sau</small><p>{item.after || "Không có"}</p></div>
            <strong>{item.legal_impact}</strong>
            {item.citations.length > 0 && <small>Nguồn: {item.citations.join(", ")}</small>}
          </article>
        ))}</div>
        <RiskList risks={result.risks} />
        <div className="recommendations"><h3>Khuyến nghị xử lý</h3><p><Check size={15} />{result.recommendation}</p></div>
      </ResultPanel>}
    </section>
  );
}

function SignaturePage() {
  return (
    <section className="tool-page signature-coming-soon-page">
      <PageHeader
        title="Ký văn bản"
        subtitle="VLegal đang hoàn thiện quy trình ký số an toàn, xác thực danh tính và theo dõi trạng thái văn bản trong một không gian thống nhất."
      />
      <section className="coming-soon-panel" aria-labelledby="signature-coming-soon-title">
        <div className="coming-soon-icon" aria-hidden="true"><PenTool size={28} /></div>
        <span className="coming-soon-status">Sắp ra mắt</span>
        <h2 id="signature-coming-soon-title">Ký số tin cậy, theo dõi minh bạch</h2>
        <p>
          Tính năng đang được hoàn thiện và chưa nhận văn bản để ký. Khi phát hành,
          bạn sẽ có thể chuẩn bị hồ sơ ký, quản lý người ký và kiểm tra toàn bộ tiến
          trình ngay trên VLegal.
        </p>
        <div className="coming-soon-capabilities" aria-label="Các khả năng dự kiến">
          <span><ShieldCheck size={17} />Xác thực và bảo vệ văn bản</span>
          <span><History size={17} />Theo dõi lịch sử ký</span>
          <span><CheckCircle2 size={17} />Quản lý trạng thái người ký</span>
        </div>
      </section>
    </section>
  );
}

function LibraryPage({
  onOpenArtifact,
  onOpenConversation,
}: {
  onOpenArtifact: (id: string) => void;
  onOpenConversation: (id: string) => void;
}) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [tab, setTab] = useState<"documents" | "chats">("documents");
  const [error, setError] = useState("");
  const reload = useCallback(() => Promise.all([artifactApi.list().then(setArtifacts), conversationApi.list().then(setConversations)]), []);
  useEffect(() => {
    reload().catch((reason) => setError((reason as Error).message));
  }, [reload]);
  return (
    <section className="tool-page library-page">
      <PageHeader title="Lịch sử & tài liệu" subtitle="Quản lý toàn bộ cuộc trò chuyện, bản nháp, kết quả review và so sánh đã được lưu an toàn." />
      {error && <ErrorNotice error={error} onClose={() => setError("")} />}
      <div className="tab-bar"><button className={tab === "documents" ? "active" : ""} onClick={() => setTab("documents")}><FileText size={16} />Tài liệu ({artifacts.length})</button><button className={tab === "chats" ? "active" : ""} onClick={() => setTab("chats")}><MessageSquareText size={16} />Hỏi đáp ({conversations.length})</button></div>
      <div className="library-list">
        {tab === "documents" ? artifacts.map((item) => (
          <article key={item.id}>
            <button className="library-item-main" type="button" onClick={() => onOpenArtifact(item.id)}>
              <span className="library-icon"><FileText size={19} /></span>
              <span className="library-item-copy">
                <small>{artifactKindLabel(item.kind)} · {formatDate(item.updated_at)}</small>
                <strong>{item.title}</strong>
                <span>{item.content.slice(0, 180)}</span>
              </span>
              <ChevronRight size={17} aria-hidden="true" />
            </button>
            <button className="icon-button library-row-action" type="button" onClick={async () => { try { await artifactApi.remove(item.id); await reload(); } catch (reason) { setError((reason as Error).message); } }} aria-label={`Xóa tài liệu ${item.title}`}><Trash2 size={15} /></button>
          </article>
        )) : conversations.map((item) => (
          <article key={item.id}>
            <button className="library-item-main" type="button" onClick={() => onOpenConversation(item.id)}>
              <span className="library-icon"><MessageSquareText size={19} /></span>
              <span className="library-item-copy">
                <small>{item.message_count} tin nhắn · {formatDate(item.updated_at)}</small>
                <strong>{item.title}</strong>
                <span>Mở lại cuộc trò chuyện pháp lý đã lưu.</span>
              </span>
              <ChevronRight size={17} aria-hidden="true" />
            </button>
            <button className="icon-button library-row-action" type="button" onClick={async () => { try { await conversationApi.update(item.id, { status: "ARCHIVED" }); await reload(); } catch (reason) { setError((reason as Error).message); } }} aria-label={`Lưu trữ cuộc trò chuyện ${item.title}`}><Archive size={15} /></button>
          </article>
        ))}
        {((tab === "documents" && !artifacts.length) || (tab === "chats" && !conversations.length)) && <div className="empty-state"><FolderClock size={30} /><h3>Chưa có dữ liệu</h3><p>Kết quả AI của bạn sẽ tự động được lưu tại đây.</p></div>}
      </div>
    </section>
  );
}

function ArtifactPage({ artifactId, onNavigate }: { artifactId: string; onNavigate: (path: string) => void }) {
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    artifactApi.get(artifactId)
      .then((data) => {
        if (active) setArtifact(data);
      })
      .catch((reason) => {
        if (active) setError((reason as Error).message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [artifactId]);

  return (
    <section className="tool-page artifact-page">
      <button className="ghost-button artifact-back" type="button" onClick={() => onNavigate("/thu-vien")}>
        <ArrowLeft size={16} /> Quay lại Lịch sử & tài liệu
      </button>
      {loading && <div className="artifact-state"><RefreshCw className="conversation-row-spinner" size={19} /><strong>Đang mở tài liệu…</strong></div>}
      {!loading && error && <ErrorNotice error={error} />}
      {!loading && artifact && (
        <article className="artifact-document">
          <header>
            <div>
              <span className="eyebrow">{artifactKindLabel(artifact.kind)}</span>
              <h1>{artifact.title}</h1>
              <p>Cập nhật {formatDate(artifact.updated_at)} · Trạng thái {artifact.status.toLocaleLowerCase("vi-VN")}</p>
            </div>
            <div className="artifact-header-actions">
              {artifact.kind === "CONTRACT_DRAFT" && (
                <button
                  className="ghost-button"
                  type="button"
                  disabled={downloading}
                  onClick={async () => {
                    setDownloading(true);
                    setError("");
                    try {
                      await downloadContractDocx(artifact.id, artifact.title);
                    } catch (reason) {
                      setError((reason as Error).message);
                    } finally {
                      setDownloading(false);
                    }
                  }}
                >
                  {downloading ? <RefreshCw className="spin" size={15} /> : <Download size={15} />}
                  {downloading ? "Đang tạo DOCX…" : "Tải DOCX"}
                </button>
              )}
              <button
                className="ghost-button"
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(artifact.content);
                    setCopied(true);
                    window.setTimeout(() => setCopied(false), 1800);
                  } catch {
                    setError("Không thể sao chép tài liệu. Vui lòng thử lại.");
                  }
                }}
              >
                <Copy size={15} /> {copied ? "Đã sao chép" : "Sao chép"}
              </button>
            </div>
          </header>
          {artifact.kind === "CONTRACT_DRAFT"
            ? <ContractDocumentPreview text={artifact.content} />
            : <div className="artifact-document-content" dangerouslySetInnerHTML={{ __html: markdown(artifact.content) }} />}
        </article>
      )}
    </section>
  );
}

function FeedbackModal({ open, page, onClose }: { open: boolean; page: string; onClose: () => void }) {
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  if (!open) return null;
  return <div className="modal-backdrop"><form className="modal feedback-modal" role="dialog" aria-modal="true" aria-labelledby="feedback-title" onSubmit={async (event) => { event.preventDefault(); await sendFeedback({ message, page }); setSent(true); setMessage(""); }}><header><div><span className="eyebrow">Phản hồi</span><h2 id="feedback-title">Giúp VLegal tốt hơn</h2></div><button className="icon-button" type="button" onClick={onClose} aria-label="Đóng hộp thoại góp ý"><X size={17} /></button></header>{sent && <div className="success-notice"><CheckCircle2 size={16} />Đã ghi nhận góp ý.</div>}<textarea aria-label="Nội dung góp ý" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Nội dung góp ý…" /><footer><button className="ghost-button" type="button" onClick={onClose}>Đóng</button><button className="primary-button" type="submit" disabled={message.length < 3}>Gửi góp ý</button></footer></form></div>;
}

function App() {
  const [path, navigate] = usePath();
  const [activeConversationId, setActiveConversationId] = useState<string | null>(readActiveConversationId);
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== "undefined" && window.innerWidth <= 1080,
  );
  const [dark, setDark] = useState(() => typeof window !== "undefined" && localStorage.getItem("vlegal-theme") === "dark");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authAvailable, setAuthAvailable] = useState(true);

  const rememberActiveConversation = useCallback((id: string | null) => {
    setActiveConversationId(id);
    persistActiveConversationId(id);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("vlegal-theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1080px)");
    const closeOnNarrowViewport = (event: MediaQueryListEvent) => {
      if (event.matches) setCollapsed(true);
    };
    media.addEventListener("change", closeOnNarrowViewport);
    return () => media.removeEventListener("change", closeOnNarrowViewport);
  }, []);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && window.innerWidth <= 1080) {
        setCollapsed(true);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

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

  if (authLoading) return <div className="app-loading"><Scale size={34} /><span>Đang mở VLegal AI…</span></div>;
  if (path === "/huong-dan") {
    return (
      <GuidePage
        authAvailable={authAvailable}
        loginUrl={authApi.loginUrl(path)}
        authenticated={Boolean(user)}
      />
    );
  }
  if (!user) {
    return (
      <LandingPage
        authAvailable={authAvailable}
        loginUrl={authApi.loginUrl(path)}
      />
    );
  }
  if (user.onboarding_required) {
    return (
      <OnboardingPage
        user={user}
        onComplete={async (preferredName) => {
          setUser(await authApi.updateProfile(preferredName));
        }}
      />
    );
  }

  const activeRoute = routes.find(
    (route) => route.path === path || (route.path !== "/" && path.startsWith(`${route.path}/`)),
  ) || routes[0];
  let page: ReactNode;
  if (path === "/tao-hop-dong") page = <ContractPage />;
  else if (path === "/review-hop-dong" || path === "/phan-tich-hop-dong") page = <ReviewPage />;
  else if (path === "/so-sanh-hop-dong") page = <ComparePage />;
  else if (path === "/ky-van-ban") page = <SignaturePage />;
  else if (path === "/van-ban") {
    const params = new URLSearchParams(window.location.search);
    page = (
      <LegalDocumentPage
        code={params.get("code") || ""}
        citation={params.get("citation") || ""}
        onNavigate={navigate}
      />
    );
  }
  else if (path === "/bai-viet" || path.startsWith("/bai-viet/")) {
    const articleSlug = path.startsWith("/bai-viet/")
      ? decodeURIComponent(path.slice("/bai-viet/".length))
      : undefined;
    page = <ArticlesPage slug={articleSlug} onNavigate={navigate} />;
  }
  else if (path.startsWith("/thu-vien/tai-lieu/")) {
    page = (
      <ArtifactPage
        artifactId={decodeURIComponent(path.slice("/thu-vien/tai-lieu/".length))}
        onNavigate={navigate}
      />
    );
  }
  else if (path === "/thu-vien") {
    page = (
      <LibraryPage
        onOpenArtifact={(id) => navigate(`/thu-vien/tai-lieu/${encodeURIComponent(id)}`)}
        onOpenConversation={(id) => {
          rememberActiveConversation(id);
          navigate("/");
        }}
      />
    );
  }
  else page = (
    <ChatPage
      onNavigate={navigate}
      userName={user.preferred_name || user.display_name}
      initialConversationId={activeConversationId}
      onActiveConversationChange={rememberActiveConversation}
    />
  );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Chuyển đến nội dung chính</a>
      {!collapsed && (
        <button
          className="sidebar-backdrop"
          type="button"
          onClick={() => setCollapsed(true)}
          aria-label="Đóng thanh điều hướng"
        />
      )}
      <aside
        id="primary-navigation"
        className={collapsed ? "sidebar collapsed" : "sidebar"}
        aria-label="Điều hướng chính"
      >
        <div className="brand-row"><button className="brand" type="button" title={collapsed ? "Mở thanh điều hướng" : "Về trang chủ"} aria-label={collapsed ? "Mở thanh điều hướng" : "Về trang chủ"} onClick={() => { if (collapsed) { setCollapsed(false); return; } if (path !== "/") navigate("/"); }}><span className="brand-mark"><Scale size={22} /></span><span><strong>VLegal</strong><small>Trợ lý pháp lý</small></span></button><button className="icon-button" type="button" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Mở thanh điều hướng" : "Thu gọn thanh điều hướng"}><AlignLeft size={18} /></button></div>
        <nav className="nav-list">
          <span className="nav-label">Trung tâm pháp lý</span>
          {routes.map((route) => {
            const Icon = route.icon;
            const active = activeRoute.path === route.path;
            return (
              <button
                key={route.path}
                type="button"
                className={active ? "active" : ""}
                aria-current={active ? "page" : undefined}
                onClick={() => {
                  navigate(route.path);
                  if (window.innerWidth <= 1080) setCollapsed(true);
                }}
              >
                <Icon size={19} />
                <span>{route.label}</span>
                {route.comingSoon && <small className="nav-coming-soon">Sắp ra mắt</small>}
              </button>
            );
          })}
        </nav>
        <div className="trust-card"><ShieldCheck size={17} /><span><strong>Căn cứ minh bạch</strong><small>Kiểm tra hiệu lực trước khi trả lời</small></span></div>
        <div className="sidebar-actions"><button type="button" onClick={() => setFeedbackOpen(true)}><Bot size={17} /><span>Gửi góp ý</span></button><button type="button" onClick={() => setDark((value) => !value)}>{dark ? <Sun size={17} /> : <Moon size={17} />}<span>{dark ? "Giao diện sáng" : "Giao diện tối"}</span></button><div className="user-card"><span className="user-avatar">{user.avatar_url ? <img src={user.avatar_url} alt="" /> : (user.preferred_name || user.display_name).charAt(0).toUpperCase()}</span><span><strong>{user.preferred_name || user.display_name}</strong><small>{user.email}</small></span><button type="button" onClick={async () => { rememberActiveConversation(null); await authApi.logout(); window.location.reload(); }} aria-label="Đăng xuất"><LogOut size={16} /></button></div></div>
      </aside>
      <div className="content-shell"><header className="mobile-topbar"><button className="icon-button" type="button" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Mở thanh điều hướng" : "Đóng thanh điều hướng"} aria-controls="primary-navigation" aria-expanded={!collapsed}><Menu size={19} /></button><strong>{activeRoute.label}</strong><button className="icon-button" type="button" onClick={() => setDark((value) => !value)} aria-label={dark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button></header><main className={`content${path === "/van-ban" ? " content-document-scroll" : ""}`} id="main-content" tabIndex={-1}>{page}</main></div>
      <FeedbackModal open={feedbackOpen} page={path} onClose={() => setFeedbackOpen(false)} />
    </div>
  );
}

export default App;
