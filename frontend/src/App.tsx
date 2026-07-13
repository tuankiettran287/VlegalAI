import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import {
  AlignLeft,
  ArrowLeft,
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  ClipboardCheck,
  Clock,
  Copy,
  FileCheck2,
  FileDiff,
  FilePenLine,
  FileText,
  History,
  LayoutDashboard,
  LogIn,
  Menu,
  MessageSquareText,
  Moon,
  PenTool,
  Plus,
  Scale,
  Search,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  Sun,
  Upload,
  X,
} from "lucide-react";
import {
  askLegalQuestion,
  compareContracts,
  draftContract,
  getStats,
  prepareSignature,
  reviewContract,
  searchLaws,
  sendFeedback,
  type ChatResponse,
  type CompareResponse,
  type DraftResponse,
  type ReviewResponse,
  type SignatureResponse,
  type StatsResponse,
} from "./api";
import { articles, retrievalModes, sampleQuestions, templates } from "./data";
import type { Article, ChatMessage, Law, RetrievalMode, Risk, Source, Template } from "./types";

const routes = [
  { path: "/", label: "Hỏi đáp", icon: MessageSquareText },
  { path: "/tao-hop-dong", label: "Tạo hợp đồng", icon: FilePenLine },
  { path: "/phan-tich-hop-dong", label: "Review hợp đồng", icon: ClipboardCheck },
  { path: "/so-sanh-hop-dong", label: "So sánh hợp đồng", icon: FileDiff },
  { path: "/ky-van-ban", label: "Ký văn bản", icon: PenTool },
  { path: "/bai-viet", label: "Bài viết", icon: BookOpen },
  { path: "/gioi-thieu", label: "Giới thiệu", icon: ShieldCheck },
];

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

function markdown(value: string) {
  const safe = escapeHtml(value || "");
  return safe
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br />");
}

function usePath() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const navigate = (nextPath: string) => {
    window.history.pushState({}, "", nextPath);
    setPath(nextPath);
  };
  return [path, navigate] as const;
}

async function readTextFile(file: File) {
  const text = await file.text();
  return text.slice(0, 50000);
}

function ModePicker({
  value,
  onChange,
}: {
  value: RetrievalMode;
  onChange: (value: RetrievalMode) => void;
}) {
  return (
    <div className="mode-picker" role="radiogroup" aria-label="Chế độ tra cứu">
      {retrievalModes.map((mode) => (
        <button
          key={mode.value}
          type="button"
          className={value === mode.value ? "active" : ""}
          onClick={() => onChange(mode.value)}
        >
          {mode.label}
        </button>
      ))}
    </div>
  );
}

function SourcePanel({ sources }: { sources?: Source[] }) {
  if (!sources?.length) return null;
  return (
    <details className="source-panel">
      <summary>
        <FileText size={16} />
        <span>{sources.length} căn cứ pháp lý</span>
        <ChevronDown size={16} />
      </summary>
      <div className="source-list">
        {sources.map((source) => (
          <article className="source-item" key={`${source.source_id}-${source.citation}`}>
            <div>
              <span className="source-id">{source.source_id}</span>
              <strong>{source.citation || source.title}</strong>
            </div>
            <p>{source.text}</p>
          </article>
        ))}
      </div>
    </details>
  );
}

function RiskList({ risks }: { risks?: Risk[] }) {
  if (!risks?.length) return <p className="muted">Chưa phát hiện rủi ro nổi bật theo bộ kiểm tra nhanh.</p>;
  return (
    <div className="risk-list">
      {risks.map((risk, index) => (
        <article className={`risk-card ${risk.level}`} key={`${risk.title}-${index}`}>
          <span>{risk.level === "high" ? "Cao" : risk.level === "medium" ? "Vừa" : "Thấp"}</span>
          <h3>{risk.title}</h3>
          <p>{risk.detail}</p>
          <strong>{risk.recommendation}</strong>
        </article>
      ))}
    </div>
  );
}

