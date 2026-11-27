import type {
  AuditLogEntry,
  ChatHistoryMessage,
  ChatResponse,
  ChatSessionSummary,
  DocumentListItem,
  EvaluationRun,
  ReviewTask,
  SearchResponse,
  TokenResponse,
  UserProfile,
} from "@/types/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

async function apiFetch<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> {
  const { token, headers, ...rest } = options;
  const reqHeaders = new Headers(headers);
  if (token) {
    reqHeaders.set("Authorization", `Bearer ${token}`);
  }
  if (!(rest.body instanceof FormData) && !reqHeaders.has("Content-Type")) {
    reqHeaders.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: reqHeaders,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const apiClient = {
  login: (email: string, password: string) =>
    apiFetch<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  guestLogin: () =>
    apiFetch<TokenResponse>("/api/v1/auth/guest", {
      method: "POST",
    }),

  me: (token: string) =>
    apiFetch<UserProfile>("/api/v1/auth/me", { token }),

  chat: (token: string, query: string, department?: string, sessionId?: string | null) =>
    apiFetch<ChatResponse>("/api/v1/chat", {
      method: "POST",
      token,
      body: JSON.stringify({
        query,
        department: department || null,
        session_id: sessionId || null,
      }),
    }),

  listChatSessions: (token: string) =>
    apiFetch<ChatSessionSummary[]>("/api/v1/chat/sessions", { token }),

  getChatSession: (token: string, sessionId: string) =>
    apiFetch<ChatHistoryMessage[]>(`/api/v1/chat/sessions/${sessionId}`, { token }),

  deleteChatSession: async (token: string, sessionId: string) => {
    const res = await fetch(`${API_BASE}/api/v1/chat/sessions/${sessionId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  },

  search: (token: string, query: string, department?: string) =>
    apiFetch<SearchResponse>("/api/v1/search", {
      method: "POST",
      token,
      body: JSON.stringify({
        query,
        department: department || null,
      }),
    }),

  uploadDocument: (
    token: string,
    file: File,
    title: string,
    department: string
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    form.append("department", department);
    return apiFetch<{ document_id: string; version_id: string; status: string }>(
      "/api/v1/documents",
      { method: "POST", token, body: form }
    );
  },

  listDocuments: (token: string) =>
    apiFetch<DocumentListItem[]>("/api/v1/documents", { token }),

  listEvaluations: (token: string) =>
    apiFetch<EvaluationRun[]>("/api/v1/evaluations", { token }),

  runEvaluation: (
    token: string,
    payload: {
      experiment_name: string;
      dataset_name: string;
      top_k: number;
      cases: Array<{
        case_id: string;
        query: string;
        expected_document_ids: string[];
        should_abstain: boolean;
      }>;
    }
  ) =>
    apiFetch<EvaluationRun>("/api/v1/evaluations/run", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  listReviews: (token: string) =>
    apiFetch<ReviewTask[]>("/api/v1/reviews", { token }),

  createReview: (
    token: string,
    query: string,
    proposedAnswer: string,
    abstentionReason: string | null
  ) =>
    apiFetch<ReviewTask>("/api/v1/reviews", {
      method: "POST",
      token,
      body: JSON.stringify({
        query,
        proposed_answer: proposedAnswer,
        abstention_reason: abstentionReason,
        escalate: true,
      }),
    }),

  resolveReview: (
    token: string,
    reviewId: string,
    decision: "approved" | "rejected"
  ) =>
    apiFetch<ReviewTask>(`/api/v1/reviews/${reviewId}/resolve`, {
      method: "POST",
      token,
      body: JSON.stringify({ decision }),
    }),

  submitFeedback: (
    token: string,
    query: string,
    rating: "positive" | "negative"
  ) =>
    apiFetch("/api/v1/feedback", {
      method: "POST",
      token,
      body: JSON.stringify({ query, rating }),
    }),

  listAuditLogs: (token: string) =>
    apiFetch<AuditLogEntry[]>("/api/v1/audit-logs", { token }),
};
