import type {
  Note,
  NoteListResponse,
  NoteTargetType,
  SuggestNotesResponse,
} from "../types";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = (body as { detail?: string }).detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function fetchNotes(
  targetType: NoteTargetType,
  targetId?: number | null,
  tag?: string,
): Promise<NoteListResponse> {
  const params = new URLSearchParams({ target_type: targetType });
  if (targetId != null) params.set("target_id", String(targetId));
  if (tag) params.set("tag", tag);
  const res = await fetch(`/api/notes?${params}`);
  return handle<NoteListResponse>(res);
}

export async function createNote(input: {
  target_type: NoteTargetType;
  target_id?: number | null;
  title?: string | null;
  body: string;
  pinned?: boolean;
  tags?: string[];
}): Promise<Note> {
  const res = await fetch("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<Note>(res);
}

export async function updateNote(
  id: number,
  input: {
    title?: string | null;
    body?: string;
    pinned?: boolean;
    tags?: string[];
  },
): Promise<Note> {
  const res = await fetch(`/api/notes/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<Note>(res);
}

export async function deleteNote(id: number): Promise<void> {
  const res = await fetch(`/api/notes/${id}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`Failed to delete note: ${res.status}`);
  }
}

export async function fetchTags(): Promise<string[]> {
  const res = await fetch("/api/notes/tags");
  const data = await handle<{ tags: string[] }>(res);
  return data.tags;
}

export async function suggestNotes(
  conversationId: number,
): Promise<SuggestNotesResponse> {
  const res = await fetch(
    `/api/chat/conversations/${conversationId}/suggest-notes`,
    { method: "POST" },
  );
  return handle<SuggestNotesResponse>(res);
}

export async function rejectSuggestion(
  body: string,
  conversationId?: number,
): Promise<void> {
  const res = await fetch("/api/notes/rejected-suggestions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body, conversation_id: conversationId }),
  });
  if (!res.ok) {
    throw new Error(`Failed to reject suggestion: ${res.status}`);
  }
}
