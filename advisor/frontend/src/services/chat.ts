import type { ChatConversation, ChatFrame } from "../types";

const BASE = "/api/chat";

export async function fetchLatestConversation(): Promise<ChatConversation | null> {
  const response = await fetch(`${BASE}/conversations/latest`);
  if (response.status === 204) return null;
  if (!response.ok) {
    throw new Error(`Failed to fetch latest conversation: ${response.status}`);
  }
  return (await response.json()) as ChatConversation;
}

export async function createConversation(): Promise<ChatConversation> {
  const response = await fetch(`${BASE}/conversations`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to create conversation: ${response.status}`);
  }
  return (await response.json()) as ChatConversation;
}

export async function fetchConversation(id: number): Promise<ChatConversation> {
  const response = await fetch(`${BASE}/conversations/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch conversation ${id}: ${response.status}`);
  }
  return (await response.json()) as ChatConversation;
}

/**
 * POST a user message and yield ndjson frames from the streaming response.
 * The caller should pass an AbortSignal from an AbortController so the stop
 * button can cancel in-flight generation.
 */
export async function* streamChatMessage(
  conversationId: number,
  userText: string,
  signal: AbortSignal,
): AsyncGenerator<ChatFrame, void, unknown> {
  const response = await fetch(
    `${BASE}/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: userText }),
      signal,
    },
  );
  if (!response.ok || !response.body) {
    throw new Error(`Chat stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newlineIdx;
      while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newlineIdx).trim();
        buffer = buffer.slice(newlineIdx + 1);
        if (!line) continue;
        try {
          yield JSON.parse(line) as ChatFrame;
        } catch {
          // ignore malformed frames — backend should not send them
        }
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // noop
    }
  }
}
