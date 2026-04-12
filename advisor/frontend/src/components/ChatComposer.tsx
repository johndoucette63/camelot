import { useState, type KeyboardEvent } from "react";

interface Props {
  onSubmit: (text: string) => void;
  onStop: () => void;
  onSuggestNotes?: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  hasMessages?: boolean;
  suggestingNotes?: boolean;
}

export function ChatComposer({ onSubmit, onStop, onSuggestNotes, isStreaming, disabled, hasMessages, suggestingNotes }: Props) {
  const [text, setText] = useState("");

  const canSubmit = !isStreaming && !disabled && text.trim().length > 0;

  const submit = () => {
    if (!canSubmit) return;
    onSubmit(text.trim());
    setText("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      {onSuggestNotes && hasMessages && !isStreaming && (
        <div className="mx-auto max-w-3xl mb-2 flex justify-end">
          <button
            type="button"
            onClick={onSuggestNotes}
            disabled={suggestingNotes}
            className="text-xs px-3 py-1 border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            {suggestingNotes ? "Analyzing…" : "Suggest notes"}
          </button>
        </div>
      )}
      <div className="mx-auto flex max-w-3xl gap-2">
        <textarea
          className="flex-1 resize-none rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          rows={2}
          placeholder="Ask the advisor about your network…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-red-700"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}

export default ChatComposer;
