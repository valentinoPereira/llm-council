"""JSON-based storage for conversations.

This module persists conversations as individual JSON files under DATA_DIR,
plus a small index.json holding sidebar metadata so list_conversations() does
not have to read and parse every conversation body.

Concurrency note: this module is currently synchronous and intended to be
called via asyncio.to_thread from the async API layer, so it does not block
the event loop on disk I/O.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import DATA_DIR
from .council import calculate_aggregate_rankings

# Cap user input length to avoid runaway token usage across ~9 council
# LLM calls per message.
MAX_USER_MESSAGE_LENGTH = 50_000

# Serializes load->mutate->save cycles across worker threads (storage runs in
# asyncio.to_thread). Without this, two concurrent requests to the same
# conversation could lose each other's messages or index entries.
_STORAGE_LOCK = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_data_dir() -> None:
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation."""
    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def get_index_path() -> str:
    """Get the path to the lightweight metadata index file."""
    return os.path.join(DATA_DIR, "index.json")


def _tmp_path(path: str) -> str:
    """
    Unique temp path for atomic writes. Includes pid + thread id so a lock-free
    reader (e.g., an index rebuild triggered from list_conversations) can never
    collide with a lock-holding mutator writing the same target file.
    """
    return f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"


def _load_index() -> Dict[str, Dict[str, Any]]:
    """
    Load the metadata index.

    If the index file is missing or corrupt (e.g., first run after upgrading
    from a version without an index), it is rebuilt from the conversation
    files on disk so existing conversations are not lost from the listing.
    """
    path = get_index_path()
    if not os.path.exists(path):
        return _rebuild_index()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        # Valid JSON but wrong shape (e.g., a list): rebuild.
        return _rebuild_index()
    except (json.JSONDecodeError, OSError):
        # Corrupt index: rebuild from the conversation files on disk rather
        # than returning an empty (and permanently stale) listing.
        return _rebuild_index()


def _rebuild_index() -> Dict[str, Dict[str, Any]]:
    """
    Scan DATA_DIR for conversation files and build a fresh metadata index.
    This is a one-time migration cost for data created before the index
    existed.
    """
    ensure_data_dir()
    index: Dict[str, Dict[str, Any]] = {}
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json") or filename == "index.json":
            continue
        path = os.path.join(DATA_DIR, filename)
        try:
            with open(path, "r") as f:
                conv = json.load(f)
            if isinstance(conv, dict) and "id" in conv:
                index[conv["id"]] = _index_entry(conv)
        except (json.JSONDecodeError, OSError):
            # Skip unreadable conversation files rather than failing the
            # entire listing.
            continue
    if index:
        _save_index(index)
    return index


def _save_index(index: Dict[str, Dict[str, Any]]) -> None:
    """Persist the metadata index atomically (write-then-rename)."""
    ensure_data_dir()
    path = get_index_path()
    tmp = _tmp_path(path)
    with open(tmp, "w") as f:
        json.dump(index, f, indent=2)
    os.replace(tmp, path)


