import { useEffect, useState } from "react";
import type { Note } from "../types";
import { createNote, deleteNote, fetchNotes, fetchTags, updateNote } from "../services/notes";
import { PlaybookModal } from "../components/PlaybookModal";

export default function Playbook() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [editingNote, setEditingNote] = useState<Note | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const [resp, tags] = await Promise.all([
        fetchNotes("playbook", null, activeTag ?? undefined),
        fetchTags(),
      ]);
      setNotes(resp.notes);
      setAllTags(tags);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    load();
  }, [activeTag]);

  async function handleCreate(data: {
    title: string;
    body: string;
    pinned: boolean;
    tags: string[];
  }) {
    setSaving(true);
    setError(null);
    try {
      await createNote({
        target_type: "playbook",
        title: data.title || null,
        body: data.body,
        pinned: data.pinned,
        tags: data.tags,
      });
      setShowModal(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create");
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdate(data: {
    title: string;
    body: string;
    pinned: boolean;
    tags: string[];
  }) {
    if (!editingNote) return;
    setSaving(true);
    setError(null);
    try {
      await updateNote(editingNote.id, {
        title: data.title || undefined,
        body: data.body,
        pinned: data.pinned,
        tags: data.tags,
      });
      setEditingNote(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
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
      setError(err instanceof Error ? err.message : "Failed to delete");
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Playbook</h1>
          <p className="text-sm text-gray-500 mt-1">
            Network-wide notes, conventions, and maintenance schedules
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          New entry
        </button>
      </div>

      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          <button
            onClick={() => setActiveTag(null)}
            className={`px-2.5 py-1 text-xs rounded-full font-medium ${
              activeTag === null
                ? "bg-blue-100 text-blue-700"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            All
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setActiveTag(tag === activeTag ? null : tag)}
              className={`px-2.5 py-1 text-xs rounded-full font-medium ${
                activeTag === tag
                  ? "bg-blue-100 text-blue-700"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {error && (
        <p className="mb-4 text-sm text-red-600 bg-red-50 p-3 rounded">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : notes.length === 0 ? (
        <p className="text-sm text-gray-400 italic">
          {activeTag ? `No entries tagged "${activeTag}"` : "No playbook entries yet"}
        </p>
      ) : (
        <div className="space-y-3">
          {notes.map((note) => (
            <div
              key={note.id}
              className="border border-gray-200 rounded-lg p-4 bg-white"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-medium text-gray-800">
                      {note.title || "(untitled)"}
                    </h3>
                    {note.pinned && (
                      <span className="text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-700 rounded">
                        pinned
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 whitespace-pre-wrap">
                    {note.body}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {note.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-1.5 py-0.5 text-xs bg-gray-100 text-gray-600 rounded"
                      >
                        {tag}
                      </span>
                    ))}
                    <span className="text-xs text-gray-400">
                      {new Date(note.updated_at).toLocaleString()}
                    </span>
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => setEditingNote(note)}
                    className="text-xs text-blue-500 hover:text-blue-600"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(note.id)}
                    className="text-xs text-red-500 hover:text-red-600"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <PlaybookModal
          onSave={handleCreate}
          onClose={() => setShowModal(false)}
          saving={saving}
        />
      )}

      {editingNote && (
        <PlaybookModal
          initial={{
            title: editingNote.title ?? "",
            body: editingNote.body,
            pinned: editingNote.pinned,
            tags: editingNote.tags,
          }}
          onSave={handleUpdate}
          onClose={() => setEditingNote(null)}
          saving={saving}
        />
      )}
    </div>
  );
}
