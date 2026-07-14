export type User = {
  id: string;
  email: string;
  display_name: string;
  avatar_url?: string | null;
  role: string;
};

export type Source = {
  source_id: string;
  score: number;
  chunk_type: string;
  citation: string;
  title: string;
  text: string;
  reasons: string[];
  doc_id?: string | null;
  source_url?: string | null;
};

export type VerificationItem = {
  code: string;
  title: string;
  status: "IN_FORCE" | "PARTIALLY_IN_FORCE" | "AMENDED" | "EXPIRED" | "REPLACED" | "UNKNOWN";
  checked_at: string;
  source_url?: string | null;
  replacement_code?: string | null;
  index_updated: boolean;
};

export type VerificationReport = {
  checked: boolean;
  all_current: boolean;
  checked_at?: string | null;
  items: VerificationItem[];
  note: string;
};

export type ChatMessage = {
  id: string;
  conversation_id?: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  verification?: VerificationReport;
  pending?: boolean;
  created_at?: string;
};

export type Conversation = {
  id: string;
  title: string;
  status: "ACTIVE" | "ARCHIVED";
  retrieval_mode: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type Risk = {
  level: "low" | "medium" | "high";
  title: string;
  detail: string;
  recommendation: string;
  citations?: string[];
};

export type Template = {
  id: string;
  name: string;
  category: string;
};

export type Artifact = {
  id: string;
  kind: string;
  title: string;
  content: string;
  metadata: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
};

export type Article = {
  id: string;
  slug: string;
  title: string;
  excerpt: string;
  content: string;
  category: string;
  status: string;
  source_url?: string | null;
  web_sources?: WebSource[];
  views: number;
  published_at?: string | null;
  created_at: string;
};

export type WebSource = {
  id: string;
  title: string;
  url: string;
  excerpt: string;
  published_date?: string | null;
  score: number;
};
