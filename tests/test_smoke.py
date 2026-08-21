"""Smoke test for the LLM Council backend (no LLM calls)."""
import asyncio
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

        # 7) index.json should exist and be consistent
        index_path = Path(cfg.DATA_DIR) / "index.json"
        assert index_path.exists(), index_path
        import json
        idx = json.loads(index_path.read_text())
        assert cid in idx
        assert idx[cid]["message_count"] == 0
        print("OK  index.json structure valid")

        # 8) Storage round-trip via _mutate_conversation
        backend.storage.add_user_message(cid, "hello world")
        loaded = backend.storage.get_conversation(cid)
        assert loaded["messages"][-1] == {"role": "user", "content": "hello world"}
        # And the index got updated
        idx = json.loads(index_path.read_text())
        assert idx[cid]["message_count"] == 1
        print("OK  add_user_message + index update")

        # 9) add_assistant_message round trip
        backend.storage.add_assistant_message(
            cid,
            stage1=[{"model": "x", "response": "y"}],
            stage2=[{"model": "x", "ranking": "z", "parsed_ranking": ["Response A"]}],
            stage3={"model": "chair", "response": "final"},
        )
        loaded = backend.storage.get_conversation(cid)
        assert len(loaded["messages"]) == 2
        assert loaded["messages"][-1]["stage3"]["response"] == "final"
        idx = json.loads(index_path.read_text())
        assert idx[cid]["message_count"] == 2
        print("OK  add_assistant_message + index update")

        # 10) update_conversation_title
        backend.storage.update_conversation_title(cid, "New Title")
        loaded = backend.storage.get_conversation(cid)
        assert loaded["title"] == "New Title"
        idx = json.loads(index_path.read_text())
        assert idx[cid]["title"] == "New Title"
        print("OK  update_conversation_title + index update")

        # 11) MAX_USER_MESSAGE_LENGTH guard
        try:
            backend.storage.add_user_message(cid, "x" * (backend.storage.MAX_USER_MESSAGE_LENGTH + 1))
        except ValueError as e:
            print(f"OK  add_user_message length cap ({e})")
        else:
            print("FAIL  add_user_message should have raised ValueError")
            return 1

        # 12) Shared openrouter SDK client is initialized via lifespan
        from backend.openrouter import get_client
        c1 = get_client()
        c2 = get_client()
        assert c1 is c2, "shared SDK client should be a singleton"
        print("OK  shared openrouter SDK client is a singleton")

        # 13) Routes list
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        for expected in [
            "/", "/api/conversations",
            "/api/conversations/{conversation_id}",
            "/api/conversations/{conversation_id}/message",
            "/api/conversations/{conversation_id}/message/stream",
        ]:
            assert expected in routes, f"missing route: {expected}"
        print(f"OK  routes registered: {len(routes)} total")

        # 14) Migration: a conversation file with no index entry must still
        # appear in the listing (index is rebuilt lazily from disk).
        legacy_id = str(uuid.uuid4())
        legacy_path = Path(cfg.DATA_DIR) / f"{legacy_id}.json"
        legacy_path.write_text(json.dumps({
            "id": legacy_id,
            "created_at": "2026-01-01T00:00:00",
            "title": "Legacy Conversation",
            "messages": [{"role": "user", "content": "hi"}],
        }))
        # Delete the index so the next read must rebuild from disk.
        index_path.unlink()
        r = await client.get("/api/conversations")
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert legacy_id in ids, f"legacy conversation missing from listing: {ids}"
        assert cid in ids, "indexed conversation missing after rebuild"
        legacy_meta = next(c for c in r.json() if c["id"] == legacy_id)
        assert legacy_meta["title"] == "Legacy Conversation"
        assert legacy_meta["message_count"] == 1
        # Rebuild should have re-created the index file.
        assert index_path.exists()
        print("OK  index lazy-rebuild migrates pre-existing conversations")

        # 15) Corrupt index.json is rebuilt rather than emptying the listing.
        index_path.write_text("{ not valid json !!!")
        r = await client.get("/api/conversations")
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert cid in ids and legacy_id in ids, f"corrupt index not rebuilt: {ids}"
        print("OK  corrupt index.json triggers rebuild")

        # 16) Oversized message returns HTTP 400, not 500.
        r = await client.post(
            f"/api/conversations/{cid}/message",
            json={"content": "x" * (backend.storage.MAX_USER_MESSAGE_LENGTH + 1)},
        )
        assert r.status_code == 400, (r.status_code, r.text)
        print("OK  oversized message -> HTTP 400")

        # 17) Streaming endpoint pre-flights oversized messages the same way.
        r = await client.post(
            f"/api/conversations/{cid}/message/stream",
            json={"content": "x" * (backend.storage.MAX_USER_MESSAGE_LENGTH + 1)},
        )
        assert r.status_code == 400, (r.status_code, r.text)
        print("OK  oversized message (streaming) -> HTTP 400")

    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)
    sys.exit(rc)