def _index_entry(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Build the metadata entry for a conversation."""
    return {
        "id": conv["id"],
        "created_at": conv["created_at"],
        "title": conv.get("title", "New Conversation"),
        "message_count": len(conv.get("messages", [])),
    }


def create_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        New conversation dict
    """
    ensure_data_dir()

    conversation = {
        "id": conversation_id,
        "created_at": _utc_now_iso(),
        "title": "New Conversation",
        "messages": [],
    }

    # Hold the lock across file write + index update so concurrent creates
    # cannot lose each other's index entries.
    with _STORAGE_LOCK:
        _save_conversation_full(conversation)

        index = _load_index()
        index[conversation_id] = _index_entry(conversation)
        _save_index(index)

    return conversation


def _backfill_message_metadata(conv: Dict[str, Any]) -> None:
    """
    Repair assistant messages that were persisted without `metadata`.

    Older code paths (and any pre-existing conversation files) saved
    stage1/stage2/stage3 but not the per-message `metadata` block that holds
    `label_to_model` and `aggregate_rankings`. The frontend needs that block
    to render the Aggregate Rankings section. `aggregate_rankings` is a pure
    function of (stage2_results, label_to_model), and `label_to_model` is
    deterministically derivable from the anonymization scheme used in
    `stage2_collect_rankings` (Response A, B, C, ... map positionally to
    stage1_results), so we can recompute both fields from data that is
    already on disk.

    This runs in-memory only: we mutate the dict that was just read, so the
    caller sees the repaired message and the on-disk file is rewritten on
    the next save. It is safe to call on every read.
    """
    for msg in conv.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        stage2 = msg.get("stage2")
        stage1 = msg.get("stage1")
        if not stage2 or not stage1:
            continue
        metadata = msg.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            msg["metadata"] = metadata
        if not metadata.get("label_to_model"):
            # The same A/B/C positional scheme used in
            # `stage2_collect_rankings` (council.py). Only the labels that
            # actually appear in a parsed_ranking are needed for the
            # aggregate calculation, so we map just the ones stage1 has.
            metadata["label_to_model"] = {
                f"Response {chr(65 + i)}": entry["model"]
                for i, entry in enumerate(stage1)
                if "model" in entry
            }
        if not metadata.get("aggregate_rankings"):
            label_to_model = metadata.get("label_to_model") or {}
            if label_to_model:
                try:
                    metadata["aggregate_rankings"] = calculate_aggregate_rankings(
                        stage2, label_to_model
                    )
                except Exception:
                    # Never let a backfill failure break a read.
                    pass


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    path = get_conversation_path(conversation_id)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        conv = json.load(f)
    # Repair older conversations (or messages saved before the metadata
    # block was persisted) so the Aggregate Rankings section shows up when
    # opening an existing chat.
    _backfill_message_metadata(conv)
    return conv


def _save_conversation_full(conversation: Dict[str, Any]) -> None:
    """
    Write a complete conversation to disk atomically (write-then-rename) so a
    crash mid-write can never leave a truncated, unreadable file. Does not
    update the metadata index.
    """
    ensure_data_dir()
    path = get_conversation_path(conversation["id"])
    tmp = _tmp_path(path)
    with open(tmp, "w") as f:
        json.dump(conversation, f, indent=2)
    os.replace(tmp, path)


def _mutate_conversation(
    conversation_id: str,
    mutator: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    """
    Load a conversation, apply mutator(conv) in-memory, save once, and refresh
    the metadata index. Raises ValueError if the conversation is missing.

    The entire load->mutate->save->index cycle holds the module lock so
    concurrent requests (running in worker threads) cannot lose updates.
    """
    with _STORAGE_LOCK:
        conversation = get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        mutator(conversation)

        _save_conversation_full(conversation)

        index = _load_index()
        index[conversation_id] = _index_entry(conversation)
        _save_index(index)

        return conversation


def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only). Reads from the index file so
    cost is O(conversations), not O(total message history).
    """
    index = _load_index()
    conversations = list(index.values())
    # Sort by creation time, newest first
    conversations.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return conversations


def add_user_message(conversation_id: str, content: str) -> None:
    """
    Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content (capped at MAX_USER_MESSAGE_LENGTH)
    """
    if len(content) > MAX_USER_MESSAGE_LENGTH:
        raise ValueError(
            f"Message content exceeds maximum length of {MAX_USER_MESSAGE_LENGTH} characters"
        )

    def _append(conv: Dict[str, Any]) -> None:
        conv["messages"].append({"role": "user", "content": content})

    _mutate_conversation(conversation_id, _append)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Add an assistant message with all 3 stages to a conversation.

    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses
        stage2: List of model rankings
        stage3: Final synthesized response
        metadata: Per-message metadata block holding `label_to_model` and
            `aggregate_rankings`. Persisted so the Aggregate Rankings
            ("Street Cred") section renders when the conversation is
            reopened. Older callers may pass None; in that case the on-read
            backfill in `_backfill_message_metadata` will recompute it.
    """

    def _append(conv: Dict[str, Any]) -> None:
        conv["messages"].append({
            "role": "assistant",
            "stage1": stage1,
            "stage2": stage2,
            "stage3": stage3,
            "metadata": metadata,
        })

    _mutate_conversation(conversation_id, _append)


def update_conversation_title(conversation_id: str, title: str) -> None:
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """

    def _set_title(conv: Dict[str, Any]) -> None:
        conv["title"] = title

    _mutate_conversation(conversation_id, _set_title)
