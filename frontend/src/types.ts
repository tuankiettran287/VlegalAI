export type Source = {
  source_id: string;
  score: number;
  chunk_type: string;
  citation: string;
  title: string;
  text: string;
  reasons: string[];
};

export type Law = {
  id: string;
  code: string;
  title: string;
  doc_type: string;
  issuer: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  pending?: boolean;
};

export type RetrievalMode = "rag" | "graphrag" | "hybrid_rag" | "local_graphrag";

export type Risk = {
  level: "low" | "medium" | "high" | string;
  title: string;
  detail: string;
  recommendation: string;
};

export type Template = {
  id: string;
  name: string;
  category: string;
};

export type Article = {
  id: string;
  title: string;
  excerpt: string;
  category: string;
  date: string;
  views: number;
};
