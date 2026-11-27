export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserProfile {
  user_id: string;
  email: string;
  department: string;
  roles: string[];
}

export interface Citation {
  citation_key: string;
  chunk_id: string;
  document_id: string;
  version_id: string;
  title: string;
  section_path: string | null;
  page_numbers: number[];
  score: number;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ChatResponse {
  query: string;
  answer: string;
  abstained: boolean;
  abstention_reason: string | null;
  citations: Citation[];
  model: string;
  provider: string;
  prompt_version: string;
  used_fallback: boolean;
  usage: TokenUsage;
  latency_ms: number;
  request_id: string;
  session_id?: string | null;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatHistoryMessage {
  id: string;
  query: string;
  answer: string;
  abstained: boolean;
  abstention_reason: string | null;
  citations: Citation[];
  model: string;
  provider: string;
  prompt_version: string;
  total_tokens: number;
  latency_ms: number;
  created_at: string;
}

export interface RetrievalHit {
  chunk_id: string;
  document_id: string;
  version_id: string;
  chunk_index: number;
  title: string;
  content: string;
  section_path: string | null;
  department: string;
  page_numbers: number[];
  score: number;
}

export interface SearchResponse {
  query: string;
  candidate_count: number;
  results: RetrievalHit[];
  request_id: string;
}

export interface EvaluationRun {
  run_id: string | null;
  experiment_name: string;
  dataset_name: string;
  status: string;
  total_cases: number;
  precision_at_k: number;
  recall_at_k: number;
  mrr: number;
  ndcg_at_k: number;
  citation_correctness: number;
  abstention_accuracy: number;
  avg_latency_ms: number;
  total_tokens: number;
  created_at: string | null;
}

export interface ReviewTask {
  id: string;
  query: string;
  proposed_answer: string;
  abstention_reason: string | null;
  status: string;
  reviewer_notes: string | null;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  request_id: string | null;
  user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: string;
  created_at: string;
}

export interface DocumentListItem {
  document_id: string;
  title: string;
  department: string;
  latest_version_id: string | null;
  version_number: number | null;
  filename: string | null;
  status: string | null;
  expected_chunks: number;
  indexed_chunks: number;
  error_message: string | null;
}
