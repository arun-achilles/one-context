"use client";
import { useEffect, useState } from "react";
import { listFeatures, createFeature, Feature } from "@/app/lib/api";

const STATUS_COLORS: Record<string, string> = {
  planned:     "bg-stone-200 text-stone-600",
  in_progress: "bg-amber-100 text-amber-700",
  shipped:     "bg-emerald-100 text-emerald-700",
  paused:      "bg-stone-200 text-stone-500",
};

interface Props {
  activeConvId: number | null;
  onSelectFeature: (f: Feature) => void;
  onGeneralChat: () => void;
  author: string;
}

export default function Sidebar({ activeConvId, onSelectFeature, onGeneralChat, author }: Props) {
  const [features, setFeatures] = useState<Feature[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", created_by: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listFeatures().then(setFeatures).catch(console.error);
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const f = await createFeature(form.name, form.description, form.created_by || "anonymous");
      setFeatures(prev => [f, ...prev]);
      setShowModal(false);
      setForm({ name: "", description: "", created_by: "" });
      onSelectFeature(f);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <aside className="w-72 flex-shrink-0 flex flex-col h-full border-r"
        style={{ background: "#ede8de", borderColor: "#d4ccbf" }}>

        {/* Brand */}
        <div className="px-4 py-4 border-b flex items-center gap-2.5"
          style={{ borderColor: "#d4ccbf" }}>
          <div className="w-7 h-7 rounded-lg flex items-center justify-center text-sm font-bold text-white"
            style={{ background: "#6366f1" }}>
            ⬡
          </div>
          <div>
            <div className="text-sm font-bold leading-none" style={{ color: "#2d2520" }}>One Context</div>
            <div className="text-xs mt-0.5" style={{ color: "#7a7268" }}>AI Delivery Co-Pilot</div>
          </div>
        </div>

        {/* General chat */}
        <div className="px-3 pt-3">
          <button onClick={onGeneralChat}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-all text-left"
            style={{ color: "#5a5248", border: "1px solid transparent" }}
            onMouseEnter={e => {
              e.currentTarget.style.background = "#e3ddd0";
              e.currentTarget.style.borderColor = "#c6bdb0";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.borderColor = "transparent";
            }}>
            <span className="text-base">💬</span>
            <span>General Chat</span>
          </button>
        </div>

        {/* Features header */}
        <div className="px-4 pt-4 pb-2 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#7a7268" }}>
            Features
          </span>
          <button onClick={() => setShowModal(true)}
            className="text-xs px-2 py-0.5 rounded-md font-semibold transition-all"
            style={{ background: "rgba(99,102,241,0.1)", color: "#5b5bd6", border: "1px solid rgba(99,102,241,0.25)" }}
            onMouseEnter={e => (e.currentTarget.style.background = "rgba(99,102,241,0.18)")}
            onMouseLeave={e => (e.currentTarget.style.background = "rgba(99,102,241,0.1)")}>
            + New
          </button>
        </div>

        {/* Feature list */}
        <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-1">
          {features.length === 0 && (
            <div className="text-xs text-center py-6" style={{ color: "#a89e94" }}>
              No features yet.<br />Create one to get started.
            </div>
          )}
          {features.map(f => (
            <button key={f.id} onClick={() => onSelectFeature(f)}
              className="w-full text-left px-3 py-2.5 rounded-lg transition-all group"
              style={{ border: "1px solid transparent" }}
              onMouseEnter={e => {
                e.currentTarget.style.background = "#e3ddd0";
                e.currentTarget.style.borderColor = "#c6bdb0";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.borderColor = "transparent";
              }}>
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-sm font-medium truncate" style={{ color: "#2d2520" }}>{f.name}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold flex-shrink-0 ${STATUS_COLORS[f.status] ?? "bg-stone-200 text-stone-600"}`}>
                  {f.status.replace("_", " ")}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono" style={{ color: "#6366f1" }}>{f.id}</span>
                {f.session_count != null && f.session_count > 0 && (
                  <span className="text-[10px]" style={{ color: "#7a7268" }}>{f.session_count} session{f.session_count !== 1 ? "s" : ""}</span>
                )}
                {author.trim() && f.created_by?.toLowerCase() === author.toLowerCase() && (
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 inline-block" style={{ background: "#6366f1" }} />
                )}
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* New Feature Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(180,168,155,0.5)", backdropFilter: "blur(4px)" }}
          onClick={e => e.target === e.currentTarget && setShowModal(false)}>
          <div className="w-full max-w-md rounded-2xl p-6 shadow-xl"
            style={{ background: "#f5f0e8", border: "1px solid #d4ccbf" }}>
            <h2 className="text-lg font-bold mb-1" style={{ color: "#2d2520" }}>New Feature</h2>
            <p className="text-sm mb-5" style={{ color: "#7a7268" }}>
              Multi-sprint, multi-role delivery workspace. A Jira epic will be created when you're ready.
            </p>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider block mb-1.5" style={{ color: "#7a7268" }}>
                  Feature name *
                </label>
                <input
                  value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. Gift Cards, QR Scan Reliability"
                  className="w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-all"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "#2d2520", caretColor: "#6366f1" }}
                  onFocus={e => (e.currentTarget.style.borderColor = "#6366f1")}
                  onBlur={e => (e.currentTarget.style.borderColor = "var(--border)")}
                  autoFocus required
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider block mb-1.5" style={{ color: "#7a7268" }}>
                  Description
                </label>
                <textarea
                  value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
                  placeholder="What problem does this feature solve?"
                  rows={2}
                  className="w-full px-3 py-2.5 rounded-lg text-sm outline-none resize-none transition-all"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "#2d2520", caretColor: "#6366f1" }}
                  onFocus={e => (e.currentTarget.style.borderColor = "#6366f1")}
                  onBlur={e => (e.currentTarget.style.borderColor = "var(--border)")}
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider block mb-1.5" style={{ color: "#7a7268" }}>
                  Your name
                </label>
                <input
                  value={form.created_by} onChange={e => setForm(p => ({ ...p, created_by: e.target.value }))}
                  placeholder="Your name"
                  className="w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-all"
                  style={{ background: "var(--bg3)", border: "1px solid var(--border)", color: "#2d2520", caretColor: "#6366f1" }}
                  onFocus={e => (e.currentTarget.style.borderColor = "#6366f1")}
                  onBlur={e => (e.currentTarget.style.borderColor = "var(--border)")}
                />
              </div>
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => setShowModal(false)}
                  className="flex-1 py-2.5 rounded-lg text-sm font-semibold transition-all"
                  style={{ background: "var(--bg3)", color: "#7a7268", border: "1px solid var(--border)" }}>
                  Cancel
                </button>
                <button type="submit" disabled={saving || !form.name.trim()}
                  className="flex-1 py-2.5 rounded-lg text-sm font-semibold transition-all text-white disabled:opacity-50"
                  style={{ background: "#6366f1" }}>
                  {saving ? "Creating…" : "Create Feature"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
