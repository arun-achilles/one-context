"use client";
import { useState } from "react";
import Sidebar from "@/app/components/Sidebar";
import ChatArea from "@/app/components/ChatArea";
import FeaturePanel from "@/app/components/FeaturePanel";
import { Feature, createConversation } from "@/app/lib/api";

type View =
  | { kind: "welcome" }
  | { kind: "feature"; feature: Feature }
  | { kind: "chat"; conversationId: number; featureName?: string; featureId?: string; role?: string };

const DEFAULT_AUTHOR = "You";

export default function Home() {
  const [view, setView] = useState<View>({ kind: "welcome" });

  async function handleGeneralChat() {
    const conv = await createConversation("General Chat");
    setView({ kind: "chat", conversationId: conv.id });
  }

  function handleSelectFeature(f: Feature) {
    setView({ kind: "feature", feature: f });
  }

  function handleStartSession(conversationId: number, role: string, featureName: string, featureId: string) {
    setView({ kind: "chat", conversationId, featureName, featureId, role });
  }

  return (
    <div className="flex h-screen" style={{ background: "var(--bg)" }}>
      <Sidebar
        activeConvId={view.kind === "chat" ? view.conversationId : null}
        onSelectFeature={handleSelectFeature}
        onGeneralChat={handleGeneralChat}
      />

      {/* Main area */}
      <main className="flex-1 flex flex-col min-w-0" style={{ background: "var(--bg)" }}>
        {view.kind === "welcome" && <WelcomeScreen onGeneralChat={handleGeneralChat} />}

        {view.kind === "feature" && (
          <FeaturePanel
            feature={view.feature}
            onStartSession={(convId, role) =>
              handleStartSession(convId, role, view.feature.name, view.feature.id)
            }
          />
        )}

        {view.kind === "chat" && (
          <ChatArea
            conversationId={view.conversationId}
            featureName={view.featureName}
            featureId={view.featureId}
            author={DEFAULT_AUTHOR}
          />
        )}
      </main>
    </div>
  );
}

function WelcomeScreen({ onGeneralChat }: { onGeneralChat: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8 text-center">
      {/* Logo */}
      <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-3xl mb-2"
        style={{ background: "linear-gradient(135deg,rgba(99,102,241,0.15),rgba(6,182,212,0.15))", border: "1px solid rgba(99,102,241,0.2)" }}>
        ⬡
      </div>
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">One Context</h1>
        <p className="text-sm max-w-md" style={{ color: "#64748b" }}>
          Your team's shared intelligence layer. Ask questions across Jira, Confluence, and your codebase — or open a Feature workspace to collaborate across roles.
        </p>
      </div>

      {/* Quick actions */}
      <div className="flex flex-col gap-3 w-full max-w-sm">
        <button onClick={onGeneralChat}
          className="flex items-center gap-3 px-5 py-3.5 rounded-xl text-sm font-semibold text-white transition-all"
          style={{ background: "linear-gradient(135deg,#6366f1,#4f46e5)", boxShadow: "0 0 24px rgba(99,102,241,0.3)" }}
          onMouseEnter={e => (e.currentTarget.style.boxShadow = "0 0 32px rgba(99,102,241,0.45)")}
          onMouseLeave={e => (e.currentTarget.style.boxShadow = "0 0 24px rgba(99,102,241,0.3)")}>
          <span>💬</span>
          Start a general chat
        </button>
        <div className="text-xs" style={{ color: "#334155" }}>or select a Feature in the sidebar</div>
      </div>

      {/* Hint cards */}
      <div className="grid grid-cols-3 gap-3 mt-2 w-full max-w-xl">
        {[
          { icon: "🔍", label: "Discover", desc: "Search existing capabilities in the codebase" },
          { icon: "✍️", label: "Draft", desc: "Create Jira stories grounded in prior decisions" },
          { icon: "🧠", label: "Remember", desc: "Save team decisions that surface automatically" },
        ].map(h => (
          <div key={h.label} className="p-4 rounded-xl text-left"
            style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
            <div className="text-lg mb-2">{h.icon}</div>
            <div className="text-sm font-semibold text-white mb-1">{h.label}</div>
            <div className="text-xs" style={{ color: "#475569" }}>{h.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