function LawPicker({
  open,
  selected,
  onApply,
  onClose,
}: {
  open: boolean;
  selected: Law[];
  onApply: (laws: Law[]) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Law[]>([]);
  const [draftSelected, setDraftSelected] = useState<Law[]>(selected);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDraftSelected(selected);
  }, [open, selected]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        setItems(await searchLaws(query));
      } finally {
        setLoading(false);
      }
    }, 220);
    return () => window.clearTimeout(timer);
  }, [open, query]);

  if (!open) return null;
  const selectedIds = new Set(draftSelected.map((law) => law.id));
  const toggleLaw = (law: Law) => {
    if (selectedIds.has(law.id)) {
      setDraftSelected((current) => current.filter((item) => item.id !== law.id));
      return;
    }
    if (draftSelected.length >= 10) return;
    setDraftSelected((current) => [...current, law]);
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal law-modal" role="dialog" aria-modal="true" aria-label="Chọn luật áp dụng">
        <div className="modal-header">
          <div>
            <h2>Chọn luật áp dụng</h2>
            <p>Tìm và chọn tối đa 10 văn bản để tập trung trả lời. ({draftSelected.length}/10)</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Đóng">
            <X size={18} />
          </button>
        </div>
        <label className="search-box">
          <Search size={18} />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm theo số hiệu hoặc tiêu đề..."
          />
        </label>
        {draftSelected.length > 0 && (
          <div className="selected-laws">
            {draftSelected.map((law) => (
              <button key={law.id} type="button" onClick={() => toggleLaw(law)}>
                {law.code}
                <X size={13} />
              </button>
            ))}
          </div>
        )}
        <div className="law-results">
          {loading && <p className="muted">Đang tìm...</p>}
          {!loading && items.length === 0 && <p className="muted">Nhập từ khóa để tìm kiếm.</p>}
          {items.map((law) => (
            <button
              key={law.id}
              type="button"
              className={selectedIds.has(law.id) ? "law-row selected" : "law-row"}
              onClick={() => toggleLaw(law)}
            >
              <span>{law.code}</span>
              <strong>{law.title}</strong>
              {selectedIds.has(law.id) && <Check size={16} />}
            </button>
          ))}
        </div>
        <div className="modal-actions">
          <button type="button" className="ghost-button" onClick={onClose}>
            Hủy
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              onApply(draftSelected);
              onClose();
            }}
          >
            Áp dụng
          </button>
        </div>
      </section>
    </div>
  );
}

