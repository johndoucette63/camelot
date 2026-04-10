import { useEffect, useRef, useState } from "react";
import { ChatComposer } from "../components/ChatComposer";
import { ChatThread } from "../components/ChatThread";
import {
  createConversation,
  fetchLatestConversation,
  streamChatMessage,
} from "../services/chat";
import type { ChatConversation, ChatMessage } from "../types";

function nowIso(): string {
  return new Date().toISOString();
}

function Chat() {
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const latest = await fetchLatestConversation();
        if (cancelled) return;
        if (latest) {
          setConversation(latest);
        } else {
          const fresh = await createConversation();
          if (!cancelled) setConversation(fresh);
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, []);

  const isStreaming = streamingMessageId !== null;

  const handleNewChat = async () => {
    if (isStreaming) return;
    try {
      const fresh = await createConversation();
      setConversation(fresh);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    // The streaming loop's catch/finally handles state cleanup.
  };

  const handleSubmit = async (text: string) => {
    if (!conversation) return;

    // Optimistically append the user message and an empty assistant shell.
    const tempUserId = -Date.now();
    const tempAssistantId = -Date.now() - 1;
    const userMsg: ChatMessage = {
      id: tempUserId,
      role: "user",
      content: text,
      created_at: nowIso(),
      finished_at: null,
      cancelled: false,
    };
    const assistantMsg: ChatMessage = {
      id: tempAssistantId,
      role: "assistant",
      content: "",
      created_at: nowIso(),
      finished_at: null,
      cancelled: false,
    };
    setConversation({
      ...conversation,
      messages: [...conversation.messages, userMsg, assistantMsg],
    });
    setStreamingMessageId(tempAssistantId);

    const controller = new AbortController();
    abortRef.current = controller;
    let realAssistantId: number | null = null;
    let assistantContent = "";
    let cancelled = false;

    const updateAssistant = (patch: Partial<ChatMessage>) => {
      setConversation((prev) => {
        if (!prev) return prev;
        const targetId = realAssistantId ?? tempAssistantId;
        return {
          ...prev,
          messages: prev.messages.map((m) =>
            m.id === targetId || m.id === tempAssistantId
              ? { ...m, ...patch }
              : m,
          ),
        };
      });
    };

    try {
      for await (const frame of streamChatMessage(
        conversation.id,
        text,
        controller.signal,
      )) {
        if (frame.type === "start") {
          realAssistantId = frame.message_id;
          updateAssistant({ id: frame.message_id });
        } else if (frame.type === "token") {
          assistantContent += frame.content;
          updateAssistant({ content: assistantContent });
        } else if (frame.type === "done") {
          updateAssistant({
            content: assistantContent,
            finished_at: nowIso(),
            cancelled: false,
          });
        } else if (frame.type === "error") {
          updateAssistant({
            content: frame.message,
            finished_at: nowIso(),
            cancelled: false,
          });
        }
      }
    } catch (e) {
      // AbortError is expected on stop; anything else is an unexpected failure.
      const isAbort =
        e instanceof DOMException && e.name === "AbortError";
      if (isAbort) {
        cancelled = true;
      } else {
        updateAssistant({
          content:
            assistantContent ||
            "The advisor encountered an error. Please try again.",
          finished_at: nowIso(),
          cancelled: false,
        });
      }
    } finally {
      if (cancelled) {
        updateAssistant({
          content: assistantContent,
          finished_at: nowIso(),
          cancelled: true,
        });
      }
      setStreamingMessageId(null);
      abortRef.current = null;
    }
  };

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center text-sm text-gray-500">
        Loading chat…
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center text-sm text-red-600">
        Failed to load chat: {loadError}
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-gray-50">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold text-gray-800">Advisor Chat</h1>
          <p className="text-xs text-gray-500">
            Ask questions about your network. Answers are grounded in live
            device and service state.
          </p>
        </div>
        <button
          type="button"
          onClick={handleNewChat}
          disabled={isStreaming}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          New chat
        </button>
      </header>

      <ChatThread
        messages={conversation?.messages ?? []}
        streamingMessageId={streamingMessageId}
      />

      <ChatComposer
        onSubmit={handleSubmit}
        onStop={handleStop}
        isStreaming={isStreaming}
      />
    </div>
  );
}

export default Chat;
