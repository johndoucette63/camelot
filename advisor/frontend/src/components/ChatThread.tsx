import { useEffect, useRef } from "react";
import type { ChatMessage as ChatMessageType } from "../types";
import { ChatMessage } from "./ChatMessage";

interface Props {
  messages: ChatMessageType[];
  streamingMessageId: number | null;
}

export function ChatThread({ messages, streamingMessageId }: Props) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const lastContentLen = messages[messages.length - 1]?.content?.length ?? 0;

  useEffect(() => {
    // scrollIntoView isn't implemented in jsdom; guard so tests don't crash.
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages.length, lastContentLen]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-gray-400">
        <div className="text-center">
          <p className="text-sm">
            Ask a question about your network to get started.
          </p>
          <p className="mt-1 text-xs">
            Try: &ldquo;Which services are down right now?&rdquo;
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-3">
        {messages.map((m) => (
          <ChatMessage
            key={m.id}
            message={m}
            streaming={m.id === streamingMessageId}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

export default ChatThread;
