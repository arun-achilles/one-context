"use client";
import { useEffect, useState } from "react";
import { getFeature, startSession, Feature } from "@/app/lib/api";

interface Props {
  feature: Feature;
  onStartSession: (conversationId: number, role: string) => void;
}

const ROLES = [
  { key: "po",         label: "Product Owner",   icon: "📋", color: "#6366f1" },
  { key: "tech_lead",  label: "Tech Lead",        icon: "🏗️",  color: "#06b6d4" },
  { key: "dev",        label: "Developer",        icon: "💻", color: "#10b981" },
  { key: "em",         label: "Eng. Manager",     icon: "📊", color: "#f59e0b" },
];

const STATUS_COLORS: Record<string, string> = {
  planned:     "bg-slate-700/60 text-slate-300",
  in_progress: "bg-amber-900/40 text-amber-300",
  shipped:     "bg-emerald-900/40 text-emerald-300",
  paused:      "bg-slate-700/60 text-slate-400",
};

export default function FeaturePanel({ feature, onStartSession }: Props) {
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof getFeature>> | null>(null);
  const [author, setAuthor] = useState("");
  const [starting, setStarting] = useState<string | null>(null);

  useEffect(() => {
    getFeature(feature.id).then(setDetail).catch(console.error);
  }, [feature.id]);

  async function handleStart(role: string) {
    if (!author.trim()) return;
    setStarting(role);
    try {
      const session = await startSession(feature.id, role, author.trim());
      onStartSession(session.conversation_id, role);
    } finally {
      setStarting(null);
    }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto px-8 py-8 max-w-2xl mx-auto w-full">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded"
            style={{ background: "rgba(99,102,241,0.1)", color: "#6366f1", border: "1px solid rgba(99,102,241,0.2)" }}>
            {feature.id}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded font-semibold ${STATUS_COLORS[feature.status] ?? ""}`}>
            {feature.status.replace("_", " ")}
          </span>
          {feature.jira_epic && (
            <span className="text-xs px-2 py-0.5 rounded"
              style={{ background: "rgba(6,182,212,0.1)", color: "#22d3ee", border: "1px solid rgba(6,182,212,0.2)" }}>
              {feature.jira_epic}
            </span>
          )}
        </div>
        <h1 className="text-2xl font-bold text-white">{feature.name}</h1>
        {feature.description && (
          <p className="text-sm mt-1.5" style={{ color: "#64748b" }}>{feature.description}</p>
        )}
      </div>

      {/* Your name */}
      <div className="mb-5">
        <label className="text-xs font-semibold uppercase tracking-wider block mb-2" style={{ color: "#475569" }}>
          Your name
        </label>
        <input value={author} onChange={e => setAuthor(e.target.value)}
          placeholder="Enter your name to start a session"
          className="w-full px-3 py-2.5 rounded-xl text-sm text-white outline-none transition-all"
          style={{ background: "var(--card)", border: "1px solid var(--border)", caretColor: "#6366f1" }}
          onFocus={e => (e.currentTarget.style.borderColor = "#6366f1")}
          onBlur={e => (e.currentTarget.style.borderColor = "var(--border)")} />
      </div>

      {/* Start session */}
      <div className="mb-6">
        <label className="text-xs font-semibold uppercase tracking-wider block mb-3" style={{ color: "#475569" }}>
          Start a session as
        </label>
        <div className="grid grid-cols-2 gap-2">
          {ROLES.map(r => (
            <button key={r.key}
              onClick={() => handleStart(r.key)}
              disabled={!author.trim() || starting !== null}
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-left transition-all disabled:opacity-40"
              style={{ background: "var(--card)", border: "1px solid var(--border)", color: "#94a3b8" }}
              onMouseEnter={e => {
                if (author.trim()) {
                  e.currentTarget.style.borderColor = r.color;
                  e.currentTarget.style.color = "white";
                }
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = "var(--border)";
                e.currentTarget.style.color = "#94a3b8";
              }}>
              {starting === r.key
                ? <span className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
                : <span className="text-base">{r.icon}</span>
              }
              {r.label}
            </button>
          ))}
        </div>
        {!author.trim() && (
          <p className="text-xs mt-2" style={{ color: "#475569" }}>Enter your name above to start a session.</p>
        )}
      </div>

      {/* Prior sessions */}
      {detail?.sessions && detail.sessions.length > 0 && (
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider block mb-3" style={{ color: "#475569" }}>
            Session history
          </label>
          <div className="space-y-2">
            {detail.sessions.map(s => {
              const roleInfo = ROLES.find(r => r.key === s.role);
              return (
                <div key={s.id} className="p-3.5 rounded-xl"
                  style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold" style={{ color: roleInfo?.color ?? "#94a3b8" }}>
                      {roleInfo?.icon} {roleInfo?.label ?? s.role}
                    </span>
                    {s.author && <span className="text-xs" style={{ color: "#475569" }}>{s.author}</span>}
                    <span className="text-xs ml-auto" style={{ color: "#334155" }}>
                      {new Date(s.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  {s.summary
                    ? <p className="text-xs leading-relaxed" style={{ color: "#64748b" }}>{s.summary}</p>
                    : <p className="text-xs italic" style={{ color: "#334155" }}>No summary yet</p>
                  }
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Feature context preview */}
      {detail?.context && (
        <div className="mt-6">
          <label className="text-xs font-semibold uppercase tracking-wider block mb-2" style={{ color: "#475569" }}>
            Context injected into sessions
          </label>
          <pre className="text-xs p-4 rounded-xl overflow-x-auto"
            style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "#475569", whiteSpace: "pre-wrap", fontFamily: "JetBrains Mono, monospace" }}>
            {detail.context}
          </pre>
        </div>
      )}
    </div>
  );
}
