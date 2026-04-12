import { useEffect, useState } from "react";
import type { Note, NoteTargetType } from "../types";
import { createNote, deleteNote, fetchNotes, updateNote } from "../services/notes";

interface Props {
  targetType: NoteTargetType;
  targetId?: number | null;
}

export function NotesList({ targetType, targetId }: Props) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const resp = await fetchNotes(targetType, targetId);
      setNotes(resp.notes);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notes");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [targetType, targetId]);

  async function handleAdd() {
    if (!body.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createNote({
        target_type: targetType,
        target_id: targetId,
        body: body.trim(),
      });
      setBody("");
      setShowAdd(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create note");
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdate(note: Note) {
    if (!body.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await updateNote(note.id, { body: body.trim() });
      setBody("");
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update note");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    setError(null);
    try {
      await deleteNote(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete note");
    }
  }

  async function handleTogglePin(note: Note) {
    setError(null);
    try {
      await updateNote(note.id, { pinned: !note.pinned });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update pin");
    }
  }

  function startEdit(note: Note) {
    setEditingId(note.id);
    setBody(note.body);
    setShowAdd(false);
  }

  function cancelEdit() {
    setEditingId(null);
    setBody("");
  }

  if (loading) {
    return <p className="text-sm text-gray-400">Loading notes…</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-gray-700">
          Notes ({notes.length})
        </h4>
        {!showAdd && editingId === null && (
          <button
            onClick={() => { setShowAdd(true); setBody(""); }}
            className="text-xs text-blue-600 hover:text-blue-700 font-medium"
          >
            + Add note
          </button>
        )}
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {showAdd && (
        <div className="border border-blue-200 rounded p-3 bg-blue-50/50">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
            maxLength={2048}
            placeholder="Write a note (Markdown supported)…"
            className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              onClick={() => { setShowAdd(false); setBody(""); }}
              className="text-xs px-3 py-1 border border-gray-300 rounded hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={saving || !body.trim()}
              className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}

      {notes.length === 0 && !showAdd && (
        <p className="text-xs text-gray-400 italic">No notes yet</p>
      )}

      {notes.map((note) => (
        <div
          key={note.id}
          className="border border-gray-200 rounded p-3 text-sm"
        >
          {editingId === note.id ? (
            <>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={3}
                maxLength={2048}
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <div className="mt-2 flex justify-end gap-2">
                <button
                  onClick={cancelEdit}
                  className="text-xs px-3 py-1 border border-gray-300 rounded hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleUpdate(note)}
                  disabled={saving || !body.trim()}
                  className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Update"}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-start justify-between gap-2">
                <p className="text-gray-700 whitespace-pre-wrap flex-1">
                  {note.body}
                </p>
                <button
                  onClick={() => handleTogglePin(note)}
                  title={note.pinned ? "Unpin" : "Pin"}
                  className={`shrink-0 text-xs px-1.5 py-0.5 rounded ${
                    note.pinned
                      ? "bg-yellow-100 text-yellow-700"
                      : "bg-gray-100 text-gray-500 hover:bg-yellow-50"
                  }`}
                >
                  {note.pinned ? "pinned" : "pin"}
                </button>
              </div>
              <div className="mt-2 flex items-center gap-3 text-xs text-gray-400">
                <span>{new Date(note.updated_at).toLocaleString()}</span>
                <button
                  onClick={() => startEdit(note)}
                  className="text-blue-500 hover:text-blue-600"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(note.id)}
                  className="text-red-500 hover:text-red-600"
                >
                  Delete
                </button>
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
