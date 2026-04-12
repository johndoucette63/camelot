import { useState } from "react";
import type { NoteSuggestion } from "../types";
import { createNote, rejectSuggestion } from "../services/notes";

interface Props {
  suggestions: NoteSuggestion[];
  conversationId: number;
  onDone: () => void;
}

export function NoteSuggestionPanel({
  suggestions,
  conversationId,
  onDone,
}: Props) {
  const [items, setItems] = useState(
    suggestions.map((s) => ({ ...s, status: "pending" as "pending" | "approved" | "rejected" | "editing" })),
  );
  const [editBody, setEditBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pending = items.filter((i) => i.status === "pending" || i.status === "editing");

  async function handleApprove(index: number, body?: string) {
    setSaving(true);
    setError(null);
    const item = items[index]!;
    try {
      await createNote({
        target_type: item.target_type,
        target_id: item.target_id,
        body: body ?? item.body,
      });
      setItems((prev) =>
        prev.map((it, i) => (i === index ? { ...it, status: "approved" } : it)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save note");
    } finally {
      setSaving(false);
    }
  }

  async function handleReject(index: number) {
    setError(null);
    const item = items[index]!;
    try {
      await rejectSuggestion(item.body, conversationId);
      setItems((prev) =>
        prev.map((it, i) => (i === index ? { ...it, status: "rejected" } : it)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject");
    }
  }

  function startEdit(index: number) {
    setEditBody(items[index]!.body);
    setItems((prev) =>
      prev.map((it, i) => (i === index ? { ...it, status: "editing" } : it)),
    );
  }

  if (pending.length === 0 && items.every((i) => i.status !== "pending" && i.status !== "editing")) {
    return (
      <div className="border border-green-200 rounded-lg p-3 bg-green-50 text-sm text-green-700">
        All suggestions handled.{" "}
        <button onClick={onDone} className="underline font-medium">
          Dismiss
        </button>
      </div>
    );
  }

  return (
    <div className="border border-blue-200 rounded-lg p-4 bg-blue-50/50 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-gray-700">
          Suggested Notes ({pending.length} remaining)
        </h4>
        <button
          onClick={onDone}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          Dismiss all
        </button>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {items.map((item, index) => {
        if (item.status === "approved") {
          return (
            <div key={index} className="text-xs text-green-600 italic">
              Saved as note
            </div>
          );
        }
        if (item.status === "rejected") {
          return (
            <div key={index} className="text-xs text-gray-400 italic">
              Rejected
            </div>
          );
        }
        return (
          <div
            key={index}
            className="border border-gray-200 rounded p-3 bg-white text-sm"
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                {item.target_type}
              </span>
              {item.target_label && (
                <span className="text-xs text-gray-500">
                  {item.target_label}
                </span>
              )}
            </div>
            {item.status === "editing" ? (
              <>
                <textarea
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  rows={3}
                  maxLength={2048}
                  className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm mt-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <div className="mt-2 flex gap-2 justify-end">
                  <button
                    onClick={() =>
                      setItems((prev) =>
                        prev.map((it, i) =>
                          i === index ? { ...it, status: "pending" } : it,
                        ),
                      )
                    }
                    className="text-xs px-3 py-1 border border-gray-300 rounded hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => handleApprove(index, editBody.trim())}
                    disabled={saving || !editBody.trim()}
                    className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    Save
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-gray-700 mt-1">{item.body}</p>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => handleApprove(index)}
                    disabled={saving}
                    className="text-xs px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => startEdit(index)}
                    className="text-xs px-3 py-1 border border-gray-300 rounded hover:bg-gray-50"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleReject(index)}
                    className="text-xs px-3 py-1 text-red-600 border border-red-200 rounded hover:bg-red-50"
                  >
                    Reject
                  </button>
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