function TemplateModal({
  open,
  selected,
  onSelect,
  onClose,
}: {
  open: boolean;
  selected?: Template;
  onSelect: (template: Template) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Tất cả");
  const categories = ["Tất cả", ...Array.from(new Set(templates.map((item) => item.category)))];
  const filtered = templates.filter((template) => {
    const inCategory = category === "Tất cả" || template.category === category;
    const inQuery = !query || template.name.toLowerCase().includes(query.toLowerCase());
    return inCategory && inQuery;
  });
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal template-modal" role="dialog" aria-modal="true" aria-label="Mẫu hợp đồng">
        <div className="modal-header">
          <div>
            <h2>Mẫu hợp đồng</h2>
            <p>Chọn mẫu để hệ thống định hướng cấu trúc bản nháp.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Đóng">
            <X size={18} />
          </button>
        </div>
        <label className="search-box">
          <Search size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm kiếm mẫu..." />
        </label>
        <div className="template-layout">
          <div className="category-list">
            {categories.map((item) => (
              <button key={item} className={category === item ? "active" : ""} type="button" onClick={() => setCategory(item)}>
                {item}
              </button>
            ))}
          </div>
          <div className="template-grid">
            {filtered.map((template) => (
              <button
                key={template.id}
                className={selected?.id === template.id ? "template-card selected" : "template-card"}
                type="button"
                onClick={() => {
                  onSelect(template);
                  onClose();
                }}
              >
                <FileText size={20} />
                <span>{template.name}</span>
                <small>{template.category}</small>
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function FeedbackModal({ open, page, onClose }: { open: boolean; page: string; onClose: () => void }) {
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation">
      <form
        className="modal narrow-modal"
        onSubmit={async (event) => {
          event.preventDefault();
          await sendFeedback({ message, email: email || undefined, page });
          setSent(true);
          setMessage("");
        }}
      >
        <div className="modal-header">
          <div>
            <h2>Gửi góp ý</h2>
            <p>Ghi nhận để hoàn thiện luồng pháp lý và dữ liệu.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Đóng">
            <X size={18} />
          </button>
        </div>
        {sent && <div className="notice success">Đã lưu góp ý.</div>}
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} required placeholder="Nội dung góp ý..." />
        <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email nếu muốn nhận phản hồi" />
        <div className="modal-actions">
          <button type="button" className="ghost-button" onClick={onClose}>
            Đóng
          </button>
          <button type="submit" className="primary-button" disabled={message.trim().length < 3}>
            Gửi
          </button>
        </div>
      </form>
    </div>
  );
}

function ChatPage() {
  const [mode, setMode] = useState<RetrievalMode>("hybrid_rag");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedLaws, setSelectedLaws] = useState<Law[]>([]);
  const [lawOpen, setLawOpen] = useState(false);

  const submit = async (question = input) => {
    const trimmed = question.trim();
    if (!trimmed) return;
    const userMessage: ChatMessage = { id: uid(), role: "user", content: trimmed };
    const assistantId = uid();
    setMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: "assistant", content: "Đang tra cứu căn cứ pháp lý...", pending: true },
    ]);
    setInput("");
    try {
      const data: ChatResponse = await askLegalQuestion({
        message: trimmed,
        backend: mode,
        law_ids: selectedLaws.map((law) => law.id),
      });
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: data.answer, sources: data.sources, pending: false }
            : message,
        ),
      );
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: `Lỗi: ${(error as Error).message}`, pending: false }
            : message,
        ),
      );
    }
  };

  return (
    <section className="chat-page">
      <div className="chat-scroll">
        {messages.length === 0 ? (
          <div className="welcome">
            <button className="help-button" type="button" aria-label="Xem hướng dẫn">
              <Sparkles size={18} />
            </button>
            <div className="welcome-mark">
              <Scale size={30} />
            </div>
            <h1>Đừng ngần ngại, đặt câu hỏi cho VLegal AI ngay.</h1>
            <div className="suggestion-grid">
              {sampleQuestions.map((question) => (
                <button key={question} type="button" onClick={() => submit(question)}>
                  <MessageSquareText size={18} />
                  <span>{question}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="messages">
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                {message.role === "assistant" && <div className="avatar">AI</div>}
                <div className="bubble">
                  <div dangerouslySetInnerHTML={{ __html: markdown(message.content) }} />
                  {message.pending && <div className="loading-line" />}
                  <SourcePanel sources={message.sources} />
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="composer-toolbar">
          <ModePicker value={mode} onChange={setMode} />
          <button className="law-button" type="button" onClick={() => setLawOpen(true)}>
            <BookOpen size={16} />
            <span>Luật áp dụng</span>
            {selectedLaws.length > 0 && <strong>{selectedLaws.length}</strong>}
          </button>
        </div>
        <div className="input-wrap">
          <textarea
            value={input}
            maxLength={5000}
            rows={1}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Nhập câu hỏi..."
          />
          <span className="counter">{input.length} / 5000</span>
          <button className="primary-icon" type="submit" disabled={!input.trim()}>
            <SendHorizontal size={18} />
          </button>
        </div>
      </form>
      <LawPicker open={lawOpen} selected={selectedLaws} onApply={setSelectedLaws} onClose={() => setLawOpen(false)} />
    </section>
  );
}

function ContractPage() {
  const [mode, setMode] = useState<RetrievalMode>("hybrid_rag");
  const [step, setStep] = useState<"start" | "create" | "edit">("start");
  const [prompt, setPrompt] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState<Template | undefined>(templates[0]);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [lawOpen, setLawOpen] = useState(false);
  const [selectedLaws, setSelectedLaws] = useState<Law[]>([]);
  const [result, setResult] = useState<DraftResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<DraftResponse[]>([]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!prompt.trim()) return;
    setLoading(true);
    try {
      const data = await draftContract({
        prompt: step === "edit" ? `Chỉnh sửa văn bản theo yêu cầu sau: ${prompt}` : prompt,
        template_id: selectedTemplate?.id,
        template_name: selectedTemplate?.name,
        backend: mode,
        law_ids: selectedLaws.map((law) => law.id),
      });
      setResult(data);
      setHistory((current) => [data, ...current].slice(0, 6));
    } finally {
      setLoading(false);
    }
  };

  if (step === "start") {
    return (
      <section className="tool-page">
        <PageHeader
          title="Tạo hợp đồng"
          subtitle="Soạn hoặc chỉnh sửa văn bản bằng mô tả tự do, mẫu hợp đồng và căn cứ GraphRAG."
          action={<button className="ghost-button"><History size={16} />Lịch sử</button>}
        />
        <div className="choice-grid">
          <button className="choice-card" type="button" onClick={() => setStep("create")}>
            <Plus size={30} />
            <h3>Tạo mới</h3>
            <p>Tạo hợp đồng, văn bản bằng cách mô tả yêu cầu hoặc chọn từ kho mẫu.</p>
            <span>Kho hợp đồng, văn bản mẫu</span>
          </button>
          <button className="choice-card" type="button" onClick={() => setStep("edit")}>
            <FilePenLine size={30} />
            <h3>Chỉnh sửa</h3>
            <p>Dán nội dung hiện có và mô tả yêu cầu chỉnh sửa trực tiếp.</p>
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="tool-page split-page">
      <div>
        <div className="inline-actions">
          <button className="ghost-button" type="button" onClick={() => setStep("start")}>
            <ArrowLeft size={16} /> Quay lại
          </button>
          <ModePicker value={mode} onChange={setMode} />
        </div>
        <form className="tool-form" onSubmit={submit}>
          <p>
            {step === "create" ? "Hãy mô tả văn bản cần tạo. Hoặc chọn " : "Dán văn bản và mô tả điểm cần chỉnh sửa. Có thể chọn "}
            <button type="button" className="link-button" onClick={() => setTemplateOpen(true)}>
              hợp đồng, văn bản mẫu
            </button>
          </p>
          <div className="template-pill">
            <FileText size={16} />
            {selectedTemplate?.name || "Chưa chọn mẫu"}
          </div>
          <textarea
            value={prompt}
            maxLength={5000}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={step === "create" ? "Mô tả hợp đồng hoặc văn bản bạn muốn tạo..." : "Dán nội dung và yêu cầu chỉnh sửa..."}
          />
          <div className="form-footer">
            <label className="ghost-button file-button">
              <Upload size={16} />
              Tải file .txt
              <input
                type="file"
                accept=".txt,.md"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (file) setPrompt(await readTextFile(file));
                }}
              />
            </label>
            <button className="law-button" type="button" onClick={() => setLawOpen(true)}>
              <BookOpen size={16} /> Luật áp dụng {selectedLaws.length ? `(${selectedLaws.length})` : ""}
            </button>
            <span className="counter">{prompt.length} / 5000</span>
            <button className="primary-button" type="submit" disabled={loading || !prompt.trim()}>
              {loading ? "Đang tạo..." : "Tạo bản nháp"}
            </button>
          </div>
        </form>
        {history.length > 0 && (
          <div className="history-strip">
            {history.map((item, index) => (
              <button key={`${item.title}-${index}`} type="button" onClick={() => setResult(item)}>
                <Clock size={14} /> {item.title}
              </button>
            ))}
          </div>
        )}
      </div>
      <ResultPanel
        title={result?.title || "Bản nháp sẽ hiển thị tại đây"}
        text={result?.draft || "Sau khi gửi yêu cầu, hệ thống sẽ tạo bản nháp có cấu trúc, checklist và căn cứ pháp lý liên quan."}
        sources={result?.sources}
        checklist={result?.checklist}
      />
      <TemplateModal open={templateOpen} selected={selectedTemplate} onSelect={setSelectedTemplate} onClose={() => setTemplateOpen(false)} />
      <LawPicker open={lawOpen} selected={selectedLaws} onApply={setSelectedLaws} onClose={() => setLawOpen(false)} />
    </section>
  );
}

function ReviewPage() {
  const [mode, setMode] = useState<RetrievalMode>("hybrid_rag");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <section className="tool-page split-page">
      <div>
        <PageHeader title="Review hợp đồng" subtitle="Rà soát rủi ro, điều khoản thiếu và căn cứ cần đối chiếu." action={<ModePicker value={mode} onChange={setMode} />} />
        <form
          className="tool-form"
          onSubmit={async (event) => {
            event.preventDefault();
            setLoading(true);
            try {
              setResult(await reviewContract({ title, text, backend: mode }));
            } finally {
              setLoading(false);
            }
          }}
        >
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Tên hợp đồng" />
          <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Dán nội dung hợp đồng cần review..." />
          <div className="form-footer">
            <label className="ghost-button file-button">
              <Upload size={16} /> Tải file .txt
              <input
                type="file"
                accept=".txt,.md"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (file) setText(await readTextFile(file));
                }}
              />
            </label>
            <button className="primary-button" disabled={loading || text.trim().length < 20}>
              {loading ? "Đang rà soát..." : "Review hợp đồng"}
            </button>
          </div>
        </form>
      </div>
      <div className="result-panel">
        <h2>Kết quả rà soát</h2>
        <div className="markdown" dangerouslySetInnerHTML={{ __html: markdown(result?.summary || "Kết quả review sẽ hiển thị sau khi bạn gửi văn bản.") }} />
        <RiskList risks={result?.risks} />
        {result?.recommendations && (
          <ul className="checklist">
            {result.recommendations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        <SourcePanel sources={result?.sources} />
      </div>
    </section>
  );
}

function ComparePage() {
  const [mode, setMode] = useState<RetrievalMode>("hybrid_rag");
  const [original, setOriginal] = useState("");
  const [revised, setRevised] = useState("");
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <section className="tool-page">
      <PageHeader
        title="So sánh hợp đồng"
        subtitle="Tải lên hoặc dán hai phiên bản để tìm điểm khác biệt và rủi ro ở bản mới."
        action={<ModePicker value={mode} onChange={setMode} />}
      />
      <form
        className="compare-grid"
        onSubmit={async (event) => {
          event.preventDefault();
          setLoading(true);
          try {
            setResult(await compareContracts({ original_text: original, revised_text: revised, backend: mode }));
          } finally {
            setLoading(false);
          }
        }}
      >
        <DocumentInput title="Bản gốc" value={original} onChange={setOriginal} />
        <DocumentInput title="Bản mới" value={revised} onChange={setRevised} />
        <div className="compare-actions">
          <button className="ghost-button" type="button" onClick={() => { setOriginal(""); setRevised(""); setResult(null); }}>
            Làm mới
          </button>
          <button className="primary-button" disabled={loading || original.length < 20 || revised.length < 20}>
            {loading ? "Đang so sánh..." : "So sánh"}
          </button>
        </div>
      </form>
      {result && (
        <section className="compare-result">
          <h2>{result.summary}</h2>
          <div className="diff-list">
            {result.differences.map((diff, index) => (
              <article key={`${diff.type}-${index}`}>
                <span>{diff.type}</span>
                <div>
                  <strong>Trước</strong>
                  <p>{diff.before}</p>
                </div>
                <div>
                  <strong>Sau</strong>
                  <p>{diff.after}</p>
                </div>
              </article>
            ))}
          </div>
          <RiskList risks={result.risks} />
          <p className="notice">{result.recommendation}</p>
          <SourcePanel sources={result.sources} />
        </section>
      )}
    </section>
  );
}

function SignPage() {
  const [title, setTitle] = useState("");
  const [documentText, setDocumentText] = useState("");
  const [signers, setSigners] = useState("Nguyễn Văn A\nCông ty TNHH ABC");
  const [result, setResult] = useState<SignatureResponse | null>(null);

  return (
    <section className="tool-page split-page">
      <div>
        <PageHeader title="Ký văn bản" subtitle="Chuẩn bị gói ký, danh sách người ký và hash tài liệu để lưu vết." />
        <form
          className="tool-form"
          onSubmit={async (event) => {
            event.preventDefault();
            setResult(
              await prepareSignature({
                title,
                document_text: documentText,
                signers: signers.split(/\n|,/).map((item) => item.trim()).filter(Boolean),
              }),
            );
          }}
        >
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Tên văn bản" />
          <textarea value={documentText} onChange={(event) => setDocumentText(event.target.value)} placeholder="Dán nội dung hoặc tải file cần ký..." />
          <textarea className="short-textarea" value={signers} onChange={(event) => setSigners(event.target.value)} placeholder="Mỗi người ký một dòng" />
          <div className="form-footer">
            <label className="ghost-button file-button">
              <Upload size={16} /> Tải file .txt
              <input
                type="file"
                accept=".txt,.md"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    setTitle(title || file.name);
                    setDocumentText(await readTextFile(file));
                  }
                }}
              />
            </label>
            <button className="primary-button" disabled={title.length < 2 || documentText.length < 5}>
              Bắt đầu ký văn bản mới
            </button>
          </div>
        </form>
      </div>
      <div className="result-panel">
        <h2>{result ? `Gói ký ${result.signature_id}` : "Gói ký sẽ hiển thị tại đây"}</h2>
        {result ? (
          <>
            <div className="hash-box">{result.document_hash}</div>
            <div className="signer-list">
              {result.signers.map((signer) => (
                <span key={signer}>{signer}</span>
              ))}
            </div>
            <ul className="timeline">
              {result.audit_log.map((item) => (
                <li key={`${item.time}-${item.event}`}>
                  <strong>{item.actor}</strong>
                  <span>{item.event}</span>
                </li>
              ))}
            </ul>
            <ul className="checklist">
              {result.next_steps.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </>
        ) : (
          <p className="muted">Tính năng này tạo gói ký nội bộ demo, chưa tích hợp nhà cung cấp chữ ký số/OAuth.</p>
        )}
      </div>
    </section>
  );
}

