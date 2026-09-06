"""Regression tests for detached council runs.

A run's lifetime is owned by the backend (``jobs.start_run`` spins up an
``asyncio`` task before the HTTP response starts), so it completes in SQLite
regardless of any HTTP connection. These tests exercise that contract
directly: start a run, await ``job.task`` with no SSE connection at all, and
assert the conversation persisted to ``status: complete`` — the primary
proof that a client disconnect can no longer kill a run.

Follows the MockTransport / ``get_client()`` patching pattern from
test_pipeline.py.
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

# Make the project root importable regardless of CWD.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SANDBOX = tempfile.mkdtemp(prefix="llmc-detach-")
os.environ["OPENROUTER_API_KEY"] = "test-key"
# Tests drive real model calls through mocked HTTP, so the .env's simulated
# mode must be overridden here (and a short sim delay used) — otherwise this
# sandbox inherits USE_SIMULATED_MODELS=true / a slow delay and bypasses the
# mocks. Set before backend.config is imported (it reads env variables once).
os.environ["USE_SIMULATED_MODELS"] = "false"
os.environ["SIMULATED_MODEL_DELAY_S"] = "1"

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
# backend.jobs is imported fresh by the main reload above, so there is no
# separate reload needed (and doing so could fork the _JOBS registry).

import httpx
from backend.main import app


def _completion(model: str, content: str) -> httpx.Response:
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


def make_router(stage1_delay: float = 0.0, captured: Dict | None = None):
    """Mock router. Optional stage1 delay to allow attaching mid-run."""
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        data = json.loads(body)
        model = data["model"]
        user_msg = data["messages"][-1]["content"]
        if captured is not None:
            captured.setdefault(model, []).append(user_msg)

        if "very short title" in user_msg.lower():
            return _completion(model, "Mocked Title")

        if "Chairman" in user_msg:
            return _completion(model, "Final synthesis from chairman.")

        if "FINAL RANKING:" in user_msg:
            return _completion(
                model,
                "Response A is good.\n\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n",
            )

        if stage1_delay and model in cfg.COUNCIL_MODELS:
            await asyncio.sleep(stage1_delay)

        return _completion(model, f"Response from {model}.")

    return handler


def make_neuralwatt_router():
    """Mock NeuralWatt router serving the stage-3 chairman synthesis."""
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        data = json.loads(body)
        return httpx.Response(200, json={
            "id": "mock-neuralwatt-completion",
            "object": "chat.completion",
            "created": 0,
            "model": data["model"],
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Final synthesis from chairman."},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    return handler


# Lazily-created shared NeuralWatt mock client (created on first use, closed
# at the end of main). The chairman leg goes through NeuralWatt now, not
# OpenRouter, so every blocking block must also patch neuralwatt.get_client.
_NW_HTTP = None
_NW_CLIENT = None


def _nw_client():
    global _NW_HTTP, _NW_CLIENT
    if _NW_CLIENT is None:
        from openai import AsyncOpenAI
        _NW_HTTP = httpx.AsyncClient(
            transport=httpx.MockTransport(make_neuralwatt_router()), timeout=10.0
        )
        _NW_CLIENT = AsyncOpenAI(
            base_url="https://api.neuralwatt.com/v1",
            api_key="test",
            http_client=_NW_HTTP,
            max_retries=0,
        )
    return _NW_CLIENT


def _install(handler):
    """Patch openrouter.get_client() + neuralwatt.get_client() with mocks."""
    from backend import openrouter as orouter
    from backend import neuralwatt
    orig = orouter.get_client
    mock_http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), timeout=10.0
    )
    from openrouter import OpenRouter
    mock_sdk = OpenRouter(api_key="test-key", async_client=mock_http)
    orouter.get_client = lambda: mock_sdk
    neuralwatt.get_client = _nw_client
    return orig, mock_http


async def _close_nw():
    """Close the shared NeuralWatt mock client (idempotent)."""
    global _NW_HTTP, _NW_CLIENT
    if _NW_HTTP is not None:
        try:
            await _NW_HTTP.aclose()
        finally:
            _NW_HTTP = None
            _NW_CLIENT = None


async def _read_sse(client, url):
    """Read an SSE GET endpoint to completion, return the raw body text."""
    r = await client.get(url)
    assert r.status_code == 200, (r.status_code, r.text)
    body = b""
    async for chunk in r.aiter_bytes():
        body += chunk
    return body.decode()


async def main() -> int:
    # ---- Test 1 (primary): detached run, NO SSE connection --------------
    orig, mock_http = _install(make_router())
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            r = await http.post("/api/conversations", json={})
            cid = r.json()["id"]

            # Start the run directly — never open any SSE connection.
            sid = f"llm-council-{cid}"
            job = await backend.jobs.start_run(cid, "Hello", sid, False)
            await job.task  # wait for the detached task to finish

            # The conversation must now be complete in storage, proving the
            # run's lifetime is fully independent of HTTP connections.
            r = await http.get(f"/api/conversations/{cid}")
            assert r.status_code == 200
            last = r.json()["messages"][-1]
            assert last["role"] == "assistant", last
            assert last["status"] == "complete", last
            assert last["stage1"] and last["stage2"] and last["stage3"], last
            print("OK  detach (primary): run completes with no SSE connection")

            # ---- Test 3: replay a finished run via /run/events ----------
            r = await http.post("/api/conversations", json={})
            cid2 = r.json()["id"]
            job2 = await backend.jobs.start_run(cid2, "Hello", f"llm-council-{cid2}", False)
            await job2.task
            text = await _read_sse(http, f"/api/conversations/{cid2}/run/events")
            for marker in ("stage1_start", "stage1_complete", "stage2_start",
                           "stage2_complete", "stage3_start", "stage3_complete",
                           "complete"):
                assert marker in text, f"replay missing event: {marker}"
            assert "title_complete" not in text  # not a first message
            print("OK  replay: finished run's full event log replays then closes")

            # ---- Test 5: duplicate start -> 409 via /message/stream -----
            r = await http.post("/api/conversations", json={})
            cid3 = r.json()["id"]
            # Seed a still-active run directly (a non-stream httpx post would
            # drain the SSE body to completion, so we can't use POST here).
            orig5, mock_http5 = _install(make_router(stage1_delay=0.4))
            try:
                job5 = await backend.jobs.start_run(cid3, "one", f"llm-council-{cid3}", False)
                await asyncio.sleep(0.05)  # ensure it is in flight, not done
                assert not job5.done
                r2 = await http.post(
                    f"/api/conversations/{cid3}/message/stream",
                    json={"content": "two"},
                )
                assert r2.status_code == 409, (r2.status_code, r2.text)
                print("OK  409: duplicate start for the same conversation")
            finally:
                await mock_http5.aclose()
            # Stop the still-running detached task cleanly.
            backend.jobs.cancel_and_remove(cid3)
            await asyncio.sleep(0.05)
            # Restore a working fast mock for the remaining tests. (Do NOT
            # restore the pre-mock real client here — it has no API key in
            # this sandbox; the outer finally handles the real restore.)
            _, mock_http = _install(make_router())

            # ---- Test 6: orphan sweep -----------------------------------
            await backend.storage.create_pending_assistant_message(cid3)
            fixed = await backend.storage.fail_orphan_pending_messages()
            assert fixed >= 1, "orphan sweep should have fixed at least one row"
            conv = await backend.storage.get_conversation(cid3)
            assert any(
                m["role"] == "assistant" and m["status"] == "error"
                for m in conv["messages"]
            ), "orphan sweep did not produce an error assistant row"
            print(f"OK  orphan sweep flipped {fixed} stale pending rows to error")

            # ---- Test 8: error persistence ------------------------------
            orig_synthesize = backend.jobs.stage3_synthesize_final
            async def _boom(*a, **kw):
                raise RuntimeError("boom")
            backend.jobs.stage3_synthesize_final = _boom
            try:
                r = await http.post("/api/conversations", json={})
                cid4 = r.json()["id"]
                job4 = await backend.jobs.start_run(cid4, "Hi", f"llm-council-{cid4}", False)
                await job4.task
            finally:
                backend.jobs.stage3_synthesize_final = orig_synthesize

            conv = await backend.storage.get_conversation(cid4)
            last = conv["messages"][-1]
            assert last["role"] == "assistant"
            assert last["status"] == "error", last
            assert last["error"] == "boom", last
            text = await _read_sse(http, f"/api/conversations/{cid4}/run/events")
            assert '"type": "error"' in text and '"boom"' in text, text
            print("OK  error persisted as an error assistant row + replay ends with error event")

            # ---- Test 7: delete during run -> clean exit ----------------
            r = await http.post("/api/conversations", json={})
            cid5 = r.json()["id"]
            # Slow stage1 so the run is still in flight when we delete.
            orig2, mock_http2 = _install(make_router(stage1_delay=0.4))
            try:
                job5 = await backend.jobs.start_run(cid5, "Hi", f"llm-council-{cid5}", False)
                # Ensure the job task actually started (first stage in flight).
                await asyncio.sleep(0.05)
                r = await http.delete(f"/api/conversations/{cid5}")
                assert r.status_code == 204, (r.status_code, r.text)
                await asyncio.sleep(0.1)  # let the cancellation settle
                status = (await http.get(f"/api/conversations/{cid5}/run/status")).json()
                assert status == {"active": False, "done": False}, status
                # No lingering job in the registry.
                assert backend.jobs.get_job(cid5) is None
            finally:
                await mock_http2.aclose()
                # Restore get_client to the previous mock.
            print("OK  delete during run exits cleanly, run/status reports inactive")

            # ---- run/status reflects active live run --------------------
            r = await http.post("/api/conversations", json={})
            cid6 = r.json()["id"]
            router_live = make_router(stage1_delay=0.3)
            orig3, mock_http3 = _install(router_live)
            try:
                job6 = await backend.jobs.start_run(cid6, "Hi", f"llm-council-{cid6}", False)
                await asyncio.sleep(0.05)
                st = (await http.get(f"/api/conversations/{cid6}/run/status")).json()
                assert st == {"active": True, "done": False}, st
                await job6.task
                st = (await http.get(f"/api/conversations/{cid6}/run/status")).json()
                assert st == {"active": False, "done": True}, st
                print("OK  run/status reflects active -> done")
            finally:
                await mock_http3.aclose()
    finally:
        orouter = sys.modules.get("backend.openrouter")
        if orouter is not None:
            orouter.get_client = orig
        await mock_http.aclose()
        try:
            await backend.storage.close_db()
        except Exception:
            pass
        shutil.rmtree(SANDBOX, ignore_errors=True)

    # ---- Test 4: attach mid-run ----------------------------------------
    # Separate block because it installs its own slow mock and needs a live
    # second connection while the run is in flight.
    captured: Dict = {}
    orig4, mock_http4 = _install(make_router(stage1_delay=0.6, captured=captured))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            r = await http.post("/api/conversations", json={})
            cid = r.json()["id"]
            job = await backend.jobs.start_run(cid, "Hi", f"llm-council-{cid}", False)
            # Attach a second connection while stage 1 is still in flight.
            await asyncio.sleep(0.1)
            text = await _read_sse(http, f"/api/conversations/{cid}/run/events")
            for marker in ("stage1_start", "stage1_complete", "stage2_start",
                           "stage2_complete", "stage3_start", "stage3_complete",
                           "complete"):
                assert marker in text, f"mid-run attach missing event: {marker}"
            await job.task
            print("OK  attach mid-run: second connection replays + tails to complete")
    finally:
        sys.modules.get("backend.openrouter").get_client = orig4
        await mock_http4.aclose()
        await _close_nw()
        try:
            await backend.storage.close_db()
        except Exception:
            pass
        shutil.rmtree(SANDBOX, ignore_errors=True)

    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        rc = 1
    sys.exit(rc)
