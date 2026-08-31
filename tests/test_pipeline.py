"""End-to-end test of the council pipeline with mocked OpenRouter."""
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make the project root importable regardless of CWD.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SANDBOX = tempfile.mkdtemp(prefix="llmc-pipe-")
os.environ["OPENROUTER_API_KEY"] = "test-key"

import importlib
import backend.config as cfg
cfg.DATA_DIR = os.path.join(SANDBOX, "conversations")
import backend.storage
importlib.reload(backend.storage)
import backend.openrouter
importlib.reload(backend.openrouter)
import backend.council
importlib.reload(backend.council)
import backend.main
importlib.reload(backend.main)

import httpx
from backend.main import app


# ---- Mock OpenRouter -------------------------------------------------------

# Captured payloads by model for inspection
captured: Dict[str, List[Dict[str, Any]]] = {}


def make_router():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        import json
        data = json.loads(body)
        model = data["model"]
        user_msg = data["messages"][-1]["content"]
        captured.setdefault(model, []).append({
            "user_msg": user_msg,
            "session_id": data.get("session_id"),
        })

        # The official openrouter SDK strictly validates responses, so the
        # mock must include required fields (index, finish_reason,
        # system_fingerprint) even though our code only reads content.
        def completion(content: str) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }],
                "created": 0,
                "id": "mock-completion",
                "model": model,
                "object": "chat.completion",
                "system_fingerprint": "mock-fingerprint",
            })

        if "very short title" in user_msg.lower():
            return completion("Mocked Title")

        # Chairman prompt embeds stage 2 rankings (which contain
        # "FINAL RANKING:") so it must be checked before the ranking branch.
        if "Chairman" in user_msg:
            return completion("Final synthesis from chairman.")

        if "FINAL RANKING:" in user_msg:
            # Stage 2: produce a ranking of A, B, C
            return completion(
                "Response A is good.\n\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n"
            )

        # Stage 1: a sample response per model
        return completion(f"Response from {model}.")

    return handler


def make_failover_router():
    """Mock router where the primary chairman hangs and the failover answers."""
    import asyncio

    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        data = json.loads(body)
        model = data["model"]
        user_msg = data["messages"][-1]["content"]

        captured.setdefault(model, []).append({
            "user_msg": user_msg,
            "session_id": data.get("session_id"),
        })

        def completion(content: str) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }],
                "created": 0,
                "id": "mock-completion",
                "model": model,
                "object": "chat.completion",
                "system_fingerprint": "mock-fingerprint",
            })

        if "very short title" in user_msg.lower():
            return completion("Failover Title")

        if model == cfg.CHAIRMAN_MODEL:
            # Hang past the test's 0.3s chairman timeout.
            await asyncio.sleep(0.7)
            return completion("this should not be reached")

        if model == cfg.CHAIRMAN_FALLBACK_MODEL:
            return completion("Vice-chair synthesis.")

        if "FINAL RANKING:" in user_msg:
            return completion(
                "Response A is good.\n\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n"
            )

        if "Chairman" in user_msg:
            # Any other chairman prompt should be answered (used by total-failure case).
            return completion("Alternate chairman synthesis.")

        return completion(f"Response from {model}.")

    return handler


def make_total_failure_router():
    """Mock router where both primary and fallback chairman hang."""
    import asyncio

    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        data = json.loads(body)
        model = data["model"]
        user_msg = data["messages"][-1]["content"]

        captured.setdefault(model, []).append({
            "user_msg": user_msg,
            "session_id": data.get("session_id"),
        })

        if model in (cfg.CHAIRMAN_MODEL, cfg.CHAIRMAN_FALLBACK_MODEL):
            await asyncio.sleep(0.7)
            return httpx.Response(200, json={
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "should not reach"},
                }],
                "created": 0,
                "id": "mock-completion",
                "model": model,
                "object": "chat.completion",
                "system_fingerprint": "mock-fingerprint",
            })

        if "very short title" in user_msg.lower():
            return httpx.Response(200, json={
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Failure Title"},
                }],
                "created": 0,
                "id": "mock-completion",
                "model": model,
                "object": "chat.completion",
                "system_fingerprint": "mock-fingerprint",
            })

        if "FINAL RANKING:" in user_msg:
            return httpx.Response(200, json={
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Response A is good.\n\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n"},
                }],
                "created": 0,
                "id": "mock-completion",
                "model": model,
                "object": "chat.completion",
                "system_fingerprint": "mock-fingerprint",
            })

        return httpx.Response(200, json={
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": f"Response from {model}."},
            }],
            "created": 0,
            "id": "mock-completion",
            "model": model,
            "object": "chat.completion",
            "system_fingerprint": "mock-fingerprint",
        })

    return handler


