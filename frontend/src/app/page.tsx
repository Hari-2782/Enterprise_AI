"use client";

import { useEffect, useState } from "react";
import {
  BarChart3,
  Bot,
  Check,
  CheckCircle,
  Copy,
  FileText,
  FileUp,
  LogOut,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  User as UserIcon,
  X,
} from "lucide-react";
import { apiClient } from "@/lib/api";
import { MarkdownAnswer } from "@/components/MarkdownAnswer";
import type {
  AuditLogEntry,
  ChatResponse,
  ChatSessionSummary,
  DocumentListItem,
  EvaluationRun,
  ReviewTask,
  SearchResponse,
  UserProfile,
} from "@/types/api";

type Tab = "chat" | "documents" | "search" | "evaluations" | "governance";

interface ChatTurn {
  id: string;
  query: string;
  response: ChatResponse;
  feedbackSent?: "positive" | "negative";
  escalated?: boolean;
}

export default function HomePage() {
  const [token, setToken] = useState("");
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tab, setTab] = useState<Tab>("chat");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Chat workspace state
  const [chatQuery, setChatQuery] = useState("");
  const [department, setDepartment] = useState("");
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [chatHistory, setChatHistory] = useState<ChatTurn[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedCitationKey, setSelectedCitationKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);

  // Documents state
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDept, setUploadDept] = useState("HR");

  // Dashboards state
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [evalExperiment, setEvalExperiment] = useState("rag-baseline-v1");
  const [evalDataset, setEvalDataset] = useState("cv-smoke");
  const [evalQuery, setEvalQuery] = useState("What are the key AI engineering skills?");
  const [evalDocId, setEvalDocId] = useState("");
  const [evalShouldAbstain, setEvalShouldAbstain] = useState(false);
  const [reviews, setReviews] = useState<ReviewTask[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);

  useEffect(() => {
    if (token) {
      refreshDocuments(token);
      refreshSessions(token);
    }
  }, [token]);

  async function refreshDocuments(activeToken = token) {
    if (!activeToken) return;
    try {
      setDocuments(await apiClient.listDocuments(activeToken));
    } catch {
      // Ignore silent background refresh errors
    }
  }

  async function refreshSessions(activeToken = token) {
    if (!activeToken) return;
    try {
      setSessions(await apiClient.listChatSessions(activeToken));
    } catch {
      // Ignore silent background refresh errors
    }
  }

  async function loadSession(sessionId: string) {
    if (!token) return;
    setError(null);
    try {
      const msgs = await apiClient.getChatSession(token, sessionId);
      setActiveSessionId(sessionId);
      setTab("chat");
      setChatHistory(
        msgs.map((m) => ({
          id: m.id,
          query: m.query,
          response: {
            query: m.query,
            answer: m.answer,
            abstained: m.abstained,
            abstention_reason: m.abstention_reason,
            citations: m.citations,
            model: m.model,
            provider: m.provider,
            prompt_version: m.prompt_version,
            used_fallback: false,
            usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: m.total_tokens },
            latency_ms: m.latency_ms,
            request_id: m.id,
            session_id: sessionId,
          },
        }))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chat session");
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await apiClient.login(email, password);
      const me = await apiClient.me(res.access_token);
      setToken(res.access_token);
      setProfile(me);
      setNotice(`Signed in as ${me.email}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  async function handleGuestLogin() {
    setError(null);
    try {
      const res = await apiClient.guestLogin();
      const me = await apiClient.me(res.access_token);
      setToken(res.access_token);
      setProfile(me);
      setNotice("Signed in as Guest (Public read-only scope)");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Guest login failed");
    }
  }

  async function submitChatQuery(rawQuery: string) {
    if (!token || !rawQuery.trim()) return;
    const submittedQuery = rawQuery.trim();
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const res = await apiClient.chat(token, submittedQuery, department, activeSessionId);
      if (res.session_id && !activeSessionId) {
        setActiveSessionId(res.session_id);
      }
      setChatHistory((prev) => [
        ...prev,
        { id: res.request_id || `${Date.now()}`, query: submittedQuery, response: res },
      ]);
      setChatQuery("");
      await refreshSessions(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleChat(e: React.FormEvent) {
    e.preventDefault();
    await submitChatQuery(chatQuery);
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !searchQuery.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setSearchResult(await apiClient.search(token, searchQuery, department));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !uploadFile || !uploadTitle.trim()) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const res = await apiClient.uploadDocument(
        token,
        uploadFile,
        uploadTitle.trim(),
        uploadDept.trim()
      );
      setNotice(
        `Queued "${uploadTitle.trim()}" (${res.status}). Refreshing document status...`
      );
      setUploadTitle("");
      setUploadFile(null);
      await refreshDocuments(token);
      setTimeout(() => refreshDocuments(token), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleFeedback(turnId: string, query: string, rating: "positive" | "negative") {
    try {
      await apiClient.submitFeedback(token, query, rating);
      setChatHistory((prev) =>
        prev.map((t) => (t.id === turnId ? { ...t, feedbackSent: rating } : t))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feedback failed");
    }
  }

  async function handleEscalate(turn: ChatTurn) {
    try {
      await apiClient.createReview(
        token,
        turn.query,
        turn.response.answer,
        turn.response.abstention_reason
      );
      setChatHistory((prev) =>
        prev.map((t) => (t.id === turn.id ? { ...t, escalated: true } : t))
      );
      setNotice("Escalated response to Human Review queue.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Escalation failed");
    }
  }

  async function openEvaluations() {
    setTab("evaluations");
    if (!token) return;
    setError(null);
    try {
      const [runs, docs] = await Promise.all([
        apiClient.listEvaluations(token),
        apiClient.listDocuments(token).catch(() => []),
      ]);
      setEvaluations(runs);
      if (docs.length > 0 && !evalDocId) {
        setEvalDocId(docs[0].document_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evaluations");
    }
  }

  async function handleRunEvaluation(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !evalExperiment.trim() || !evalQuery.trim()) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const run = await apiClient.runEvaluation(token, {
        experiment_name: evalExperiment.trim(),
        dataset_name: evalDataset.trim() || "custom",
        top_k: 5,
        cases: [
          {
            case_id: "case-1",
            query: evalQuery.trim(),
            expected_document_ids: evalDocId.trim() ? [evalDocId.trim()] : [],
            should_abstain: evalShouldAbstain,
          },
        ],
      });
      setNotice(
        `Evaluation "${run.experiment_name}" complete — Recall@K: ${run.recall_at_k}, Citations: ${run.citation_correctness}`
      );
      setEvaluations(await apiClient.listEvaluations(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation run failed");
    } finally {
      setLoading(false);
    }
  }

  async function openGovernance() {
    setTab("governance");
    if (!token) return;
    setError(null);
    try {
      const [rev, logs] = await Promise.all([
        apiClient.listReviews(token).catch(() => []),
        apiClient.listAuditLogs(token).catch(() => []),
      ]);
      setReviews(rev);
      setAuditLogs(logs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load governance");
    }
  }

  if (!profile) {
    return (
      <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#070b14] p-6">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(99,102,241,0.18),_transparent_55%),radial-gradient(ellipse_at_bottom_right,_rgba(16,185,129,0.08),_transparent_50%)]" />
        <div className="relative w-full max-w-md space-y-6 rounded-2xl border border-white/10 bg-gray-900/75 p-8 shadow-2xl shadow-indigo-950/40 backdrop-blur-xl">
          <div className="space-y-3 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30">
              <Sparkles className="h-6 w-6" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Enterprise AI Intelligence
            </h1>
            <p className="text-sm leading-relaxed text-gray-400">
              Sign in with your corporate credentials to access grounded knowledge search &amp; AI chat.
            </p>
          </div>

          {error && (
            <div className="rounded-xl border border-red-500/30 bg-red-950/50 p-3 text-xs text-red-300">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-300">Email</label>
              <input
                type="email"
                placeholder="admin@enterprise.local"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-gray-950/80 px-3.5 py-2.5 text-sm text-white placeholder-gray-500 transition focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-300">Password</label>
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-gray-950/80 px-3.5 py-2.5 text-sm text-white placeholder-gray-500 transition focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                required
              />
            </div>
            <button
              type="submit"
              className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition hover:from-indigo-500 hover:to-violet-500"
            >
              Sign In
            </button>
          </form>

          <div className="relative flex items-center py-1">
            <div className="flex-grow border-t border-white/10" />
            <span className="mx-3 text-xs text-gray-500">or</span>
            <div className="flex-grow border-t border-white/10" />
          </div>

          <button
            type="button"
            onClick={handleGuestLogin}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 py-2.5 text-sm font-medium text-gray-200 transition hover:border-indigo-400/50 hover:bg-indigo-500/10 hover:text-white"
          >
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            Continue as Guest (Public Demo)
          </button>
        </div>
      </main>
    );
  }

  const isAdmin = profile.roles.includes("admin");
  const isGuest = profile.email === "guest@enterprise.local" || profile.department === "Public";
  const authorizedDepartments = Array.from(
    new Set([profile.department, ...documents.map((d) => d.department)].filter(Boolean))
  ) as string[];
  const defaultScopeLabel = isAdmin
    ? "All departments (Admin)"
    : authorizedDepartments.length <= 1
    ? `${profile.department} (Authorized only)`
    : `All authorized (${authorizedDepartments.join(", ")})`;

  return (
    <div className="flex min-h-screen bg-[#070b14] bg-[radial-gradient(ellipse_at_top_right,_rgba(99,102,241,0.10),_transparent_50%)] text-gray-100">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col justify-between border-r border-white/10 bg-gray-950/80 p-4 backdrop-blur-xl">
        <div className="space-y-6">
          <div className="flex items-center gap-3 px-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-md shadow-indigo-500/30">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight text-white">Enterprise AI</div>
              <div className="text-[11px] text-gray-400">OpenRouter · Azure RAG</div>
            </div>
          </div>

          <nav className="space-y-1">
            <button
              onClick={() => setTab("chat")}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                tab === "chat"
                  ? "bg-indigo-600 text-white"
                  : "text-gray-300 hover:bg-gray-900"
              }`}
            >
              <MessageSquare className="h-4 w-4" /> AI Assistant
            </button>
            <button
              onClick={() => {
                setTab("documents");
                refreshDocuments();
              }}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                tab === "documents"
                  ? "bg-indigo-600 text-white"
                  : "text-gray-300 hover:bg-gray-900"
              }`}
            >
              <FileUp className="h-4 w-4" /> Knowledge Base
              <span className="ml-auto rounded-full bg-gray-800 px-2 py-0.5 text-[11px] text-gray-300">
                {documents.length}
              </span>
            </button>
            <button
              onClick={() => setTab("search")}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                tab === "search"
                  ? "bg-indigo-600 text-white"
                  : "text-gray-300 hover:bg-gray-900"
              }`}
            >
              <Search className="h-4 w-4" /> Hybrid Search
            </button>
            <button
              onClick={openEvaluations}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                tab === "evaluations"
                  ? "bg-indigo-600 text-white"
                  : "text-gray-300 hover:bg-gray-900"
              }`}
            >
              <BarChart3 className="h-4 w-4" /> Evaluations
            </button>
            <button
              onClick={openGovernance}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                tab === "governance"
                  ? "bg-indigo-600 text-white"
                  : "text-gray-300 hover:bg-gray-900"
              }`}
            >
              <ShieldAlert className="h-4 w-4" /> Reviews &amp; Audit
            </button>
          </nav>

          {/* Persistent Chat History */}
          <div className="space-y-2 border-t border-gray-800/80 pt-4">
            <div className="flex items-center justify-between px-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Chat History
              </span>
              <button
                onClick={() => {
                  setActiveSessionId(null);
                  setChatHistory([]);
                  setTab("chat");
                }}
                className="flex items-center gap-1 rounded bg-gray-800 px-2 py-0.5 text-[11px] text-gray-200 hover:bg-gray-700"
              >
                <Plus className="h-3 w-3" /> New
              </button>
            </div>
            <div className="max-h-48 space-y-1 overflow-y-auto pr-1">
              {sessions.length === 0 ? (
                <p className="px-2 text-[11px] text-gray-500">No saved chats yet.</p>
              ) : (
                sessions.map((s) => (
                  <div
                    key={s.id}
                    className={`group flex items-center justify-between rounded-md px-2 py-1.5 text-xs transition ${
                      activeSessionId === s.id
                        ? "bg-gray-800 text-white"
                        : "text-gray-400 hover:bg-gray-900 hover:text-gray-200"
                    }`}
                  >
                    <button
                      onClick={() => loadSession(s.id)}
                      className="flex-1 truncate text-left"
                      title={s.title}
                    >
                      {s.title}
                    </button>
                    <button
                      onClick={async () => {
                        await apiClient.deleteChatSession(token, s.id);
                        if (activeSessionId === s.id) {
                          setActiveSessionId(null);
                          setChatHistory([]);
                        }
                        refreshSessions(token);
                      }}
                      className="ml-1 hidden text-gray-500 hover:text-red-400 group-hover:inline"
                      title="Delete session"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="space-y-3 border-t border-gray-800 pt-4">
          <div className="rounded-lg bg-gray-900 p-3 text-xs">
            <div className="flex items-center gap-1.5 font-medium text-white">
              <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
              {profile.email}
            </div>
            <div className="mt-1 text-gray-400">
              Dept: {profile.department} · {profile.roles.join(", ")}
            </div>
          </div>
          <button
            onClick={() => {
              setToken("");
              setProfile(null);
              setChatHistory([]);
            }}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-800 py-1.5 text-xs text-gray-400 hover:bg-gray-900 hover:text-white"
          >
            <LogOut className="h-3.5 w-3.5" /> Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-gray-950/60 px-6 py-3.5 backdrop-blur-md">
          <h2 className="text-base font-semibold tracking-tight text-white">
            {tab === "chat" && "Grounded AI Assistant"}
            {tab === "documents" && "Knowledge Base & Ingestion Pipeline"}
            {tab === "search" && "Hybrid Vector + Keyword Search"}
            {tab === "evaluations" && "RAG Evaluation & Ablation Runs"}
            {tab === "governance" && "Human Review Queue & Audit Logs"}
          </h2>
          <div className="flex items-center gap-2.5 text-xs">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
                isAdmin
                  ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-300"
                  : isGuest
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-sky-500/30 bg-sky-500/10 text-sky-300"
              }`}
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              {isAdmin
                ? "Admin · Full Access"
                : isGuest
                ? "Guest · Public Read-Only"
                : `${profile.department} · Dept Scope`}
            </span>
            <span className="text-gray-400">Scope:</span>
            <select
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="min-w-[11rem] rounded-lg border border-white/10 bg-gray-900/90 px-2.5 py-1.5 text-xs text-white transition focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            >
              <option value="">{defaultScopeLabel}</option>
              {authorizedDepartments.map((dept) => (
                <option key={dept} value={dept}>
                  {dept}
                </option>
              ))}
            </select>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-red-500/30 bg-red-950/50 px-4 py-3 text-sm text-red-300">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => setError(null)}
                className="rounded p-0.5 text-red-400 hover:bg-red-500/20 hover:text-red-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
          {notice && (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-emerald-500/30 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
              <span className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-400" />
                {notice}
              </span>
              <button
                type="button"
                onClick={() => setNotice(null)}
                className="rounded p-0.5 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          {tab === "chat" && (
            <div className="mx-auto flex h-full max-w-4xl flex-col justify-between space-y-6">
              <div className="space-y-6">
                {chatHistory.length === 0 && (
                  <div className="rounded-2xl border border-white/10 bg-gradient-to-b from-gray-900/80 to-gray-950/80 p-10 text-center shadow-2xl shadow-black/40 backdrop-blur-sm space-y-5">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 text-indigo-400 ring-1 ring-indigo-500/30 shadow-lg shadow-indigo-500/10">
                      <Bot className="h-6 w-6" />
                    </div>
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold tracking-tight text-white">
                        Ask across your published enterprise documents
                      </h3>
                      <p className="mx-auto max-w-xl text-xs leading-relaxed text-gray-400">
                        Responses are grounded strictly in authorized Azure AI Search chunks with verified citations, PII masking, and persistent session history.
                      </p>
                    </div>
                    <div className="flex flex-wrap justify-center gap-2 text-[11px] text-gray-400">
                      {["Azure Hybrid Search", "Verified Citations", "PII Masking", "RBAC Enforced"].map((pill) => (
                        <span
                          key={pill}
                          className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5"
                        >
                          {pill}
                        </span>
                      ))}
                    </div>
                    <div className="flex flex-wrap justify-center gap-2.5 pt-2">
                      {[
                        "What Microsoft certifications and degree are in the CV?",
                        "Compare the Medical Chatbot and Azure AI Foundry RAG projects.",
                        "What measurable impact was achieved in freelance and internship roles?",
                      ].map((sample) => (
                        <button
                          key={sample}
                          type="button"
                          onClick={() => submitChatQuery(sample)}
                          className="rounded-xl border border-white/10 bg-gray-900/90 px-3.5 py-2 text-xs text-gray-300 shadow-sm transition hover:-translate-y-0.5 hover:border-indigo-500/60 hover:bg-indigo-500/10 hover:text-white"
                        >
                          {sample}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {chatHistory.map((turn) => (
                  <div key={turn.id} className="space-y-3">
                    <div className="flex items-start gap-3 justify-end">
                      <div className="max-w-2xl rounded-2xl bg-indigo-600 px-4 py-2.5 text-sm text-white">
                        {turn.query}
                      </div>
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-800">
                        <UserIcon className="h-4 w-4 text-gray-300" />
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-950 text-indigo-400">
                        <Bot className="h-4 w-4" />
                      </div>
                      <div className="flex-1 space-y-3 rounded-2xl border border-gray-800 bg-gray-900/70 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-gray-400">
                          <span>
                            {turn.response.model} · {turn.response.prompt_version} ·{" "}
                            {turn.response.usage.total_tokens} tokens ·{" "}
                            {turn.response.latency_ms}ms
                          </span>
                          {turn.response.abstained ? (
                            <span className="rounded-full bg-amber-900/60 px-2.5 py-0.5 text-amber-300">
                              Abstained
                            </span>
                          ) : (
                            <span className="rounded-full bg-emerald-900/50 px-2.5 py-0.5 text-emerald-300">
                              Grounded
                            </span>
                          )}
                        </div>

                        <MarkdownAnswer content={turn.response.answer} />

                        {turn.response.citations.length > 0 && (
                          <div className="space-y-2 border-t border-gray-800 pt-3">
                            <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                              Verified Citations
                            </div>
                            <div className="grid gap-2 md:grid-cols-2">
                              {turn.response.citations.map((c) => {
                                const citKey = `${turn.id}-${c.chunk_id}`;
                                const expanded = selectedCitationKey === citKey;
                                return (
                                  <button
                                    key={c.chunk_id}
                                    type="button"
                                    onClick={() =>
                                      setSelectedCitationKey(expanded ? null : citKey)
                                    }
                                    className={`rounded-lg border p-2.5 text-left text-xs transition ${
                                      expanded
                                        ? "border-indigo-500 bg-indigo-950/30"
                                        : "border-gray-800 bg-gray-950 hover:border-gray-700"
                                    }`}
                                  >
                                    <div className="font-semibold text-indigo-400">
                                      [{c.citation_key}] {c.title}
                                    </div>
                                    <div className="mt-0.5 text-gray-400">
                                      {c.section_path || "Document"} · Pages:{" "}
                                      {c.page_numbers.join(", ") || "n/a"} · Score:{" "}
                                      {c.score.toFixed(3)}
                                    </div>
                                    {expanded && (
                                      <div className="mt-1.5 border-t border-gray-800 pt-1.5 text-[11px] text-gray-400">
                                        Chunk ID: {c.chunk_id} · Version: {c.version_id.slice(0, 8)}…
                                      </div>
                                    )}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          <button
                            onClick={() => handleFeedback(turn.id, turn.query, "positive")}
                            disabled={Boolean(turn.feedbackSent)}
                            className={`flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs ${
                              turn.feedbackSent === "positive"
                                ? "border-emerald-600 bg-emerald-950 text-emerald-300"
                                : "border-gray-700 text-gray-300 hover:bg-gray-800"
                            }`}
                          >
                            <ThumbsUp className="h-3.5 w-3.5" /> Helpful
                          </button>
                          <button
                            onClick={() => handleFeedback(turn.id, turn.query, "negative")}
                            disabled={Boolean(turn.feedbackSent)}
                            className={`flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs ${
                              turn.feedbackSent === "negative"
                                ? "border-red-600 bg-red-950 text-red-300"
                                : "border-gray-700 text-gray-300 hover:bg-gray-800"
                            }`}
                          >
                            <ThumbsDown className="h-3.5 w-3.5" /> Unhelpful
                          </button>
                          <button
                            onClick={() => handleEscalate(turn)}
                            disabled={turn.escalated}
                            className="rounded-md border border-amber-700/70 px-2.5 py-1 text-xs text-amber-300 hover:bg-amber-950/60 disabled:opacity-50"
                          >
                            {turn.escalated ? "Escalated" : "Escalate to Review"}
                          </button>
                          <button
                            onClick={() => {
                              navigator.clipboard?.writeText(turn.response.answer);
                              setCopiedId(turn.id);
                              setTimeout(() => setCopiedId(null), 1500);
                            }}
                            className="ml-auto flex items-center gap-1 rounded-md border border-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-800"
                          >
                            {copiedId === turn.id ? (
                              <>
                                <Check className="h-3.5 w-3.5 text-emerald-400" /> Copied
                              </>
                            ) : (
                              <>
                                <Copy className="h-3.5 w-3.5" /> Copy
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <form
                onSubmit={handleChat}
                className="sticky bottom-0 flex gap-2 rounded-2xl border border-white/10 bg-gray-900/90 p-2 shadow-2xl shadow-black/40 backdrop-blur-md transition focus-within:border-indigo-500/60 focus-within:ring-2 focus-within:ring-indigo-500/20"
              >
                <input
                  type="text"
                  placeholder="Ask a question about uploaded documents..."
                  value={chatQuery}
                  onChange={(e) => setChatQuery(e.target.value)}
                  className="flex-1 bg-transparent px-3.5 py-2 text-sm text-white placeholder-gray-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={loading || !chatQuery.trim()}
                  className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2 text-sm font-medium text-white shadow-md shadow-indigo-600/25 transition hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50"
                >
                  <Send className="h-4 w-4" />
                  {loading ? "Thinking..." : "Send"}
                </button>
              </form>
            </div>
          )}

          {tab === "documents" && (
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-5 space-y-4">
                <h3 className="text-sm font-semibold text-white">
                  Upload Document (PDF, DOCX, TXT)
                </h3>
                <form onSubmit={handleUpload} className="space-y-3">
                  <div>
                    <label className="text-xs text-gray-400">Title</label>
                    <input
                      type="text"
                      placeholder="e.g. Employee Handbook"
                      value={uploadTitle}
                      onChange={(e) => setUploadTitle(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400">Department</label>
                    <input
                      type="text"
                      placeholder="HR, Engineering, Finance..."
                      value={uploadDept}
                      onChange={(e) => setUploadDept(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400">File</label>
                    <input
                      type="file"
                      accept=".pdf,.docx,.txt"
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      className="mt-1 w-full text-xs text-gray-300"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                  >
                    {loading ? "Uploading..." : "Upload & Index"}
                  </button>
                </form>
              </div>

              <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-gray-900/70 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white">
                    Document Library &amp; Indexing Status
                  </h3>
                  <button
                    onClick={() => refreshDocuments()}
                    className="flex items-center gap-1.5 rounded-md border border-gray-700 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-800"
                  >
                    <RefreshCw className="h-3.5 w-3.5" /> Refresh
                  </button>
                </div>

                {documents.length === 0 ? (
                  <p className="text-sm text-gray-400">No documents uploaded yet.</p>
                ) : (
                  <div className="space-y-2">
                    {documents.map((doc) => (
                      <div
                        key={doc.document_id}
                        className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-800 bg-gray-950 p-3 text-sm"
                      >
                        <div className="flex items-center gap-3">
                          <FileText className="h-4 w-4 text-indigo-400" />
                          <div>
                            <div className="font-medium text-white">
                              {doc.title}{" "}
                              <span className="text-xs text-gray-400">
                                ({doc.department})
                              </span>
                            </div>
                            <div className="text-xs text-gray-400">
                              {doc.filename || "n/a"} · v{doc.version_number || 1} ·{" "}
                              {doc.indexed_chunks}/{doc.expected_chunks} chunks
                            </div>
                          </div>
                        </div>
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            doc.status === "published"
                              ? "bg-emerald-900/50 text-emerald-300"
                              : doc.status?.includes("failed")
                              ? "bg-red-900/50 text-red-300"
                              : "bg-amber-900/50 text-amber-300"
                          }`}
                        >
                          {doc.status || "unknown"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === "search" && (
            <div className="mx-auto max-w-4xl space-y-4">
              <form onSubmit={handleSearch} className="flex gap-2">
                <input
                  type="text"
                  placeholder="Search passages with hybrid BM25 + E5 vector RRF..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="flex-1 rounded-lg border border-gray-800 bg-gray-900 px-3 py-2.5 text-sm text-white focus:border-indigo-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {loading ? "Searching..." : "Search"}
                </button>
              </form>

              {searchResult && (
                <div className="space-y-3">
                  <div className="text-xs text-gray-400">
                    {searchResult.results.length} matching chunk(s) returned
                  </div>
                  {searchResult.results.map((hit) => (
                    <div
                      key={hit.chunk_id}
                      className="rounded-xl border border-gray-800 bg-gray-900/70 p-4 space-y-1.5"
                    >
                      <div className="flex justify-between text-sm font-semibold text-indigo-400">
                        <span>
                          {hit.title} ({hit.department}) · Pages:{" "}
                          {hit.page_numbers.join(", ") || "n/a"}
                        </span>
                        <span className="text-xs text-gray-400">
                          RRF Score: {hit.score.toFixed(4)}
                        </span>
                      </div>
                      <p className="text-sm leading-relaxed text-gray-200 whitespace-pre-line">
                        {hit.content.replace(/\n\s*\n+/g, "\n")}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === "evaluations" && (
            <div className="space-y-6">
              <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-5 space-y-4">
                <div>
                  <h3 className="text-sm font-semibold text-white">
                    Run New Evaluation Experiment
                  </h3>
                  <p className="mt-1 text-xs text-gray-400">
                    Test retrieval &amp; grounding quality on a labelled query.{" "}
                    <strong>Recall@K / NDCG@K</strong> measure whether the retriever found the expected document;{" "}
                    <strong>Citations</strong> &amp; <strong>Abstention</strong> measure whether the LLM answered faithfully without hallucinating.
                  </p>
                </div>

                <form onSubmit={handleRunEvaluation} className="grid gap-3 md:grid-cols-2">
                  <input
                    type="text"
                    placeholder="Experiment name (e.g. rag-baseline-v1)"
                    value={evalExperiment}
                    onChange={(e) => setEvalExperiment(e.target.value)}
                    className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
                    required
                  />
                  <input
                    type="text"
                    placeholder="Dataset name (e.g. cv-smoke)"
                    value={evalDataset}
                    onChange={(e) => setEvalDataset(e.target.value)}
                    className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
                    required
                  />
                  <input
                    type="text"
                    placeholder="Test query"
                    value={evalQuery}
                    onChange={(e) => setEvalQuery(e.target.value)}
                    className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm md:col-span-2"
                    required
                  />
                  <select
                    value={evalDocId}
                    onChange={(e) => setEvalDocId(e.target.value)}
                    className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
                  >
                    <option value="">No expected document (for abstention tests)</option>
                    {documents.map((d) => (
                      <option key={d.document_id} value={d.document_id}>
                        {d.title} ({d.department}) — {d.document_id.slice(0, 8)}…
                      </option>
                    ))}
                  </select>
                  <div className="flex items-center justify-between gap-3">
                    <label className="flex items-center gap-2 text-xs text-gray-300">
                      <input
                        type="checkbox"
                        checked={evalShouldAbstain}
                        onChange={(e) => setEvalShouldAbstain(e.target.checked)}
                      />
                      Expect abstention
                    </label>
                    <button
                      type="submit"
                      disabled={loading}
                      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                    >
                      {loading ? "Running..." : "Run Evaluation"}
                    </button>
                  </div>
                </form>
              </div>

              <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900/70">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-gray-800 text-xs uppercase text-gray-400">
                    <tr>
                      <th className="p-3.5">Experiment</th>
                      <th className="p-3.5">Dataset</th>
                      <th className="p-3.5">Recall@K</th>
                      <th className="p-3.5">NDCG@K</th>
                      <th className="p-3.5">Citations</th>
                      <th className="p-3.5">Abstention</th>
                      <th className="p-3.5">Tokens</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {evaluations.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="p-4 text-center text-gray-400">
                          No evaluation runs recorded yet. Run one above!
                        </td>
                      </tr>
                    ) : (
                      evaluations.map((run) => (
                        <tr key={run.run_id || run.experiment_name}>
                          <td className="p-3.5 font-medium">{run.experiment_name}</td>
                          <td className="p-3.5">{run.dataset_name}</td>
                          <td className="p-3.5">{run.recall_at_k}</td>
                          <td className="p-3.5">{run.ndcg_at_k}</td>
                          <td className="p-3.5">{run.citation_correctness}</td>
                          <td className="p-3.5">{run.abstention_accuracy}</td>
                          <td className="p-3.5">{run.total_tokens}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {tab === "governance" && (
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-white">
                  Human Review Queue
                </h3>
                {reviews.length === 0 ? (
                  <p className="text-sm text-gray-400">No review tasks.</p>
                ) : (
                  reviews.map((rev) => (
                    <div
                      key={rev.id}
                      className="rounded-xl border border-gray-800 bg-gray-900/70 p-4 text-sm space-y-2"
                    >
                      <div className="flex justify-between">
                        <span className="font-medium text-white">{rev.query}</span>
                        <span className="rounded-full bg-gray-800 px-2.5 py-0.5 text-xs">
                          {rev.status}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400">{rev.proposed_answer}</p>
                      {(rev.status === "pending" || rev.status === "escalated") && (
                        <div className="flex gap-2">
                          <button
                            onClick={async () => {
                              await apiClient.resolveReview(token, rev.id, "approved");
                              openGovernance();
                            }}
                            className="rounded-md bg-emerald-700 px-3 py-1 text-xs font-medium text-white"
                          >
                            Approve
                          </button>
                          <button
                            onClick={async () => {
                              await apiClient.resolveReview(token, rev.id, "rejected");
                              openGovernance();
                            }}
                            className="rounded-md bg-red-700 px-3 py-1 text-xs font-medium text-white"
                          >
                            Reject
                          </button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>

              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-white">Audit Logs</h3>
                <div className="space-y-2">
                  {auditLogs.map((log) => (
                    <div
                      key={log.id}
                      className="rounded-lg border border-gray-800 bg-gray-900/70 p-3 text-xs"
                    >
                      <span className="font-semibold text-indigo-400">
                        {log.action}
                      </span>{" "}
                      · {log.resource_type} ·{" "}
                      <span className="text-emerald-400">{log.outcome}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
