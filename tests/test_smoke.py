"""Smoke test for the LLM Council backend (no LLM calls).

Exercises the aiosqlite-backed storage layer through both the HTTP API and
direct storage calls. The previous version tested the JSON-file storage
internals (index.json, lazy rebuild, on-read backfill); those concepts no
longer exist. The migration-specific behaviour (importing legacy JSON
files, backfilling missing metadata) is now covered by an explicit
`migrate_json_to_sqlite` test.
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

# Make the project root importable regardless of CWD.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Use a sandbox data dir so we don't touch the real one.
SANDBOX = tempfile.mkdtemp(prefix="llmc-test-")
os.environ["OPENROUTER_API_KEY"] = "test-key-not-used"

# Point DATA_DIR at our sandbox BEFORE importing the backend.
import importlib
import backend.config as cfg
cfg.DATA_DIR = os.path.join(SANDBOX, "conversations")
# Reset modules that captured the old DATA_DIR
import backend.storage
importlib.reload(backend.storage)
import backend.council
importlib.reload(backend.council)
import backend.migrate_json_to_sqlite
importlib.reload(backend.migrate_json_to_sqlite)
import backend.main
importlib.reload(backend.main)
from backend.main import app

import httpx


async def main() -> int:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1) Health
        r = await client.get("/")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ok"
        print("OK  GET /")

        # 2) List (empty)
        r = await client.get("/api/conversations")
        assert r.status_code == 200, r.text
        assert r.json() == []
        print("OK  GET /api/conversations (empty)")

        # 3) Create conversation
        r = await client.post("/api/conversations", json={})
        assert r.status_code == 200, r.text
        conv = r.json()
        cid = conv["id"]
        assert conv["messages"] == []
        assert conv["title"] == "New Conversation"
        print(f"OK  POST /api/conversations  id={cid}")

        # 4) List (one)
        r = await client.get("/api/conversations")
        assert r.status_code == 200, r.text
        items = r.json()
        assert len(items) == 1
        assert items[0]["id"] == cid
        assert items[0]["message_count"] == 0
        print("OK  GET /api/conversations (1 item)")

        # 5) Get conversation
        r = await client.get(f"/api/conversations/{cid}")
        assert r.status_code == 200
        assert r.json()["id"] == cid
        print("OK  GET /api/conversations/{id}")

        # 6) Get nonexistent
        r = await client.get(f"/api/conversations/{uuid.uuid4()}")
        assert r.status_code == 404
        print("OK  GET /api/conversations/<missing> -> 404")

        # 7) SQLite database file exists under DATA_DIR
        db_path = Path(cfg.DATA_DIR) / "council.db"
        assert db_path.exists(), db_path
        print(f"OK  council.db created at {db_path.name}")

        # 8) Storage round-trip via direct async calls
        await backend.storage.add_user_message(cid, "hello world")
        loaded = await backend.storage.get_conversation(cid)
        assert loaded["messages"][-1] == {"role": "user", "content": "hello world"}
        # The list endpoint reflects the new message count via COUNT(*).
        r = await client.get("/api/conversations")
        meta = next(c for c in r.json() if c["id"] == cid)
        assert meta["message_count"] == 1, meta
        print("OK  add_user_message + message_count reflects it")

        # 9) add_assistant_message round trip (with metadata persistence)
        await backend.storage.add_assistant_message(
            cid,
            stage1=[{"model": "x", "response": "y"}],
            stage2=[{"model": "x", "ranking": "z", "parsed_ranking": ["Response A"]}],
            stage3={"model": "chair", "response": "final"},
            metadata={"label_to_model": {"Response A": "x"}, "aggregate_rankings": [{"model": "x", "average_rank": 1.0, "rankings_count": 1}]},
        )
        loaded = await backend.storage.get_conversation(cid)
        assert len(loaded["messages"]) == 2
        assert loaded["messages"][-1]["stage3"]["response"] == "final"
        # Metadata must be persisted so the Aggregate Rankings section shows
        # up when the conversation is reopened. Regression test for the
        # "Aggregate Rankings only shows for the first response" bug.
        persisted_metadata = loaded["messages"][-1].get("metadata")
        assert persisted_metadata is not None, "metadata was not persisted"
        assert persisted_metadata["label_to_model"] == {"Response A": "x"}
        assert persisted_metadata["aggregate_rankings"] == [
            {"model": "x", "average_rank": 1.0, "rankings_count": 1}
        ]
        meta = next(c for c in (await _list(client)) if c["id"] == cid)
        assert meta["message_count"] == 2, meta
        print("OK  add_assistant_message + metadata persistence")

        # 10) update_conversation_title
        await backend.storage.update_conversation_title(cid, "New Title")
        loaded = await backend.storage.get_conversation(cid)
        assert loaded["title"] == "New Title"
        meta = next(c for c in (await _list(client)) if c["id"] == cid)
        assert meta["title"] == "New Title"
        print("OK  update_conversation_title")

        # 11) update_conversation_title on a missing conversation raises
        try:
            await backend.storage.update_conversation_title(
                str(uuid.uuid4()), "ghost"
            )
        except ValueError:
            print("OK  update_conversation_title on missing conv -> ValueError")
        else:
            print("FAIL  update_conversation_title should have raised ValueError")
            return 1

        # 12) MAX_USER_MESSAGE_LENGTH guard
        try:
            await backend.storage.add_user_message(
                cid, "x" * (backend.storage.MAX_USER_MESSAGE_LENGTH + 1)
            )
        except ValueError as e:
            print(f"OK  add_user_message length cap ({e})")
        else:
            print("FAIL  add_user_message should have raised ValueError")
            return 1

        # 13) Shared openrouter SDK client is initialized via lifespan
        from backend.openrouter import get_client
        c1 = get_client()
        c2 = get_client()
        assert c1 is c2, "shared SDK client should be a singleton"
        print("OK  shared openrouter SDK client is a singleton")

        # 14) Routes list
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        for expected in [
            "/", "/api/conversations",
            "/api/conversations/{conversation_id}",
            "/api/conversations/{conversation_id}/message",
            "/api/conversations/{conversation_id}/message/stream",
        ]:
            assert expected in routes, f"missing route: {expected}"
        print(f"OK  routes registered: {len(routes)} total")

        # 15) Oversized message returns HTTP 400, not 500.
        r = await client.post(
            f"/api/conversations/{cid}/message",
            json={"content": "x" * (backend.storage.MAX_USER_MESSAGE_LENGTH + 1)},
        )
        assert r.status_code == 400, (r.status_code, r.text)
        print("OK  oversized message -> HTTP 400")

        # 16) Streaming endpoint pre-flights oversized messages the same way.
        r = await client.post(
            f"/api/conversations/{cid}/message/stream",
            json={"content": "x" * (backend.storage.MAX_USER_MESSAGE_LENGTH + 1)},
        )
        assert r.status_code == 400, (r.status_code, r.text)
        print("OK  oversized message (streaming) -> HTTP 400")

        # 17) Migration: legacy JSON conversation files on disk are imported
        # into SQLite, and assistant messages lacking a `metadata` block get
        # their label_to_model + aggregate_rankings backfilled during import.
        legacy_id = str(uuid.uuid4())
        legacy_path = Path(cfg.DATA_DIR) / f"{legacy_id}.json"
        legacy_path.write_text(json.dumps({
            "id": legacy_id,
            "created_at": "2026-01-01T00:00:00",
            "title": "Legacy Conversation",
            "messages": [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "stage1": [{"model": "google/gemini-2.5-flash", "response": "r1"}],
                    "stage2": [
                        {
                            "model": "google/gemini-2.5-flash",
                            "ranking": "FINAL RANKING:\n1. Response A\n",
                            "parsed_ranking": ["Response A"],
                        }
                    ],
                    "stage3": {"model": "chair", "response": "final"},
                    # NOTE: no `metadata` key, simulating a pre-fix save.
                },
            ],
        }))
        imported = await backend.migrate_json_to_sqlite.migrate()
        assert imported == 0, "migrate() should return 0 on success"

        r = await client.get("/api/conversations")
        ids = [c["id"] for c in r.json()]
        assert legacy_id in ids, f"legacy conversation missing after migration: {ids}"
        assert cid in ids, "pre-existing conversation missing after migration"
        legacy_meta = next(c for c in r.json() if c["id"] == legacy_id)
        assert legacy_meta["title"] == "Legacy Conversation"
        assert legacy_meta["message_count"] == 2, legacy_meta
        print("OK  migration imports legacy JSON conversation")

        # The legacy assistant message's metadata was backfilled on import.
        r = await client.get(f"/api/conversations/{legacy_id}")
        assert r.status_code == 200, r.text
        legacy_msg = r.json()["messages"][-1]
        assert legacy_msg["metadata"]["label_to_model"] == {
            "Response A": "google/gemini-2.5-flash"
        }
        assert legacy_msg["metadata"]["aggregate_rankings"], (
            "aggregate_rankings was not backfilled during migration"
        )
        print("OK  migration backfills aggregate_rankings for old messages")

        # 18) Migration is idempotent: re-running skips already-imported convs.
        imported2 = await backend.migrate_json_to_sqlite.migrate()
        assert imported2 == 0
        r = await client.get("/api/conversations")
        legacy_count = sum(1 for c in r.json() if c["id"] == legacy_id)
        assert legacy_count == 1, "legacy conversation imported twice"
        print("OK  migration is idempotent")

        # 19) Corrupt/unreadable JSON files are skipped, not fatal.
        bad_path = Path(cfg.DATA_DIR) / f"{uuid.uuid4()}.json"
        bad_path.write_text("{ not valid json !!!")
        imported3 = await backend.migrate_json_to_sqlite.migrate()
        assert imported3 == 0
        r = await client.get("/api/conversations")
        assert legacy_id in [c["id"] for c in r.json()], "good conv lost after bad file"
        print("OK  corrupt JSON file skipped during migration")

    return 0


async def _list(client: httpx.AsyncClient):
    r = await client.get("/api/conversations")
    assert r.status_code == 200, r.text
    return r.json()


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    finally:
        # The httpx ASGI transport in this test does not trigger the
        # lifespan shutdown that normally closes the DB. Close it here
        # before deleting the sandbox to avoid a hung connection thread.
        try:
            asyncio.run(backend.storage.close_db())
        except Exception:
            pass
        shutil.rmtree(SANDBOX, ignore_errors=True)
    sys.exit(rc)
