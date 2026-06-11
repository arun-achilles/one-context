const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────

export interface Feature {
  id: string;
  name: string;
  description: string | null;
  status: "planned" | "in_progress" | "shipped" | "paused";
  jira_epic: string | null;
  created_by: string | null;
  created_at: string;
  session_count?: number;
  link_count?: number;
}

export interface Session {
  id: number;
  feature_id: string;
  conversation_id: number;
  role: string | null;
  author: string | null;
  summary: string | null;
  created_at: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  author: string | null;
  cited_sources: string[];
  created_at: string;
}

export interface Conversation {
  id: number;
  topic: string;
  created_at: string;
}

// ── Features ─────────────────────────────────────────────────────────────────

export async function listFeatures(): Promise<Feature[]> {
  const res = await fetch(`${BASE}/features`);
  if (!res.ok) throw new Error("Failed to load features");
  return res.json();
}

export async function createFeature(name: string, description: string, created_by: string): Promise<Feature> {
  const res = await fetch(`${BASE}/features`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, created_by }),
  });
  if (!res.ok) throw new Error("Failed to create feature");
  return res.json();
}

export async function getFeature(id: string): Promise<Feature & { sessions: Session[]; context: string }> {
  const res = await fetch(`${BASE}/features/${id}`);
  if (!res.ok) throw new Error("Feature not found");
  return res.json();
}

// ── Sessions ─────────────────────────────────────────────────────────────────

export async function startSession(featureId: string, role: string, author: string): Promise<{ session_id: number; conversation_id: number; feature_id: string; feature_context: string }> {
  const res = await fetch(`${BASE}/features/${featureId}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, author }),
  });
  if (!res.ok) throw new Error("Failed to start session");
  return res.json();
}

// ── Conversations ─────────────────────────────────────────────────────────────

export async function createConversation(topic: string): Promise<Conversation> {
  const res = await fetch(`${BASE}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic }),
  });
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json();
}

export async function getMessages(conversationId: number): Promise<Message[]> {
  const res = await fetch(`${BASE}/conversations/${conversationId}/messages`);
  if (!res.ok) return [];
  return res.json();
}

// ── Streaming chat ─────────────────────────────────────────────────────────────

export async function* streamChat(
  conversationId: number,
  message: string,
  author: string
): AsyncGenerator<{ type: string; content?: string; sources?: string[]; detail?: string }> {
  const res = await fetch(`${BASE}/conversations/${conversationId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, author }),
  });

  if (!res.ok || !res.body) {
    yield { type: "error", detail: "Request failed" };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          yield JSON.parse(line.slice(6));
        } catch {
          // skip malformed
        }
      }
    }
  }
}