async def main() -> int:
    transport = httpx.MockTransport(make_router())

    # Build a dedicated httpx client backed by the mock transport, wrap it in
    # the official openrouter SDK client, and patch get_client() so
    # openrouter.py uses it. Auth is applied by the SDK itself; the injected
    # client only supplies the transport.
    mock_http = httpx.AsyncClient(transport=transport, timeout=10.0)
    from openrouter import OpenRouter
    mock_sdk = OpenRouter(api_key="test-key", async_client=mock_http)
    from backend import openrouter as orouter
    original_get_client = orouter.get_client
    orouter.get_client = lambda: mock_sdk
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            # Create a conversation
            r = await http.post("/api/conversations", json={})
            cid = r.json()["id"]

            # Send a first message -- exercises title-gen + full council
            r = await http.post(
                f"/api/conversations/{cid}/message",
                json={"content": "What is the meaning of life?"},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            print(f"OK  POST /message  status={r.status_code}  stages={list(data.keys())}")

            # Sanity-check stages
            assert len(data["stage1"]) > 0, "stage1 should have at least one response"
            assert len(data["stage2"]) > 0, "stage2 should have at least one ranking"
            assert data["stage3"]["response"] == "Final synthesis from chairman.", data["stage3"]
            assert data["metadata"]["label_to_model"], "label_to_model should be populated"
            assert data["metadata"]["aggregate_rankings"], "aggregate_rankings should be populated"

            # Timing: each stage result should carry a duration_ms
            for entry in data["stage1"]:
                assert "duration_ms" in entry and entry["duration_ms"] >= 0, \
                    f"stage1 entry missing duration_ms: {entry}"
            for entry in data["stage2"]:
                assert "duration_ms" in entry and entry["duration_ms"] >= 0, \
                    f"stage2 entry missing duration_ms: {entry}"
            assert "duration_ms" in data["stage3"] and data["stage3"]["duration_ms"] >= 0, \
                f"stage3 missing duration_ms: {data['stage3']}"
            print(f"OK  duration_ms present in stage1/stage2/stage3 results")

            # The aggregate ranking should mention a model from stage 1
            agg = data["metadata"]["aggregate_rankings"]
            assert any("glm" in e["model"] or "/" in e["model"] for e in agg), agg
            print(f"OK  aggregate_rankings: {[e['model'] for e in agg]}")

            # Title should be set
            r = await http.get(f"/api/conversations/{cid}")
            assert r.json()["title"] == "Mocked Title", r.json()["title"]
            print("OK  title persisted")

            # The persisted assistant message must carry the metadata block
            # (label_to_model + aggregate_rankings) so the Aggregate
            # Rankings section renders when the conversation is reopened.
            # This is the regression test for the "Aggregate Rankings only
            # shows for the first response" bug.
            persisted_msg = r.json()["messages"][-1]
            assert persisted_msg["role"] == "assistant", persisted_msg
            assert "metadata" in persisted_msg, (
                "metadata was not persisted with the assistant message"
            )
            assert persisted_msg["metadata"]["label_to_model"], (
                "label_to_model missing from persisted metadata"
            )
            assert persisted_msg["metadata"]["aggregate_rankings"], (
                "aggregate_rankings missing from persisted metadata"
            )
            print("OK  metadata persisted with assistant message")

            # parsed_ranking was reused (each stage2 entry must have one)
            for entry in data["stage2"]:
                assert "parsed_ranking" in entry, entry
            print("OK  parsed_ranking present in stage2 results")

            # OpenRouter was actually called
            assert "moonshotai/kimi-k3" in captured, "chairman not called"
            assert "google/gemini-2.5-flash" in captured, "title model not called"
            council_models = set(cfg.COUNCIL_MODELS)
            assert council_models.issubset(captured.keys()), \
                f"missing council models: {council_models - set(captured.keys())}"
            print(f"OK  openrouter called for: {sorted(captured.keys())}")

            # Stage 1 + Stage 2 each called once per model
            for m in council_models:
                assert len(captured[m]) == 2, f"{m} called {len(captured[m])} times"
            print("OK  stage 1 + stage 2 each called once per model")

            # Every request (all stages + title gen) carried the conversation's
            # OpenRouter session id: one conversation = one session.
            expected_sid = f"llm-council-{cid}"
            all_entries = [e for entries in captured.values() for e in entries]
            assert all_entries, "no requests were captured"
            bad_sids = {e["session_id"] for e in all_entries} - {expected_sid}
            assert not bad_sids and all(e["session_id"] == expected_sid for e in all_entries), \
                f"unexpected session ids: {bad_sids or {e['session_id'] for e in all_entries}}"
            print(f"OK  all {len(all_entries)} requests used session_id={expected_sid}")

            # 14) Streaming endpoint smoke test
            r = await http.post("/api/conversations", json={})
            cid2 = r.json()["id"]
            r = await http.post(
                f"/api/conversations/{cid2}/message/stream",
                json={"content": "Stream test"},
            )
            assert r.status_code == 200, r.text
            # Read the SSE stream to completion
            body = b""
            async for chunk in r.aiter_bytes():
                body += chunk
            text = body.decode()
            for marker in ("stage1_start", "stage1_complete", "stage2_start",
                           "stage2_complete", "stage3_start", "stage3_complete",
                           "title_complete", "complete"):
                assert marker in text, f"missing SSE event: {marker}"
            print("OK  streaming endpoint emits all 8 expected events")

            # title_complete carries the category taxonomy field
            title_line = [
                line for line in text.splitlines()
                if '"title_complete"' in line and line.startswith("data:")
            ][0]
            title_data = json.loads(title_line.split(":", 1)[1].strip())
            assert title_data["data"]["title"], "title missing from title_complete"
            assert title_data["data"]["category"], "category missing from title_complete"
            print("OK  title_complete carries title + category:", title_data["data"])

            # The streamed conversation got its own session id
            expected_sid2 = f"llm-council-{cid2}"
            all_entries = [e for entries in captured.values() for e in entries]
            sid2_entries = [e for e in all_entries if e["session_id"] == expected_sid2]
            assert sid2_entries, f"streaming requests missing session id {expected_sid2}"
            print(f"OK  streaming requests used session_id={expected_sid2} "
                  f"({len(sid2_entries)} requests)")

            # 15) Chairman timeout -> failover to Vice-Chairman.
            # Speed up the test by shrinking the app-level timeout and the SSE
            # heartbeat interval so we get a progress tick before failover.
            original_timeout = backend.council.CHAIRMAN_TIMEOUT_S
            backend.council.CHAIRMAN_TIMEOUT_S = 0.3
            original_heartbeat = backend.main.STAGE_HEARTBEAT_S
            backend.main.STAGE_HEARTBEAT_S = 0.1
            try:
                transport2 = httpx.MockTransport(make_failover_router())
                mock_http2 = httpx.AsyncClient(transport=transport2, timeout=10.0)
                mock_sdk2 = OpenRouter(api_key="test-key", async_client=mock_http2)
                failover_get_client = orouter.get_client
                orouter.get_client = lambda: mock_sdk2
                try:
                    r = await http.post("/api/conversations", json={})
                    cid3 = r.json()["id"]

                    r = await http.post(
                        f"/api/conversations/{cid3}/message/stream",
                        json={"content": "Failover test"},
                    )
                    assert r.status_code == 200, r.text
                    body = b""
                    async for chunk in r.aiter_bytes():
                        body += chunk
                    text = body.decode()

                    assert "stage3_complete" in text, "stage3_complete event missing"
                    # Find the stage3_complete payload line.
                    stage3_line = [
                        line for line in text.splitlines()
                        if '"stage3_complete"' in line and line.startswith("data:")
                    ][0]
                    stage3_data = json.loads(stage3_line.split(":", 1)[1].strip())
                    assert stage3_data["data"]["model"] == cfg.CHAIRMAN_FALLBACK_MODEL, \
                        f"expected failover to {cfg.CHAIRMAN_FALLBACK_MODEL}, got {stage3_data['data']['model']}"
                    assert stage3_data["data"].get("fallback") is True, "fallback flag missing"
                    assert "stage_progress" in text, "heartbeat missing for stage3"
                    assert "complete" in text, "final complete event missing"
                    print("OK  chairman timeout triggers failover to", cfg.CHAIRMAN_FALLBACK_MODEL)

                    # Persisted assistant message carries the fallback result.
                    conv = await http.get(f"/api/conversations/{cid3}")
                    assert conv.status_code == 200, conv.text
                    assistant = [m for m in conv.json()["messages"] if m["role"] == "assistant"][-1]
                    assert assistant["stage3"]["model"] == cfg.CHAIRMAN_FALLBACK_MODEL
                    assert assistant["stage3"].get("fallback") is True
                    print("OK  fallback result persisted in storage")

                    # 16) Both chairman models fail -> graceful error result.
                    transport3 = httpx.MockTransport(make_total_failure_router())
                    mock_http3 = httpx.AsyncClient(transport=transport3, timeout=10.0)
                    mock_sdk3 = OpenRouter(api_key="test-key", async_client=mock_http3)
                    orouter.get_client = lambda: mock_sdk3
                    try:
                        r = await http.post("/api/conversations", json={})
                        cid4 = r.json()["id"]
                        r = await http.post(
                            f"/api/conversations/{cid4}/message/stream",
                            json={"content": "Total failure test"},
                        )
                        assert r.status_code == 200, r.text
                        body = b""
                        async for chunk in r.aiter_bytes():
                            body += chunk
                        text = body.decode()
                        stage3_line = [
                            line for line in text.splitlines()
                            if '"stage3_complete"' in line and line.startswith("data:")
                        ][0]
                        stage3_data = json.loads(stage3_line.split(":", 1)[1].strip())
                        assert stage3_data["data"].get("error"), "expected error field in stage3 result"
                        assert stage3_data["data"]["response"] is None
                        print("OK  both chairman models failing yields graceful error result")
                    finally:
                        await mock_http3.aclose()
                finally:
                    orouter.get_client = failover_get_client
                    await mock_http2.aclose()
            finally:
                backend.council.CHAIRMAN_TIMEOUT_S = original_timeout
                backend.main.STAGE_HEARTBEAT_S = original_heartbeat

    finally:
        orouter.get_client = original_get_client
        await mock_http.aclose()
        # The httpx ASGI transport in this test does not trigger the
        # lifespan shutdown that normally closes the DB. Close it here
        # before deleting the sandbox to avoid a hung connection thread.
        try:
            await backend.storage.close_db()
        except Exception:
            pass
        shutil.rmtree(SANDBOX, ignore_errors=True)

    # Category normalization: fixed taxonomy mapping + fallback.
    from backend.council import _normalize_category
    assert _normalize_category("science") == "Science"
    assert _normalize_category('"Business & Markets"') == "Business & Markets"
    assert _normalize_category("Philosophy.") == "Philosophy"
    assert _normalize_category("Astrology") == "Unclassified"
    assert _normalize_category(None) == "Unclassified"
    print("OK  _normalize_category maps freeform replies to the taxonomy")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
