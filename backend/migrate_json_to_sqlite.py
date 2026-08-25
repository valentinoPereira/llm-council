"""One-time migration: import legacy JSON conversations into SQLite.

The previous storage backend wrote one JSON file per conversation under
DATA_DIR (plus an `index.json`). This script reads those files and loads
them into the new SQLite database (`council.db`), recomputing the
`metadata` block (label_to_model + aggregate_rankings) for any assistant
message that was persisted before that block existed.

Idempotent: conversations already present in the DB (matched by id) are
skipped, so this is safe to run repeatedly.

Usage (from the project root):

    python -m backend.migrate_json_to_sqlite
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from . import storage
from .config import DATA_DIR
from .council import calculate_aggregate_rankings


def _backfill_metadata(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Recompute label_to_model + aggregate_rankings for an assistant message
    that was saved without a `metadata` block.

    Mirrors the on-read backfill the old JSON storage performed:
    `label_to_model` follows the positional A/B/C scheme used in
    `stage2_collect_rankings` (Response A = stage1[0], etc.), and
    `aggregate_rankings` is a pure function of (stage2, label_to_model).
    """
    stage1 = msg.get("stage1")
    stage2 = msg.get("stage2")
    if not stage1 or not stage2:
        return msg.get("metadata")

    metadata = msg.get("metadata") or {}
    if not metadata.get("label_to_model"):
        metadata["label_to_model"] = {
            f"Response {chr(65 + i)}": entry["model"]
            for i, entry in enumerate(stage1)
            if isinstance(entry, dict) and "model" in entry
        }
    if not metadata.get("aggregate_rankings"):
        label_to_model = metadata.get("label_to_model") or {}
        if label_to_model:
            try:
                metadata["aggregate_rankings"] = calculate_aggregate_rankings(
                    stage2, label_to_model
                )
            except Exception:
                # Never let a backfill failure block migration.
                pass
    return metadata or None


def _dumps(value: Any) -> Optional[str]:
    return json.dumps(value) if value is not None else None


async def migrate() -> int:
    # Reuse an already-open connection (e.g. when invoked in-process during
    # a test) so we don't clobber the app's `_db` global. Only manage the
    # lifecycle ourselves when no connection is open yet.
    opened = False
    if storage._db is None:
        await storage.init_db()
        opened = True
    try:
        db = storage._db_conn()

        data_dir = Path(DATA_DIR)
        if not data_dir.exists():
            print(f"No data directory at {data_dir}; nothing to migrate.")
            return 0

        # Skip index.json and any non-conversation files.
        files = sorted(p for p in data_dir.glob("*.json") if p.name != "index.json")

        imported = 0
        skipped = 0
        errors = 0

        for path in files:
            try:
                conv = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  skip unreadable {path.name}: {e}")
                errors += 1
                continue
            if not isinstance(conv, dict) or "id" not in conv:
                print(f"  skip non-conversation file {path.name}")
                errors += 1
                continue

            cid = conv["id"]

            # Idempotent: don't re-import conversations the DB already has.
            existing = await storage.get_conversation(cid)
            if existing is not None:
                skipped += 1
                continue

            created_at = conv.get("created_at") or storage._utc_now_iso()
            title = conv.get("title", "New Conversation")
            await db.execute(
                "INSERT OR IGNORE INTO conversations (id, created_at, title) "
                "VALUES (?, ?, ?)",
                (cid, created_at, title),
            )

            for msg in conv.get("messages", []):
                role = msg.get("role")
                if role == "user":
                    await db.execute(
                        "INSERT INTO messages "
                        "(conversation_id, role, content, created_at) "
                        "VALUES (?, 'user', ?, ?)",
                        (cid, msg.get("content", ""), created_at),
                    )
                elif role == "assistant":
                    metadata = _backfill_metadata(msg)
                    await db.execute(
                        "INSERT INTO messages "
                        "(conversation_id, role, content, stage1, stage2, "
                        " stage3, metadata, created_at) "
                        "VALUES (?, 'assistant', NULL, ?, ?, ?, ?, ?)",
                        (
                            cid,
                            _dumps(msg.get("stage1")),
                            _dumps(msg.get("stage2")),
                            _dumps(msg.get("stage3")),
                            _dumps(metadata),
                            created_at,
                        ),
                    )
            await db.commit()
            imported += 1
            print(f"  imported {cid}  ({len(conv.get('messages', []))} messages)")
    finally:
        if opened:
            await storage.close_db()

    print(
        f"\nMigration complete: {imported} imported, "
        f"{skipped} skipped, {errors} errors."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(migrate()))
