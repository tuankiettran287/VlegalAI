import type { Law, RetrievalMode, Risk, Source } from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || "Không gọi được API");
  }
  return data as T;
}

export function postJson<T>(url: string, body: unknown): Promise<T> {
  return requestJson<T>(url, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type ChatResponse = {
  answer: string;
  backend: string;
  mode_label: string;
  sources: Source[];
  selected_laws: Law[];
  groq_ready: boolean;
};

export function askLegalQuestion(payload: {
  message: string;
  backend: RetrievalMode;
  law_ids: string[];
}) {
  return postJson<ChatResponse>("/api/chat", {
    ...payload,
    top_k: 10,
  });
}

export async function searchLaws(query: string): Promise<Law[]> {
  const params = new URLSearchParams({ q: query, limit: "50" });
  const data = await requestJson<{ items: Law[] }>(`/api/laws/search?${params.toString()}`);
  return data.items;
}

export type DraftResponse = {
  title: string;
  draft: string;
  checklist: string[];
  backend: string;
  mode_label: string;
  sources: Source[];
  selected_laws: Law[];
};

export function draftContract(payload: {
  prompt: string;
  template_id?: string;
  template_name?: string;
  backend: RetrievalMode;
  law_ids: string[];
}) {
  return postJson<DraftResponse>("/api/contracts/draft", payload);
}

export type ReviewResponse = {
  summary: string;
  risks: Risk[];
  recommendations: string[];
  backend: string;
  mode_label: string;
  sources: Source[];
};

export function reviewContract(payload: { title?: string; text: string; backend: RetrievalMode }) {
  return postJson<ReviewResponse>("/api/contracts/review", payload);
}

export type CompareResponse = {
  summary: string;
  differences: Array<{ type: string; before: string; after: string }>;
  risks: Risk[];
  recommendation: string;
  backend: string;
  mode_label: string;
  sources: Source[];
};

export function compareContracts(payload: {
  original_title?: string;
  revised_title?: string;
  original_text: string;
  revised_text: string;
  backend: RetrievalMode;
}) {
  return postJson<CompareResponse>("/api/contracts/compare", payload);
}

export type SignatureResponse = {
  signature_id: string;
  title: string;
  status: string;
  document_hash: string;
  signers: string[];
  audit_log: Array<{ time: number; event: string; actor: string }>;
  next_steps: string[];
};

export function prepareSignature(payload: { title: string; document_text: string; signers: string[] }) {
  return postJson<SignatureResponse>("/api/signatures/prepare", payload);
}

export function sendFeedback(payload: { message: string; email?: string; page?: string }) {
  return postJson<{ ok: boolean }>("/api/feedback", payload);
}

export type StatsResponse = {
  documents?: number;
  nodes?: number;
  edges?: number;
  chunks?: number;
  mode_label?: string;
  groq_ready?: boolean;
  backend_error?: string;
};

export function getStats() {
  return requestJson<StatsResponse>("/api/stats?backend=local_graphrag");
}
