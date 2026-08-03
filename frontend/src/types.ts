export type User = {
  id: string;
  email: string;
  display_name: string;
  preferred_name?: string | null;
  avatar_url?: string | null;
  role: string;
  onboarding_required: boolean;
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

export type ChatAttachment = {
  filename: string;
  content_type: string;
  kind: "image" | "document";
  size_bytes: number;
  page_count?: number | null;
  truncated: boolean;
  token?: string;
  preview?: string;
};

export type ChatMessage = {
  id: string;
  conversation_id?: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  verification?: VerificationReport;
  attachments?: ChatAttachment[];
  feedback_rating?: "good" | "bad" | null;
  pending?: boolean;
  typing?: boolean;
  regenerating?: boolean;
  created_at?: string;
};

export type Conversation = {
  id: string;
  title: string;
  status: "ACTIVE" | "ARCHIVED";
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type Risk = {
  level: "low" | "medium" | "high";
  title: string;
  detail: string;
  recommendation: string;
  citations: string[];
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
  providers?: string[];
};
