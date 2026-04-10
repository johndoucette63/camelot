import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatComposer } from "../ChatComposer";

describe("ChatComposer", () => {
  it("shows a Send button when not streaming and invokes onSubmit", () => {
    const onSubmit = vi.fn();
    const onStop = vi.fn();
    render(
      <ChatComposer onSubmit={onSubmit} onStop={onStop} isStreaming={false} />,
    );

    const textarea = screen.getByPlaceholderText(/ask the advisor/i);
    fireEvent.change(textarea, { target: { value: "what's up" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(onSubmit).toHaveBeenCalledWith("what's up");
    expect(onStop).not.toHaveBeenCalled();
  });

  it("disables Send on empty or whitespace-only input", () => {
    render(
      <ChatComposer
        onSubmit={vi.fn()}
        onStop={vi.fn()}
        isStreaming={false}
      />,
    );
    const sendBtn = screen.getByRole("button", {
      name: /send/i,
    }) as HTMLButtonElement;
    expect(sendBtn.disabled).toBe(true);

    const textarea = screen.getByPlaceholderText(/ask the advisor/i);
    fireEvent.change(textarea, { target: { value: "   " } });
    expect(sendBtn.disabled).toBe(true);
  });

  it("shows a Stop button while streaming and invokes onStop when clicked", () => {
    const onStop = vi.fn();
    render(
      <ChatComposer
        onSubmit={vi.fn()}
        onStop={onStop}
        isStreaming={true}
      />,
    );
    const stopBtn = screen.getByRole("button", { name: /stop/i });
    fireEvent.click(stopBtn);
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("submits on Enter key without Shift", () => {
    const onSubmit = vi.fn();
    render(
      <ChatComposer
        onSubmit={onSubmit}
        onStop={vi.fn()}
        isStreaming={false}
      />,
    );
    const textarea = screen.getByPlaceholderText(/ask the advisor/i);
    fireEvent.change(textarea, { target: { value: "ping" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSubmit).toHaveBeenCalledWith("ping");
  });
});
