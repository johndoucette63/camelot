import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ChatMessage as ChatMessageType } from "../../types";
import { ChatMessage } from "../ChatMessage";
import { ChatThread } from "../ChatThread";

function msg(overrides: Partial<ChatMessageType>): ChatMessageType {
  return {
    id: 1,
    role: "user",
    content: "hello",
    created_at: new Date().toISOString(),
    finished_at: null,
    cancelled: false,
    ...overrides,
  };
}

describe("ChatMessage", () => {
  it("renders the message content", () => {
    render(<ChatMessage message={msg({ content: "hello world" })} />);
    expect(screen.getByText("hello world")).toBeTruthy();
  });

  it("shows a (stopped) indicator for cancelled assistant messages", () => {
    render(
      <ChatMessage
        message={msg({
          id: 2,
          role: "assistant",
          content: "partial reply",
          cancelled: true,
        })}
      />,
    );
    expect(screen.getByText(/stopped/i)).toBeTruthy();
    expect(screen.getByText("partial reply")).toBeTruthy();
  });
});

describe("ChatThread", () => {
  it("shows empty-state prompt when there are no messages", () => {
    render(<ChatThread messages={[]} streamingMessageId={null} />);
    expect(screen.getByText(/ask a question about your network/i)).toBeTruthy();
  });

  it("renders user and assistant messages in order", () => {
    const messages: ChatMessageType[] = [
      msg({ id: 1, role: "user", content: "What services are down?" }),
      msg({
        id: 2,
        role: "assistant",
        content: "Deluge on Torrentbox is down.",
      }),
    ];
    render(<ChatThread messages={messages} streamingMessageId={null} />);
    expect(screen.getByText("What services are down?")).toBeTruthy();
    expect(screen.getByText("Deluge on Torrentbox is down.")).toBeTruthy();
  });
});
