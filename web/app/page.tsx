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

export default function Home() {
  const [view, setView] = useState<View>({ kind: "welcome" });
  const [author, setAuthor] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("oc_author") ?? "";
  });

  function handleSetAuthor(name: string) {
    setAuthor(name);
    if (typeof window !== "undefined") localStorage.setItem("oc_author", name);
  }

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
        author={author}
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
            author={author}
            onAuthorChange={handleSetAuthor}
          />
        )}

        {view.kind === "chat" && (
          <ChatArea
            conversationId={view.conversationId}
            featureName={view.featureName}
            featureId={view.featureId}
            author={author || "You"}
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
        style={{ background: "#F04E2B", color: "#ffffff" }}>
        ⬡
      </div>
      <div>
        <h1 className="text-2xl font-bold mb-2" style={{ color: "#1a1a1a" }}>One Context</h1>
        <p className="text-sm max-w-md" style={{ color: "#6b6b6b" }}>
          Your team's shared intelligence layer. Ask questions across Jira, Confluence, and your codebase — or open a Feature workspace to collaborate across roles.
        </p>
      </div>

      {/* Quick actions */}
      <div className="flex flex-col gap-3 w-full max-w-sm">
        <button onClick={onGeneralChat}
          className="flex items-center gap-3 px-5 py-3.5 rounded-xl text-sm font-semibold transition-all"
          style={{ background: "#F04E2B", color: "#ffffff" }}
          onMouseEnter={e => (e.currentTarget.style.background = "#c73d1e")}
          onMouseLeave={e => (e.currentTarget.style.background = "#F04E2B")}>
          <span>💬</span>
          Start a general chat
        </button>
        <div className="text-xs" style={{ color: "#999999" }}>or select a feature in the sidebar</div>
      </div>

      {/* Hint cards */}
      <div className="grid grid-cols-3 gap-3 mt-2 w-full max-w-xl">
        {[
          { icon: "🔍", label: "Discover", desc: "Search existing capabilities in the codebase" },
          { icon: "✍️", label: "Draft", desc: "Create Jira stories grounded in prior decisions" },
          { icon: "💡", label: "Takeaways", desc: "Save team decisions that surface automatically" },
        ].map(h => (
          <div key={h.label} className="p-4 rounded-xl text-left"
            style={{ background: "#f2f2f2", border: "1px solid #e5e5e5" }}>
            <div className="text-lg mb-2">{h.icon}</div>
            <div className="text-sm font-semibold mb-1" style={{ color: "#1a1a1a" }}>{h.label}</div>
            <div className="text-xs" style={{ color: "#6b6b6b" }}>{h.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
