import type {
  Article,
  Artifact,
  Conversation,
  Risk,
  Source,
  Template,
  User,
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
    const safeDetail = [400, 409, 422].includes(response.status)
      ? data.detail || data.message
      : undefined;
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

export const authApi = {
  capabilities: () => requestJson<{ google_login: boolean }>("/api/auth/capabilities"),
  me: () => requestJson<User>("/api/auth/me"),
  loginUrl: (returnTo = typeof window !== "undefined" ? window.location.pathname : "/") => apiUrl(`/api/auth/google/login?return_to=${encodeURIComponent(returnTo)}`),
  logout: () => requestJson<void>("/api/auth/logout", { method: "POST" }),
};

export const conversationApi = {
  list: () => requestJson<Conversation[]>("/api/conversations"),
  create: (title = "Cuộc trò chuyện mới") => post<Conversation>("/api/conversations", { title }),
  get: (id: string) =>
    requestJson<{
      conversation: Conversation;
      messages: Array<{
        id: string;
        conversation_id: string;
        role: "user" | "assistant";
        content: string;
        sources: Source[];
        verification: VerificationReport;
        created_at: string;
      }>;
    }>(`/api/conversations/${id}`),
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
  differences: Array<{ type: string; before: string; after: string; legal_impact: string }>;
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
    post<{ query: string; summary: string; sources: WebSource[]; article?: Article }>("/api/articles/web-search", {
      query,
      save,
    }),
};

export function getTemplates() {
  return requestJson<{ items: Template[]; categories: string[] }>("/api/templates");
}

export function sendFeedback(payload: { message: string; page?: string }) {
  return post<{ ok: boolean }>("/api/feedback", payload);
}
