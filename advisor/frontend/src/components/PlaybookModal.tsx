import { useEffect, useState } from "react";
import { fetchTags } from "../services/notes";

interface Props {
  initial?: {
    title: string;
    body: string;
    pinned: boolean;
    tags: string[];
  };
  onSave: (data: { title: string; body: string; pinned: boolean; tags: string[] }) => void;
  onClose: () => void;
  saving?: boolean;
}

export function PlaybookModal({ initial, onSave, onClose, saving }: Props) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [pinned, setPinned] = useState(initial?.pinned ?? false);
  const [tagInput, setTagInput] = useState((initial?.tags ?? []).join(", "));
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  useEffect(() => {
    fetchTags().then(setSuggestions).catch(() => {});
  }, []);

  function parseTags(): string[] {
    return tagInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
  }

  // Show autocomplete when the user is typing the last tag segment.
  const lastSegment = tagInput.split(",").pop()?.trim().toLowerCase() ?? "";
  const filtered = lastSegment
    ? suggestions.filter(
        (s) =>
          s.toLowerCase().startsWith(lastSegment) &&
          !parseTags().includes(s),
      )
    : [];

  function selectSuggestion(tag: string) {
    const existing = tagInput.split(",").slice(0, -1).map((t) => t.trim()).filter(Boolean);
    existing.push(tag);
    setTagInput(existing.join(", ") + ", ");
    setShowSuggestions(false);
  }

  function handleSubmit() {
    onSave({ title: title.trim(), body: body.trim(), pinned, tags: parseTags() });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          {initial ? "Edit Playbook Entry" : "New Playbook Entry"}
        </h2>

        <div className="overflow-y-auto flex-1 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Title
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              placeholder="Entry title"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Body <span className="text-gray-400 font-normal">(Markdown)</span>
            </label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={5}
              maxLength={2048}
              placeholder="Write your playbook entry…"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-400 mt-1">
              {body.length}/2048 characters
            </p>
          </div>

          <div className="relative">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tags <span className="text-gray-400 font-normal">(comma-separated)</span>
            </label>
            <input
              type="text"
              value={tagInput}
              onChange={(e) => {
                setTagInput(e.target.value);
                setShowSuggestions(true);
              }}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
              placeholder="e.g. maintenance, vendor"
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {showSuggestions && filtered.length > 0 && (
              <div className="absolute z-10 left-0 right-0 mt-1 bg-white border border-gray-200 rounded shadow-lg max-h-32 overflow-y-auto">
                {filtered.map((tag) => (
                  <button
                    key={tag}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectSuggestion(tag)}
                    className="block w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 text-gray-700"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            )}
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={pinned}
              onChange={(e) => setPinned(e.target.checked)}
              className="rounded border-gray-300"
            />
            Pin this entry (always included in advisor context)
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving || !body.trim()}
            className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
