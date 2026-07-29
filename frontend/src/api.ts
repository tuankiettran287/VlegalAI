import type {
  Article,
  Artifact,
  ChatMessage,
  Conversation,
  Risk,
  Source,
  Template,
  User,
  VerificationItem,
  VerificationReport,
  WebSource,
} from "./types";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const configuredApiOrigin = (import.meta.env.VITE_API_URL || "").trim().replace(/\/$/, "");

function apiUrl(path: string) {
  if (configuredApiOrigin) return `${configuredApiOrigin}${path}`;
  if (import.meta.env.DEV && typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000${path}`;
  }
  return path;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(url), {
      credentials: "include",
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
    });
  } catch {
    throw new ApiError("Tính năng này đang tạm gián đoạn. Vui lòng thử lại sau.", 0, "UNAVAILABLE");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fallback = response.status === 401
      ? "Vui lòng đăng nhập để tiếp tục."
      : response.status === 403
        ? "Bạn chưa có quyền thực hiện thao tác này."
        : response.status === 404
          ? "Không tìm thấy nội dung yêu cầu."
          : response.status === 429
            ? "Bạn thao tác quá nhanh. Vui lòng thử lại sau ít phút."
            : response.status >= 500
              ? "Tính năng này đang tạm gián đoạn. Vui lòng thử lại sau."
              : "Yêu cầu chưa thể hoàn tất. Vui lòng kiểm tra và thử lại.";
    const safeDetail = data.detail || data.message;
    throw new ApiError(typeof safeDetail === "string" ? safeDetail : fallback, response.status, data.code);
  }
  return data as T;
}

function post<T>(url: string, body: unknown) {
  return requestJson<T>(url, { method: "POST", body: JSON.stringify(body) });
}

function patch<T>(url: string, body: unknown) {
  return requestJson<T>(url, { method: "PATCH", body: JSON.stringify(body) });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const verificationStatuses = new Set<VerificationItem["status"]>([
  "IN_FORCE",
  "PARTIALLY_IN_FORCE",
  "AMENDED",
  "EXPIRED",
  "REPLACED",
  "UNKNOWN",
]);

function normalizeSources(value: unknown): Source[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item, index) => {
    if (!isRecord(item)) return [];
    return [{
      source_id: typeof item.source_id === "string" ? item.source_id : `S${index + 1}`,
      score: typeof item.score === "number" && Number.isFinite(item.score) ? item.score : 0,
      chunk_type: typeof item.chunk_type === "string" ? item.chunk_type : "",
      citation: typeof item.citation === "string" ? item.citation : "",
      title: typeof item.title === "string" ? item.title : "",
      text: typeof item.text === "string" ? item.text : "",
      reasons: Array.isArray(item.reasons)
        ? item.reasons.filter((reason): reason is string => typeof reason === "string")
        : [],
      doc_id: typeof item.doc_id === "string" ? item.doc_id : null,
      source_url: typeof item.source_url === "string" ? item.source_url : null,
    }];
  });
}

function normalizeVerification(value: unknown): VerificationReport | undefined {
  if (!isRecord(value) || Object.keys(value).length === 0) return undefined;
  const items: VerificationItem[] = Array.isArray(value.items)
    ? value.items.flatMap((item) => {
        if (!isRecord(item)) return [];
        const rawStatus = typeof item.status === "string" ? item.status : "UNKNOWN";
        const status = verificationStatuses.has(rawStatus as VerificationItem["status"])
          ? rawStatus as VerificationItem["status"]
          : "UNKNOWN";
        return [{
          code: typeof item.code === "string" ? item.code : "",
          title: typeof item.title === "string" ? item.title : "",
          status,
          checked_at: typeof item.checked_at === "string" ? item.checked_at : "",
          source_url: typeof item.source_url === "string" ? item.source_url : null,
          replacement_code: typeof item.replacement_code === "string" ? item.replacement_code : null,
          index_updated: Boolean(item.index_updated),
        }];
      })
    : [];

  return {
    checked: Boolean(value.checked),
    all_current: Boolean(value.all_current),
    checked_at: typeof value.checked_at === "string" ? value.checked_at : null,
    items,
    note: typeof value.note === "string" ? value.note : "",
  };
}

function normalizeConversationMessages(value: unknown, conversationId: string): ChatMessage[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item, index) => {
    if (!isRecord(item)) return [];
    const role = typeof item.role === "string" ? item.role.toLowerCase() : "";
    if (role !== "user" && role !== "assistant") return [];
    const sources = normalizeSources(item.sources);
    const verification = normalizeVerification(item.verification);
    return [{
      id: typeof item.id === "string" ? item.id : `${conversationId}-${index}`,
      conversation_id: typeof item.conversation_id === "string" ? item.conversation_id : conversationId,
      role,
      content: typeof item.content === "string" ? item.content : "",
      sources: sources.length ? sources : undefined,
      verification,
      created_at: typeof item.created_at === "string" ? item.created_at : undefined,
    }];
  });
}

export const authApi = {
  capabilities: () => requestJson<{ google_login: boolean }>("/api/auth/capabilities"),
  me: () => requestJson<User>("/api/auth/me"),
  loginUrl: (returnTo = typeof window !== "undefined" ? window.location.pathname : "/") => apiUrl(`/api/auth/google/login?return_to=${encodeURIComponent(returnTo)}`),
  logout: () => requestJson<void>("/api/auth/logout", { method: "POST" }),
};

export const conversationApi = {
  list: () => requestJson<Conversation[]>("/api/conversations"),
  create: (title = "Cuộc trò chuyện mới") => post<Conversation>("/api/conversations", { title }),
  get: async (id: string) => {
    const data = await requestJson<{
      conversation: Conversation;
      messages: unknown;
    }>(`/api/conversations/${id}`);
    return {
      conversation: data.conversation,
      messages: normalizeConversationMessages(data.messages, id),
    };
  },
  update: (id: string, body: Partial<Pick<Conversation, "title" | "status">>) =>
    patch<Conversation>(`/api/conversations/${id}`, body),
  remove: (id: string) => requestJson<void>(`/api/conversations/${id}`, { method: "DELETE" }),
};

export type ChatResponse = {
  conversation_id: string | null;
  message_id: string;
  answer: string;
  sources: Source[];
  verification: VerificationReport;
  temporary: boolean;
  cache_hit: boolean;
  cache_similarity: number | null;
  cache_mode: "miss" | "exact" | "semantic_draft" | "scope_clarification";
};

export function askLegalQuestion(
  message: string,
  conversationId?: string | null,
  history: Array<{ role: "user" | "assistant"; content: string }> = [],
) {
  return post<ChatResponse>("/api/chat", { message, conversation_id: conversationId || null, history });
}

export type DraftResponse = {
  artifact_id: string;
  title: string;
  draft: string;
  checklist: string[];
  sources: Source[];
  verification: VerificationReport;
};

export function draftContract(payload: { prompt: string; template_id?: string; template_name?: string }) {
  return post<DraftResponse>("/api/contracts/draft", payload);
}

export type ReviewResponse = {
  artifact_id: string;
  summary: string;
  risks: Risk[];
  recommendations: string[];
  sources: Source[];
  verification: VerificationReport;
};

export function reviewContract(payload: { title?: string; text: string }) {
  return post<ReviewResponse>("/api/contracts/review", payload);
}

export type CompareResponse = {
  artifact_id: string;
  summary: string;
  similarity: number;
  differences: Array<{
    type: string;
    before: string;
    after: string;
    legal_impact: string;
    citations: string[];
  }>;
  risks: Risk[];
  recommendation: string;
  sources: Source[];
  verification: VerificationReport;
};

export function compareContracts(payload: {
  original_title?: string;
  revised_title?: string;
  original_text: string;
  revised_text: string;
}) {
  return post<CompareResponse>("/api/contracts/compare", payload);
}

export const artifactApi = {
  list: (kind?: string) => requestJson<Artifact[]>(`/api/artifacts${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`),
  update: (id: string, body: Partial<Pick<Artifact, "title" | "content" | "status">>) =>
    patch<Artifact>(`/api/artifacts/${id}`, body),
  remove: (id: string) => requestJson<void>(`/api/artifacts/${id}`, { method: "DELETE" }),
};

export type SignatureResponse = {
  signature_id: string;
  title: string;
  status: string;
  document_hash: string;
  signers: string[];
  audit_log: Array<{ time: string; event: string; actor: string }>;
  next_steps: string[];
};

export function prepareSignature(payload: { title: string; document_text: string; signers: string[] }) {
  return post<SignatureResponse>("/api/signatures/prepare", payload);
}

export const articleApi = {
  list: (query = "") => requestJson<{ items: Article[] }>(`/api/articles?q=${encodeURIComponent(query)}`),
  get: (slug: string) => requestJson<Article>(`/api/articles/${encodeURIComponent(slug)}`),
  webSearch: (query: string, save = false) =>
    post<{
      query: string;
      summary: string;
      sources: WebSource[];
      providers_used: string[];
      search_warnings: string[];
      google_search_entry_point?: string | null;
      article?: Article;
    }>("/api/articles/web-search", { query, save }),
};

export function getTemplates() {
  return requestJson<{ items: Template[]; categories: string[] }>("/api/templates");
}

export function sendFeedback(payload: { message: string; page?: string }) {
  return post<{ ok: boolean }>("/api/feedback", payload);
}
