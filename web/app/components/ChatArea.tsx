"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { streamChat, getMessages, getLinks, Message, FeatureLink } from "@/app/lib/api";

interface Props {
  conversationId: number;
  featureContext?: string;
  featureName?: string;
  featureId?: string;
  author: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: string[];
  richSources?: Array<{ url: string; label: string; content_type: string; score: number }>;
  streaming?: boolean;
}

type RichSource = { url: string; label: string; content_type: string; score: number };

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const cleanContent = msg.content
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\s*\[S\d+\]/g, "")
    .trim();

  // Compact checkpoint badge — no bubble
  if (!isUser && cleanContent.startsWith("[CHECKPOINT]")) {
    const summary = cleanContent.slice("[CHECKPOINT]".length).trim();
    return (
      <div className="flex justify-center fade-up">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium"
          style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.25)", color: "#f59e0b" }}>
          <span>💡</span>
          <span>Takeaway saved: {summary}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 fade-up ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold mt-0.5 ${
        isUser
          ? "bg-indigo-600 text-white"
          : "text-white"
      }`}
        style={isUser ? {} : { background: "linear-gradient(135deg,#6366f1,#06b6d4)" }}>
        {isUser ? "U" : "⬡"}
      </div>

      {/* Bubble */}
      <div className={`max-w-[75%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1`}>
        <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isUser
            ? "rounded-tr-sm text-white"
            : "rounded-tl-sm"
        }`}
          style={isUser
            ? { background: "linear-gradient(150deg,#312e81,#2563eb)", border: "1px solid rgba(99,102,241,0.5)" }
            : { background: "linear-gradient(160deg, rgba(22,33,59,0.88), rgba(14,22,45,0.92))", border: "1px solid rgba(62,83,137,0.75)", color: "#d8def3" }}>
          {msg.streaming && !cleanContent ? (
            <span className="typing-cursor text-slate-400 text-xs">Thinking</span>
          ) : (
            <div
              className="message-content"
              dangerouslySetInnerHTML={{ __html: formatContent(cleanContent) }}
            />
          )}
          {msg.streaming && cleanContent && (
            <span className="typing-cursor" />
          )}
        </div>

        {/* Sources */}
        {msg.sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-1">
            {(msg.richSources ?? msg.sources.filter(Boolean).slice(0, 4).map(u => ({ url: u, label: "", content_type: "knowledge", score: 0 }))).slice(0, 5).map((src, i) => {
              const normalizedType = inferSourceType(src);
              const typeIcon = SOURCE_TYPE_ICONS[normalizedType] ?? "🔗";
              const label = urlLabel(src.url);
              return (
                <a key={i} href={src.url} target="_blank" rel="noopener noreferrer"
                  className="text-[10px] px-2 py-0.5 rounded-full transition-all flex items-center gap-1"
                  style={{ background: "rgba(99,102,241,0.08)", color: "#93c5fd", border: "1px solid rgba(99,102,241,0.26)" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "rgba(99,102,241,0.15)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "rgba(99,102,241,0.08)")}>
                  <span>{typeIcon}</span>
                  <span>{label}</span>
                </a>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function formatContent(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\n- /g, "\n• ")
    .split("\n\n").map(p =>
      p.startsWith("•") || p.startsWith("-")
        ? `<ul>${p.split("\n").map(l => `<li>${l.replace(/^[•\-]\s*/, "")}</li>`).join("")}</ul>`
        : `<p>${p}</p>`
    ).join("");
}

function urlLabel(url: string): string {
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    return parts[parts.length - 1]?.slice(0, 24) || u.hostname;
  } catch {
    return url.slice(0, 24);
  }
}

function inferSourceType(src: RichSource): string {
  const ctype = (src.content_type || "").toLowerCase();
  if (ctype && ctype !== "knowledge" && ctype !== "unknown") return ctype;

  const url = (src.url || "").toLowerCase();
  const label = (src.label || "").toLowerCase();

  if (url.includes("/browse/")) return "jira_issue";
  if (url.includes("/wiki/")) return "confluence_page";
  if (url.includes("github.com") || url.includes("/pull/")) return "feature_link";
  if (label.includes("session summary")) return "feature_session_summary";
  if (label.includes("team memory")) return "takeaway";
  return "knowledge";
}

const SOURCE_TYPE_ICONS: Record<string, string> = {
  feature_session_summary: "🗂️",
  feature_link:            "🔗",
  takeaway:                "💡",
  team_memory:             "💡",
  jira_issue:              "📋",
  confluence_page:         "📄",
  business_flow:           "⚙️",
  shipped_feature:         "🚀",
  api_capability:          "🔌",
  knowledge:               "📚",
};

const SUGGESTIONS = [
  "What does this project do?",
  "What capabilities exist that I can reuse?",
  "Draft a story for improving this feature",
  "What were the key architectural decisions?",
];

export default function ChatArea({ conversationId, featureContext, featureName, featureId, author }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [links, setLinks] = useState<FeatureLink[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [expandedTakeaway, setExpandedTakeaway] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Fetch feature links (takeaways + artefacts) when featureId is set
  const refreshLinks = useCallback(() => {
    if (featureId) getLinks(featureId).then(setLinks).catch(console.error);
  }, [featureId]);

  useEffect(() => { refreshLinks(); }, [refreshLinks]);

  // Load existing messages
  useEffect(() => {
    setMessages([]);
    getMessages(conversationId).then(history => {
      setMessages(history
        .filter(m =>
          !m.content.startsWith("[FEATURE CONTEXT]") &&
          !m.content.startsWith("[FEATURE CONTEXT ACK]")
        )
        .map(m => ({
          id: String(m.id),
          role: m.role,
          content: m.content,
          sources: m.cited_sources ?? [],
        }))
      );
    });
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setInput("");
    setLoading(true);

    const userMsg: ChatMessage = { id: Date.now() + "u", role: "user", content: trimmed, sources: [] };
    const assistantMsg: ChatMessage = { id: Date.now() + "a", role: "assistant", content: "", sources: [], streaming: true };

    setMessages(prev => [...prev, userMsg, assistantMsg]);

    try {
      for await (const event of streamChat(conversationId, trimmed, author)) {
        if (event.type === "token") {
          setMessages(prev => prev.map(m =>
            m.id === assistantMsg.id ? { ...m, content: m.content + (event.content ?? "") } : m
          ));
        } else if (event.type === "sources") {
          setMessages(prev => prev.map(m =>
            m.id === assistantMsg.id ? {
              ...m,
              sources: event.sources ?? [],
              richSources: event.rich_sources ?? undefined,
            } : m
          ));
        } else if (event.type === "done" || event.type === "error") {
          setMessages(prev => prev.map(m =>
            m.id === assistantMsg.id ? { ...m, streaming: false } : m
          ));
        }
      }
    } finally {
      setLoading(false);
      inputRef.current?.focus();
      // Refresh sidebar after response in case a takeaway or artefact was saved
      refreshLinks();
    }
  }, [conversationId, loading, author, refreshLinks]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  const isEmpty = messages.length === 0;

  const takeaways = links.filter(l => l.link_type === "memory");
  const artefacts = links.filter(l => l.link_type !== "memory");

  const ARTEFACT_META: Record<string, { icon: string; color: string }> = {
    jira_story:      { icon: "📋", color: "#6366f1" },
    jira_task:       { icon: "✅", color: "#06b6d4" },
    jira_epic:       { icon: "🏔️", color: "#8b5cf6" },
    confluence_page: { icon: "📄", color: "#22d3ee" },
    github_pr:       { icon: "🔀", color: "#10b981" },
  };

  return (
    <div className="flex h-full min-w-0">
      {/* Main chat column */}
      <div className="flex flex-col flex-1 min-w-0 h-full">
      {/* Feature context banner */}
      {featureName && (
        <div className="flex-shrink-0 px-6 py-2.5 flex items-center gap-2.5 border-b"
          style={{ background: "rgba(99,102,241,0.05)", borderColor: "rgba(99,102,241,0.2)" }}>
          <div className="w-2 h-2 rounded-full bg-indigo-400" />
          <span className="text-xs" style={{ color: "#818cf8" }}>
            <span className="font-semibold">{featureName}</span>
          </span>
          <span className="text-[10px] font-mono" style={{ color: "#4f46e5" }}>{featureId}</span>
          {featureId && (
            <button
              onClick={() => setSidebarOpen(o => !o)}
              className="ml-auto text-[10px] px-2 py-0.5 rounded-md transition-colors"
              style={{ color: "#475569", border: "1px solid rgba(62,83,137,0.4)" }}>
              {sidebarOpen ? "Hide panel" : "Show panel"}
            </button>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
            <div>
              <div className="w-14 h-14 rounded-2xl mx-auto mb-4 flex items-center justify-center text-2xl"
                style={{ background: "linear-gradient(135deg,rgba(99,102,241,0.15),rgba(6,182,212,0.15))", border: "1px solid rgba(99,102,241,0.2)" }}>
                {featureName ? "🗂️" : "💬"}
              </div>
              <h2 className="text-xl font-bold text-white mb-2">
                {featureName ? `Working on: ${featureName}` : "General Chat"}
              </h2>
              <p className="text-sm max-w-sm" style={{ color: "#64748b" }}>
                {featureName
                  ? "Ask about existing capabilities, draft stories, or explore the codebase for this feature."
                  : "Ask anything about your Jira, Confluence, or codebase knowledge."}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 w-full max-w-md">
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => send(s)}
                  className="text-xs text-left px-3.5 py-2.5 rounded-xl transition-all"
                  style={{ background: "rgba(20,31,56,0.88)", border: "1px solid rgba(62,83,137,0.75)", color: "#94a3b8" }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "#6366f1"; e.currentTarget.style.color = "#a5b4fc"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(62,83,137,0.75)"; e.currentTarget.style.color = "#94a3b8"; }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map(m => <MessageBubble key={m.id} msg={m} />)
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 px-4 pb-4 pt-2">
        <div className="flex items-end gap-2 p-2 rounded-2xl transition-all"
          style={{ background: "linear-gradient(170deg, rgba(22,33,59,0.92), rgba(13,21,43,0.96))", border: "1px solid rgba(64,86,141,0.78)", boxShadow: "0 14px 36px rgba(1,9,24,0.32)" }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={featureName ? `Ask about ${featureName}…` : "Ask anything…"}
            rows={1}
            disabled={loading}
            className="flex-1 bg-transparent text-sm text-white placeholder-slate-600 outline-none resize-none px-2 py-1.5 max-h-32"
            style={{ caretColor: "#6366f1" }}
            onInput={e => {
              const t = e.currentTarget;
              t.style.height = "auto";
              t.style.height = Math.min(t.scrollHeight, 128) + "px";
            }}
          />
          {featureId && (
            <button
              onClick={() => send("remember our key decisions and action items from this conversation so far")}
              disabled={loading}
              title="Save takeaway"
              className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 transition-all disabled:opacity-30 text-sm"
              style={{
                background: "rgba(245,158,11,0.1)",
                border: "1px solid rgba(245,158,11,0.2)",
                color: "#f59e0b"
              }}>
              💾
            </button>
          )}
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || loading}
            className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 transition-all disabled:opacity-30"
            style={{ background: input.trim() && !loading ? "linear-gradient(135deg,#6366f1,#4f46e5)" : "var(--bg3)" }}>
            {loading
              ? <span className="w-3 h-3 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />
              : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            }
          </button>
        </div>
        <p className="text-[10px] text-center mt-1.5" style={{ color: "#334155" }}>
          Enter to send · Shift+Enter for new line
        </p>
      </div>
      </div>{/* end main chat column */}

      {/* Right sidebar — takeaways + artefacts (feature sessions only) */}
      {featureId && sidebarOpen && (
        <div className="flex-shrink-0 w-72 border-l flex flex-col overflow-y-auto"
          style={{ borderColor: "rgba(62,83,137,0.4)", background: "rgba(10,17,35,0.7)" }}>

          {/* Takeaways */}
          <div className="p-4 border-b" style={{ borderColor: "rgba(62,83,137,0.3)" }}>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm">💡</span>
              <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "#f59e0b" }}>
                Takeaways
              </span>
              <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full font-mono"
                style={{ background: "rgba(245,158,11,0.1)", color: "#f59e0b" }}>
                {takeaways.length}
              </span>
            </div>
            {takeaways.length === 0 ? (
              <p className="text-[11px] italic" style={{ color: "#334155" }}>
                No takeaways yet — click 💡 to save key decisions.
              </p>
            ) : (
              <div className="space-y-2">
                {takeaways.map(t => (
                  <div key={t.id}
                    className="rounded-lg cursor-pointer transition-all"
                    style={{ background: "rgba(245,158,11,0.06)", border: "1px solid rgba(245,158,11,0.2)" }}
                    onClick={() => setExpandedTakeaway(expandedTakeaway === t.id ? null : t.id)}>
                    <div className="flex items-start gap-2 px-3 py-2">
                      <span className="text-xs mt-0.5 flex-shrink-0" style={{ color: "#f59e0b" }}>💡</span>
                      <p className={`text-xs leading-relaxed ${expandedTakeaway === t.id ? "" : "line-clamp-2"}`}
                        style={{ color: "#d1a832" }}>
                        {t.title || t.link_id}
                      </p>
                    </div>
                    {expandedTakeaway === t.id && (
                      <div className="px-3 pb-2">
                        <span className="text-[10px]" style={{ color: "#475569" }}>
                          {new Date(t.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Linked Artefacts */}
          <div className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm">🔗</span>
              <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "#6366f1" }}>
                Linked Artefacts
              </span>
              <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full font-mono"
                style={{ background: "rgba(99,102,241,0.1)", color: "#6366f1" }}>
                {artefacts.length}
              </span>
            </div>
            {artefacts.length === 0 ? (
              <p className="text-[11px] italic" style={{ color: "#334155" }}>
                No artefacts linked yet.
              </p>
            ) : (
              <div className="space-y-1.5">
                {artefacts.map(a => {
                  const meta = ARTEFACT_META[a.link_type] ?? { icon: "🔗", color: "#94a3b8" };
                  return (
                    <div key={a.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg"
                      style={{ background: "rgba(20,31,56,0.6)", border: "1px solid rgba(62,83,137,0.4)" }}>
                      <span className="text-xs flex-shrink-0">{meta.icon}</span>
                      {a.link_url ? (
                        <a href={a.link_url} target="_blank" rel="noopener noreferrer"
                          className="text-[11px] truncate hover:underline flex-1"
                          style={{ color: meta.color }}>
                          {a.title || a.link_id}
                        </a>
                      ) : (
                        <span className="text-[11px] truncate flex-1" style={{ color: "#475569" }}>
                          {a.title || a.link_id}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
