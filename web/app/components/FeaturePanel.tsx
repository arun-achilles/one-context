"use client";
import { useEffect, useState } from "react";
import { getFeature, startSession, deleteSession, summarizeSession, Feature, FeatureLink, Session } from "@/app/lib/api";

interface Props {
  feature: Feature;
  onStartSession: (conversationId: number, role: string) => void;
  author: string;
  onAuthorChange: (name: string) => void;
}

const ROLES = [
  { key: "po",         label: "Product Owner",   icon: "📋", color: "#F04E2B" },
  { key: "tech_lead",  label: "Tech Lead",        icon: "🏗️",  color: "#1a1a1a" },
  { key: "dev",        label: "Developer",        icon: "💻", color: "#6b6b6b" },
  { key: "ba",         label: "Business Analyst", icon: "🧾", color: "#F04E2B" },
  { key: "qa",         label: "QA",               icon: "🧪", color: "#1a1a1a" },
];

const STATUS_COLORS: Record<string, string> = {
  planned:     "bg-stone-100 text-stone-500",
  in_progress: "bg-orange-50 text-orange-600",
  shipped:     "bg-green-50 text-green-700",
  paused:      "bg-stone-100 text-stone-400",
};

export default function FeaturePanel({ feature, onStartSession, author, onAuthorChange }: Props) {
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof getFeature>> | null>(null);
  const [links, setLinks] = useState<FeatureLink[]>([]);
  const [starting, setStarting] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [summarizing, setSummarizing] = useState<number | null>(null);
  const [expandedTakeaway, setExpandedTakeaway] = useState<number | null>(null);

  function refreshDetail() {
    getFeature(feature.id).then(d => {
      setDetail(d);
      setLinks(d.links ?? []);
    }).catch(console.error);
  }

  useEffect(() => { refreshDetail(); }, [feature.id]);

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

  async function handleContinue(s: Session) {
    // Re-enter the existing session's conversation — no new session created
    onStartSession(s.conversation_id, s.role ?? "dev");
  }

  async function handleDeleteSession(s: Session) {
    if (!confirm(`Delete this ${s.role ?? "session"} session by ${s.author ?? "unknown"}? This will remove all messages.`)) return;
    setDeleting(s.id);
    try {
      await deleteSession(feature.id, s.id);
      refreshDetail();
    } catch {
      alert("Failed to delete session");
    } finally {
      setDeleting(null);
    }
  }

  async function handleSummarizeSession(s: Session) {
    setSummarizing(s.id);
    try {
      await summarizeSession(feature.id, s.id);
      refreshDetail();
    } catch {
      alert("Failed to summarize session");
    } finally {
      setSummarizing(null);
    }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto px-8 py-8 max-w-2xl mx-auto w-full">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono px-2 py-0.5 rounded"
            style={{ background: "rgba(240,78,43,0.08)", color: "#F04E2B", border: "1px solid rgba(240,78,43,0.2)" }}>
            {feature.id}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded font-semibold ${STATUS_COLORS[feature.status] ?? ""}`}>
            {feature.status.replace("_", " ")}
          </span>
          {feature.jira_epic && (
            <span className="text-xs px-2 py-0.5 rounded"
              style={{ background: "#f2f2f2", color: "#6b6b6b", border: "1px solid #e5e5e5" }}>
              {feature.jira_epic}
            </span>
          )}
        </div>
        <h1 className="text-2xl font-bold" style={{ color: "#1a1a1a" }}>{feature.name}</h1>
        {feature.description && (
          <p className="text-sm mt-1.5" style={{ color: "#6b6b6b" }}>{feature.description}</p>
        )}
      </div>

      {/* Your name */}
      <div className="mb-5">
        <label className="text-xs font-semibold uppercase tracking-wider block mb-2" style={{ color: "#6b6b6b" }}>
          Your name
        </label>
        <input value={author} onChange={e => onAuthorChange(e.target.value)}
          placeholder="Enter your name to start a session"
          className="w-full px-3 py-2.5 rounded-xl text-sm outline-none transition-all"
          style={{ background: "#f5f5f5", border: "1px solid #e5e5e5", color: "#1a1a1a", caretColor: "#F04E2B" }}
          onFocus={e => (e.currentTarget.style.borderColor = "#F04E2B")}
          onBlur={e => (e.currentTarget.style.borderColor = "#e5e5e5")} />
      </div>

      {/* Start session */}
      <div className="mb-6">
        <label className="text-xs font-semibold uppercase tracking-wider block mb-3" style={{ color: "#6b6b6b" }}>
          Start a session as
        </label>
        <div className="grid grid-cols-2 gap-2">
          {ROLES.map(r => (
            <button key={r.key}
              onClick={() => handleStart(r.key)}
              disabled={!author.trim() || starting !== null}
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-left transition-all disabled:opacity-40"
              style={{ background: "#f5f5f5", border: "1px solid #e5e5e5", color: "#6b6b6b" }}
              onMouseEnter={e => {
                if (author.trim()) {
                  e.currentTarget.style.borderColor = "#F04E2B";
                  e.currentTarget.style.color = "#1a1a1a";
                }
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = "#e5e5e5";
                e.currentTarget.style.color = "#6b6b6b";
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
          <p className="text-xs mt-2" style={{ color: "#999999" }}>Enter your name above to start a session.</p>
        )}
      </div>

      {/* Prior sessions */}
      {detail?.sessions && detail.sessions.length > 0 && (
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider block mb-3" style={{ color: "#6b6b6b" }}>
            Session history
          </label>
          <div className="space-y-2">
            {detail.sessions.map(s => {
              const roleInfo = ROLES.find(r => r.key === s.role);
              const isOwn = author.trim() !== "" && s.author?.toLowerCase() === author.toLowerCase();
              return (
                <div key={s.id} className="p-3.5 rounded-xl"
                  style={{
                    background: "#ffffff",
                    border: "1px solid #e5e5e5",
                    ...(isOwn ? { borderLeft: "3px solid #F04E2B" } : {}),
                  }}>
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold" style={{ color: roleInfo?.color ?? "#6b6b6b" }}>
                        {roleInfo?.icon} {roleInfo?.label ?? s.role}
                      </span>
                      {s.author && <span className="text-xs" style={{ color: "#6b6b6b" }}>{s.author}</span>}
                      <span className="text-xs" style={{ color: "#999999" }}>
                        {new Date(s.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {isOwn && (
                        <button
                          onClick={() => handleContinue(s)}
                          disabled={starting !== null}
                          className="text-xs px-2 py-1 rounded-lg font-semibold"
                          style={{ background: "rgba(240,78,43,0.08)", color: "#F04E2B", border: "1px solid rgba(240,78,43,0.2)" }}>
                          Continue
                        </button>
                      )}
                      {!s.summary && (
                        <button
                          onClick={() => handleSummarizeSession(s)}
                          disabled={summarizing === s.id}
                          title="Save session summary"
                          className="text-xs px-2 py-1 rounded-lg font-semibold transition-opacity"
                          style={{ background: "rgba(240,78,43,0.08)", color: "#F04E2B", border: "1px solid rgba(240,78,43,0.2)" }}>
                          {summarizing === s.id ? "…" : "💡 Save"}
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteSession(s)}
                        disabled={deleting === s.id}
                        title="Delete session"
                        className="w-6 h-6 flex items-center justify-center rounded-lg text-xs transition-opacity opacity-40 hover:opacity-100"
                        style={{ color: "#ef4444" }}>
                        {deleting === s.id ? "…" : "✕"}
                      </button>
                    </div>
                  </div>
                  {s.summary
                    ? <p className="text-xs leading-relaxed" style={{ color: "#6b6b6b" }}>{s.summary}</p>
                    : <p className="text-xs italic" style={{ color: "#999999" }}>No summary yet</p>
                  }
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Linked Artefacts */}
      {links.length > 0 && (
        <div className="mt-6">
          <label className="text-xs font-semibold uppercase tracking-wider block mb-3" style={{ color: "#6b6b6b" }}>
            Linked Artefacts
          </label>
          {(() => {
            const LINK_META: Record<string, { icon: string; label: string; color: string }> = {
              jira_story:      { icon: "📋", label: "Jira Stories",     color: "#F04E2B" },
              jira_task:       { icon: "✅", label: "Jira Tasks",       color: "#F04E2B" },
              jira_epic:       { icon: "🏔️", label: "Jira Epics",       color: "#F04E2B" },
              confluence_page: { icon: "📄", label: "Confluence Pages", color: "#1a1a1a" },
              github_pr:       { icon: "🔀", label: "GitHub PRs",       color: "#6b6b6b" },
              memory:          { icon: "💡", label: "Takeaways",        color: "#F04E2B" },
            };
            const grouped = links.reduce<Record<string, FeatureLink[]>>((acc, lnk) => {
              const key = lnk.link_type as string;
              if (!acc[key]) acc[key] = [];
              acc[key].push(lnk);
              return acc;
            }, {} as Record<string, FeatureLink[]>);
            return (Object.entries(grouped) as [string, FeatureLink[]][]).map(([type, items]) => {
              const meta = LINK_META[type] ?? { icon: "🔗", label: type, color: "#6b6b6b" };
              return (
                <div key={type} className="mb-3">
                  <div className="text-xs font-semibold mb-1.5" style={{ color: meta.color }}>
                    {meta.icon} {meta.label}
                  </div>
                  <div className="space-y-1">
                    {items.map(lnk => {
                      const isTakeaway = lnk.link_type === "memory";
                      const isExpanded = expandedTakeaway === lnk.id;
                      return (
                        <div key={lnk.id}
                          className={`rounded-lg ${isTakeaway ? "cursor-pointer" : ""}`}
                          style={isTakeaway
                            ? { background: "rgba(240,78,43,0.04)", border: "1px solid rgba(240,78,43,0.15)" }
                            : { background: "#ffffff", border: "1px solid #e5e5e5" }}
                          onClick={isTakeaway ? () => setExpandedTakeaway(isExpanded ? null : lnk.id) : undefined}>
                          <div className="flex items-start gap-2 px-3 py-2">
                            {lnk.link_url ? (
                              <a href={lnk.link_url} target="_blank" rel="noopener noreferrer"
                                className="text-xs hover:underline truncate flex-1"
                                style={{ color: meta.color }}
                                onClick={e => e.stopPropagation()}>
                                {lnk.title || lnk.link_id}
                              </a>
                            ) : (
                              <span className={`text-xs flex-1 ${isTakeaway ? "" : "truncate"}`}
                                style={{ color: isTakeaway ? "#c73d1e" : "#6b6b6b" }}>
                                {isTakeaway
                                  ? (isExpanded ? (lnk.title || lnk.link_id) : (lnk.title || lnk.link_id).slice(0, 60) + ((lnk.title || "").length > 60 ? "…" : ""))
                                  : (lnk.title || lnk.link_id)
                                }
                              </span>
                            )}
                            {!isTakeaway && (
                              <span className="text-[10px] font-mono flex-shrink-0" style={{ color: "#999999" }}>
                                {lnk.link_id}
                              </span>
                            )}
                            {isTakeaway && (
                              <span className="text-[10px] flex-shrink-0 ml-1" style={{ color: "#999999" }}>
                                {isExpanded ? "▲" : "▼"}
                              </span>
                            )}
                          </div>
                          {isTakeaway && isExpanded && (
                            <div className="px-3 pb-2 pt-0">
                              <p className="text-xs leading-relaxed" style={{ color: "#c73d1e" }}>
                                {lnk.title || lnk.link_id}
                              </p>
                              <span className="text-[10px] mt-1 block" style={{ color: "#999999" }}>
                                {new Date(lnk.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                              </span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            });
          })()}
        </div>
      )}

      {/*
      Feature context preview intentionally hidden.
      {detail?.context && (
        <div className="mt-6">
          <label className="text-xs font-semibold uppercase tracking-wider block mb-2" style={{ color: "#6b6b6b" }}>
            Context injected into sessions
          </label>
          <pre className="text-xs p-4 rounded-xl overflow-x-auto"
            style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "#6b6b6b", whiteSpace: "pre-wrap", fontFamily: "JetBrains Mono, monospace" }}>
            {detail.context}
          </pre>
        </div>
      )}
      */}
    </div>
  );
}