function ArticlesPage({ navigate }: { navigate: (path: string) => void }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Tất cả");
  const [selected, setSelected] = useState<Article | null>(null);
  const categories = ["Tất cả", ...Array.from(new Set(articles.map((article) => article.category)))];
  const filtered = articles.filter((article) => {
    const inCategory = category === "Tất cả" || article.category === category;
    const inQuery = !query || `${article.title} ${article.excerpt}`.toLowerCase().includes(query.toLowerCase());
    return inCategory && inQuery;
  });

  return (
    <section className="articles-page">
      <div className="article-main">
        <PageHeader title="Bài viết mới nhất" subtitle="Chia sẻ kiến thức pháp luật, tin tức pháp lý và hướng dẫn hữu ích." />
        {selected ? (
          <article className="article-detail">
            <button className="ghost-button" type="button" onClick={() => setSelected(null)}>
              <ArrowLeft size={16} /> Quay lại
            </button>
            <span className="tag">{selected.category}</span>
            <h1>{selected.title}</h1>
            <p>{selected.excerpt}</p>
            <div className="article-body">
              <p>VLegal AI có thể dùng nội dung này làm điểm khởi đầu để tra cứu căn cứ pháp lý, tạo mẫu văn bản hoặc review hợp đồng liên quan.</p>
              <p>Với vụ việc cụ thể, bạn nên đối chiếu thêm tài liệu gốc, thời điểm hiệu lực và dữ kiện thực tế trước khi áp dụng.</p>
            </div>
            <button className="primary-button" type="button" onClick={() => navigate("/")}>
              Hỏi AI về chủ đề này
            </button>
          </article>
        ) : (
          <div className="article-list">
            {filtered.map((article) => (
              <button key={article.id} className="article-card" type="button" onClick={() => setSelected(article)}>
                <div className="article-thumb">
                  <FileText size={26} />
                  <span>{article.category}</span>
                </div>
                <div>
                  <h2>{article.title}</h2>
                  <p>{article.excerpt}</p>
                  <small>{article.date} • {article.views} lượt xem</small>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
      <aside className="article-sidebar">
        <label className="search-box">
          <Search size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm kiếm bài viết..." />
        </label>
        <div className="sidebar-box">
          <h3>Chuyên mục</h3>
          {categories.map((item) => (
            <button key={item} className={category === item ? "active" : ""} type="button" onClick={() => setCategory(item)}>
              {item}
            </button>
          ))}
        </div>
        <div className="sidebar-box">
          <h3>Công cụ</h3>
          <button type="button" onClick={() => navigate("/tao-hop-dong")}>Tạo hợp đồng</button>
          <button type="button" onClick={() => navigate("/phan-tich-hop-dong")}>Phân tích hợp đồng</button>
          <button type="button" onClick={() => navigate("/so-sanh-hop-dong")}>So sánh hợp đồng</button>
        </div>
      </aside>
    </section>
  );
}

function AboutPage() {
  return (
    <section className="about-page">
      <h2>VLEGAL AI VÀ CAM KẾT</h2>
      <article>
        <h3>Giới thiệu VLegal AI</h3>
        <p>
          VLegal AI là ứng dụng hỗ trợ pháp lý thông minh, kết hợp GraphRAG trên văn bản pháp luật Việt Nam và các công cụ tạo, rà soát, so sánh văn bản.
        </p>
      </article>
      <article>
        <h3>Dịch vụ chính</h3>
        <ul>
          <li><strong>Hỏi đáp pháp luật:</strong> đặt câu hỏi và nhận trả lời có căn cứ nguồn.</li>
          <li><strong>Tạo hợp đồng:</strong> soạn bản nháp theo mô tả, mẫu và văn bản ưu tiên.</li>
          <li><strong>Rà soát hợp đồng:</strong> cảnh báo rủi ro, điều khoản thiếu và đề xuất sửa đổi.</li>
          <li><strong>So sánh hợp đồng:</strong> tìm điểm khác biệt giữa hai phiên bản.</li>
          <li><strong>Ký văn bản:</strong> chuẩn bị gói ký, người ký và hash tài liệu để lưu vết.</li>
        </ul>
      </article>
      <article>
        <h3>Cam kết bảo mật</h3>
        <p>Dữ liệu người dùng cần được bảo vệ theo quy trình nội bộ. Không chia sẻ nội dung hợp đồng hoặc hồ sơ pháp lý cho bên thứ ba nếu chưa có căn cứ hợp pháp.</p>
      </article>
      <article>
        <h3>Lưu ý quan trọng</h3>
        <p>AI không thay thế luật sư. Với giao dịch có giá trị lớn hoặc tranh chấp phức tạp, hãy rà soát cùng chuyên gia pháp lý trước khi ký hoặc nộp hồ sơ.</p>
      </article>
    </section>
  );
}

function PageHeader({ title, subtitle, action }: { title: string; subtitle: string; action?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
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
}: {
  title: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="document-input">
      <span>{title}</span>
      <textarea value={value} onChange={(event) => onChange(event.target.value)} placeholder={`Dán nội dung ${title.toLowerCase()}...`} />
      <label className="ghost-button file-button">
        <Upload size={16} /> Tải file .txt
        <input
          type="file"
          accept=".txt,.md"
          onChange={async (event) => {
            const file = event.target.files?.[0];
            if (file) onChange(await readTextFile(file));
          }}
        />
      </label>
    </label>
  );
}

function ResultPanel({
  title,
  text,
  sources,
  checklist,
}: {
  title: string;
  text: string;
  sources?: Source[];
  checklist?: string[];
}) {
  return (
    <div className="result-panel">
      <div className="result-header">
        <h2>{title}</h2>
        <button className="icon-button" type="button" onClick={() => navigator.clipboard?.writeText(text)} aria-label="Sao chép">
          <Copy size={17} />
        </button>
      </div>
      <div className="markdown" dangerouslySetInnerHTML={{ __html: markdown(text) }} />
      {checklist && (
        <ul className="checklist">
          {checklist.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <SourcePanel sources={sources} />
    </div>
  );
}

function App() {
  const [path, navigate] = usePath();
  const [collapsed, setCollapsed] = useState(() => window.innerWidth <= 820);
  const [dark, setDark] = useState(() => localStorage.getItem("vlegal-theme") === "dark");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [stats, setStats] = useState<StatsResponse | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("vlegal-theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    getStats().then(setStats).catch(() => setStats(null));
  }, []);

  const activeRoute = useMemo(
    () => routes.find((route) => route.path === path) || routes[0],
    [path],
  );

  const page = useMemo(() => {
    if (path === "/tao-hop-dong") return <ContractPage />;
    if (path === "/phan-tich-hop-dong") return <ReviewPage />;
    if (path === "/so-sanh-hop-dong") return <ComparePage />;
    if (path === "/ky-van-ban") return <SignPage />;
    if (path === "/bai-viet") return <ArticlesPage navigate={navigate} />;
    if (path === "/gioi-thieu") return <AboutPage />;
    return <ChatPage />;
  }, [path, navigate]);

  return (
    <div className="app-shell">
      <aside className={collapsed ? "sidebar collapsed" : "sidebar"}>
        <div className="brand-row">
          <button className="brand" type="button" onClick={() => navigate("/")}>
            <Scale size={25} />
            <span>VLegal AI</span>
          </button>
          <button className="icon-button" type="button" onClick={() => setCollapsed((value) => !value)} aria-label="Thu gọn sidebar">
            <AlignLeft size={18} />
          </button>
        </div>
        <nav className="nav-list">
          {routes.map((route) => {
            const Icon = route.icon;
            return (
              <button
                key={route.path}
                type="button"
                className={activeRoute.path === route.path ? "active" : ""}
                onClick={() => navigate(route.path)}
              >
                <Icon size={19} />
                <span>{route.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-meta">
          <div>
            <strong>{stats?.documents ?? "-"}</strong>
            <span>văn bản</span>
          </div>
          <div>
            <strong>{stats?.chunks ?? "-"}</strong>
            <span>chunks</span>
          </div>
        </div>
        <div className="sidebar-actions">
          <button type="button" onClick={() => setFeedbackOpen(true)}>
            <Bot size={17} />
            <span>Gửi góp ý</span>
          </button>
          <button type="button" className="login-button">
            <LogIn size={17} />
            <span>Đăng nhập Google</span>
          </button>
          <button type="button" onClick={() => setDark((value) => !value)}>
            {dark ? <Sun size={17} /> : <Moon size={17} />}
            <span>{dark ? "Chế độ sáng" : "Chế độ tối"}</span>
          </button>
        </div>
      </aside>
      <div className="content-shell">
        <header className="mobile-topbar">
          <button className="icon-button" type="button" onClick={() => setCollapsed((value) => !value)} aria-label="Mở menu">
            <Menu size={19} />
          </button>
          <strong>{activeRoute.label}</strong>
          <button className="icon-button" type="button" onClick={() => setDark((value) => !value)} aria-label="Đổi giao diện">
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </header>
        <main className="content">{page}</main>
      </div>
      <FeedbackModal open={feedbackOpen} page={path} onClose={() => setFeedbackOpen(false)} />
    </div>
  );
}

export default App;
