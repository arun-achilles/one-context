"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { streamChat, getMessages, Message } from "@/app/lib/api";

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
  streaming?: boolean;
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const cleanContent = msg.content.replace(/<!--[\s\S]*?-->/g, "").trim();

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
            ? { background: "#312e81", border: "1px solid #4338ca" }
            : { background: "var(--card)", border: "1px solid var(--border)", color: "#cbd5e1" }}>
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
            {msg.sources.filter(Boolean).slice(0, 4).map((url, i) => (
              <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                className="text-[10px] px-2 py-0.5 rounded-full transition-all"
                style={{ background: "rgba(6,182,212,0.08)", color: "#22d3ee", border: "1px solid rgba(6,182,212,0.2)" }}
                onMouseEnter={e => (e.currentTarget.style.background = "rgba(6,182,212,0.15)")}
                onMouseLeave={e => (e.currentTarget.style.background = "rgba(6,182,212,0.08)")}>
                ↗ {urlLabel(url)}
              </a>
            ))}
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
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load existing messages
  useEffect(() => {
    setMessages([]);
    getMessages(conversationId).then(history => {
      setMessages(history
        .filter(m => !m.content.startsWith("[FEATURE CONTEXT]"))
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
            m.id === assistantMsg.id ? { ...m, sources: event.sources ?? [] } : m
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
    }
  }, [conversationId, loading, author]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Feature context banner */}
      {featureName && (
        <div className="flex-shrink-0 px-6 py-2.5 flex items-center gap-2.5 border-b"
          style={{ background: "rgba(99,102,241,0.05)", borderColor: "rgba(99,102,241,0.2)" }}>
          <div className="w-2 h-2 rounded-full bg-indigo-400" />
          <span className="text-xs" style={{ color: "#818cf8" }}>
            <span className="font-semibold">{featureName}</span>
          </span>
          <span className="text-[10px] font-mono" style={{ color: "#4f46e5" }}>{featureId}</span>
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
                  style={{ background: "var(--card)", border: "1px solid var(--border)", color: "#94a3b8" }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "#6366f1"; e.currentTarget.style.color = "#a5b4fc"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "#94a3b8"; }}>
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
          style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
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
              title="Save memory checkpoint"
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
    </div>
  );
}
