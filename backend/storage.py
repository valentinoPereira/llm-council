"""SQLite-backed storage for conversations.

Persists conversations and messages in a single SQLite database file
(`council.db` under DATA_DIR) via `aiosqlite`. All public functions are
async coroutines, so the API layer can `await` them directly without
`asyncio.to_thread` wrappers.

Schema:

    conversations(id TEXT PK, created_at TEXT, title TEXT)
    messages(id INTEGER PK, conversation_id TEXT FK, role TEXT,
            content TEXT, stage1 TEXT, stage2 TEXT, stage3 TEXT,
            metadata TEXT, created_at TEXT)

Assistant-message stage1/stage2/stage3/metadata are stored as JSON blobs
and decoded back to their native Python shapes on read.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite

from .config import DATA_DIR

# Cap user input length to avoid runaway token usage across ~9 council
# LLM calls per message.
MAX_USER_MESSAGE_LENGTH = 50_000

# Single SQLite database file lives alongside the old JSON data dir.
DATABASE_PATH = os.path.join(DATA_DIR, "council.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT 'New Conversation'
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT,
    stage1 TEXT,
    stage2 TEXT,
    stage3 TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id);
"""

# Shared connection, opened in init_db() (called from the FastAPI lifespan
# at startup) and closed in close_db() (lifespan shutdown). _get_db()
# lazily initializes on first use so storage also works without a lifespan
# (e.g. under httpx.ASGITransport in tests, or the migration CLI).
_db: Optional[aiosqlite.Connection] = None
_init_lock = asyncio.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Open the shared connection and ensure the schema exists.

    Idempotent: safe to call from the lifespan and again from _get_db().
    """
    global _db
    os.makedirs(DATA_DIR, exist_ok=True)
    _db = await aiosqlite.connect(DATABASE_PATH)
    _db.row_factory = aiosqlite.Row
    # WAL gives concurrent readers + a single writer without blocking; the
    # event loop is the only writer.
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript(_SCHEMA)
    await _db.commit()


async def _get_db() -> aiosqlite.Connection:
    """Return the shared connection, initializing it lazily on first use."""
    global _db
    if _db is None:
        async with _init_lock:
            if _db is None:
                await init_db()
    return _db


async def close_db() -> None:
    """Close the shared connection. Called from the lifespan on shutdown."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def _db_conn() -> aiosqlite.Connection:
    """Synchronous accessor for the already-open connection (used by the
    migration CLI after it has called init_db())."""
    if _db is None:
        raise RuntimeError("Database not initialized; call init_db() first")
    return _db


def _loads(value: Optional[str]) -> Optional[Any]:
    if value is None:
        return None
    return json.loads(value)


def _row_to_message(row: aiosqlite.Row) -> Dict[str, Any]:
    """Reconstruct a message dict from a DB row."""
    if row["role"] == "user":
        return {"role": "user", "content": row["content"]}
    msg: Dict[str, Any] = {
        "role": "assistant",
        "stage1": _loads(row["stage1"]),
        "stage2": _loads(row["stage2"]),
        "stage3": _loads(row["stage3"]),
    }
    metadata = _loads(row["metadata"])
    if metadata is not None:
        msg["metadata"] = metadata
    return msg


async def create_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        New conversation dict (with empty messages list)
    """
    db = await _get_db()
    created_at = _utc_now_iso()
    await db.execute(
        "INSERT INTO conversations (id, created_at, title) VALUES (?, ?, ?)",
        (conversation_id, created_at, "New Conversation"),
    )
    await db.commit()
    return {
        "id": conversation_id,
        "created_at": created_at,
        "title": "New Conversation",
        "messages": [],
    }


async def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation with all its messages in insertion order.

    Returns:
        Conversation dict or None if not found.
    """
    db = await _get_db()
    cur = await db.execute(
        "SELECT id, created_at, title FROM conversations WHERE id = ?",
        (conversation_id,),
    )
    crow = await cur.fetchone()
    await cur.close()
    if crow is None:
        return None

    cur = await db.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conversation_id,),
    )
    rows = await cur.fetchall()
    await cur.close()

    messages = [_row_to_message(r) for r in rows]
    return {
        "id": crow["id"],
        "created_at": crow["created_at"],
        "title": crow["title"],
        "messages": messages,
    }


async def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only). The message count comes from a
    LEFT JOIN/COUNT so the cost is a single query, not a per-conversation
    scan.
    """
    db = await _get_db()
    cur = await db.execute(
        """
        SELECT c.id, c.created_at, c.title,
               COUNT(m.id) AS message_count
        FROM conversations c
        LEFT JOIN messages m ON m.conversation_id = c.id
        GROUP BY c.id
        ORDER BY c.created_at DESC
        """
    )
    rows = await cur.fetchall()
    await cur.close()
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "title": r["title"],
            "message_count": r["message_count"],
        }
        for r in rows
    ]


async def add_user_message(conversation_id: str, content: str) -> None:
    """
    Append a user message to a conversation.

    Raises ValueError if the content exceeds MAX_USER_MESSAGE_LENGTH.
    Raises a foreign-key violation if the conversation does not exist.
    """
    if len(content) > MAX_USER_MESSAGE_LENGTH:
        raise ValueError(
            f"Message content exceeds maximum length of {MAX_USER_MESSAGE_LENGTH} characters"
        )
    db = await _get_db()
    await db.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) "
        "VALUES (?, 'user', ?, ?)",
        (conversation_id, content, _utc_now_iso()),
    )
    await db.commit()


async def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append an assistant message with all 3 stages (and optional metadata)
    to a conversation. stage1/stage2/stage3/metadata are stored as JSON
    blobs so their full structure round-trips on read.

    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses
        stage2: List of model rankings
        stage3: Final synthesized response
        metadata: Per-message metadata block holding `label_to_model` and
            `aggregate_rankings`. Persisted so the Aggregate Rankings
            section renders when the conversation is reopened.
    """
    db = await _get_db()
    await db.execute(
        "INSERT INTO messages "
        "(conversation_id, role, content, stage1, stage2, stage3, metadata, created_at) "
        "VALUES (?, 'assistant', NULL, ?, ?, ?, ?, ?)",
        (
            conversation_id,
            json.dumps(stage1) if stage1 is not None else None,
            json.dumps(stage2) if stage2 is not None else None,
            json.dumps(stage3) if stage3 is not None else None,
            json.dumps(metadata) if metadata is not None else None,
            _utc_now_iso(),
        ),
    )
    await db.commit()


async def update_conversation_title(conversation_id: str, title: str) -> None:
    """
    Update the title of a conversation.

    Raises ValueError if the conversation does not exist.
    """
    db = await _get_db()
    cur = await db.execute(
        "UPDATE conversations SET title = ? WHERE id = ?",
        (title, conversation_id),
    )
    await db.commit()
    if cur.rowcount == 0:
        raise ValueError(f"Conversation {conversation_id} not found")
