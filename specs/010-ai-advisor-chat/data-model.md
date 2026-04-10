# Data Model: AI-Powered Advisor Chat

**Feature**: 010-ai-advisor-chat
**Storage**: PostgreSQL 16 in the existing `advisor_pgdata` Docker volume
**Migration**: `advisor/backend/migrations/versions/003_chat_conversations.py` (new)

This feature adds two tables — `conversations` and `messages` — to the existing advisor schema. It does not modify any F4.1/F4.2/F4.3 tables.

---

## Entity: Conversation

A persisted chat session. The UI in v1 shows at most one conversation at a time, but the table is designed so that future features (conversation browser, search, export) can be added without a schema change.

### Fields

| Field | Type | Nullable | Default | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary key. Stable identifier for the conversation, used in URLs and API paths. |
| `created_at` | `TIMESTAMPTZ` | NO | `now()` | When the conversation was first created (when the user clicked "New chat" or first opened the advisor with no prior conversation). Never modified. |
| `updated_at` | `TIMESTAMPTZ` | NO | `now()` | When the conversation last had activity (last message inserted). Bumped on every message insert. Used by the "most recent conversation" query for FR-006a. |
| `title` | `TEXT` | YES | `NULL` | Optional short label for the conversation. Not populated in v1; reserved for a future feature that auto-titles from the first user message. |

### Constraints

- `PRIMARY KEY (id)`
- No foreign keys (no ownership linkage — single-admin deployment).

### Indexes

- Primary key index on `id`.
- `CREATE INDEX ix_conversations_updated_at ON conversations (updated_at DESC)` — supports the "latest conversation" lookup in FR-006a.

### State transitions

A conversation has no explicit state. It is effectively always "active" once created. Deletion cascades to its messages (handled on the message side via `ON DELETE CASCADE`).

### Validation rules

- `title` (if populated in a future version): free text, no constraint.

---

## Entity: Message

One entry in a conversation. Both user questions and advisor replies are stored here, distinguished by `role`. Assistant messages are created at stream start with empty content and finalized when the stream completes or is cancelled.

### Fields

| Field | Type | Nullable | Default | Description |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary key. Returned in the `done` / `error` frames so the client can correlate. |
| `conversation_id` | `UUID` | NO | — | FK to `conversations.id`. |
| `role` | `TEXT` | NO | — | `'user'` or `'assistant'`. |
| `content` | `TEXT` | NO | `''` | The text of the message. For assistant messages this is empty while streaming and written once at the end (normal completion or cancellation). For user messages it is set at insert time. |
| `created_at` | `TIMESTAMPTZ` | NO | `now()` | When the row was inserted. For assistant messages this is when the stream began, not when it completed. Used for `ORDER BY` to present the thread in chronological order. |
| `finished_at` | `TIMESTAMPTZ` | YES | `NULL` | When the assistant message finished (either completed normally or was cancelled). `NULL` while streaming. Always `NULL` for user messages (they are instantaneous). |
| `cancelled` | `BOOLEAN` | NO | `FALSE` | `TRUE` if the assistant message was interrupted by a user cancellation. The partial `content` is still saved. Always `FALSE` for user messages. |

### Constraints

- `PRIMARY KEY (id)`
- `FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE`
- `CHECK (role IN ('user', 'assistant'))`
- `CHECK (role = 'user' OR cancelled = FALSE OR content != '')` — if a message is cancelled, it must have some partial content (prevents accidentally saving empty cancelled assistant messages — the frontend won't display empty bubbles).

### Indexes

- Primary key index on `id`.
- `CREATE INDEX ix_messages_conversation_id_created_at ON messages (conversation_id, created_at ASC)` — supports the "fetch all messages for a conversation in order" query, which is the hot read path.

### State transitions

User messages have no transitions — they are created in their final state.

Assistant messages have this lifecycle:

```text
[not yet created]
      │
      │ POST /chat/conversations/{id}/messages begins; assistant row inserted
      │ with content='', finished_at=NULL, cancelled=FALSE
      ▼
   streaming
      │
      ├── normal completion: UPDATE content=<buffer>, finished_at=now()
      │                      → finished-normal
      │
      └── client disconnect / AbortController.abort() detected via
          request.is_disconnected(): UPDATE content=<partial buffer>,
          finished_at=now(), cancelled=TRUE
          → finished-cancelled
```

A single `UPDATE` finalizes the row. There are no intermediate writes per token.

### Validation rules

- `content` for a user message MUST be non-empty and non-whitespace at the API boundary (enforced by the request body schema, not a DB constraint).

---

## Relationships

```text
conversations (1) ──────< (N) messages
                  on delete cascade
```

No other tables are touched by this feature. The prompt assembler reads from existing F4.2 tables (`devices`, `device_annotations`) and F4.3 tables (`services`, `service_definitions`, `health_check_results`, `alerts`, `events`) but does not write to them.

---

## Alembic migration sketch

Location: `advisor/backend/migrations/versions/003_chat_conversations.py`

```python
"""chat conversations and messages

Revision ID: 003
Revises: 002
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa


revision = "003"
down_revision = "002"


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_conversations_updated_at",
        "conversations",
        [sa.text("updated_at DESC")],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", sa.UUID(),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.CheckConstraint("role IN ('user', 'assistant')",
                           name="messages_role_check"),
        sa.CheckConstraint(
            "role = 'user' OR cancelled = false OR content != ''",
            name="messages_cancelled_has_content",
        ),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_id_created_at",
                  table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_updated_at", table_name="conversations")
    op.drop_table("conversations")
```

The `pgcrypto` extension (providing `gen_random_uuid()`) is already enabled from F4.2's migration `001_network_discovery.py`. No extension management needed here.
