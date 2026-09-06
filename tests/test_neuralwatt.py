"""Unit tests for the NeuralWatt chairman adapter (backend/neuralwatt.py) and
the stage-3 chairman dispatch (council.stage3_synthesize_final).

The chairman is NeuralWatt-only with NO fallback model. These tests prove:
- the happy path returns the NeuralWatt synthesis,
- provider failures / bad-auth / timeouts degrade to a graceful error result
  without ever calling OpenRouter (the removed failover really is gone),
- the request body targets glm-5.3 with the chairman prompt and no
  OpenRouter session field,
- simulated mode short-circuits to the synthetic synthesis.

Follows the MockTransport pattern: inject an httpx client into the OpenAI SDK
and patch neuralwatt.get_client(). The SDK applies auth itself; the injected
client only supplies the transport.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force real (non-simulated) mode before backend.config is imported, so the
# adapter's USE_SIMULATED_MODELS flag is False and every path goes through
# the mocked HTTP transport.
os.environ["USE_SIMULATED_MODELS"] = "false"
os.environ["SIMULATED_MODEL_DELAY_S"] = "0.01"

import httpx
from openai import AsyncOpenAI

import backend.config as cfg
from backend import council, neuralwatt


# ---- Shared fixtures ------------------------------------------------------

def _stage1() -> List[Dict[str, Any]]:
    return [{"model": "openai/gpt-5.6-sol", "response": "Council response.", "duration_ms": 100}]


def _stage2() -> List[Dict[str, Any]]:
    return [{
        "model": "openai/gpt-5.6-sol",
        "ranking": "Response A is best.\n\nFINAL RANKING:\n1. Response A",
        "parsed_ranking": ["Response A"],
        "duration_ms": 100,
    }]


def _openai_completion(model: str, content: str) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "mock-neuralwatt-completion",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })


def openai_client_with(transport, *, max_retries: int = 0) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://api.neuralwatt.com/v1",
        api_key="test",
        http_client=httpx.AsyncClient(transport=transport, timeout=10.0),
        max_retries=max_retries,
    )


class CapturingTransport:
    """MockTransport handler that records every request body sent."""

    def __init__(self, status: int = 200, content: str = "Synthesis."):
        self.requests: List[Dict[str, Any]] = []
        self.status = status
        self.content = content

    async def handler(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        data = json.loads(body)
        self.requests.append(data)
        if self.status != 200:
            return httpx.Response(self.status, json={
                "error": {"message": "boom", "type": "server_error", "code": "error"},
            })
        return _openai_completion(data["model"], self.content)


async def _run_failure_case(status: int) -> Dict[str, Any]:
    """Run stage 3 against a transport that returns the given status."""
    cap = CapturingTransport(status=status)
    client = openai_client_with(httpx.MockTransport(cap.handler))
    orig = neuralwatt.get_client
    neuralwatt.get_client = lambda: client

    # Spy on the OpenRouter adapter: it must never be called for stage 3.
    from backend import openrouter as orouter
    calls: List[str] = []
    orig_query = orouter.query_model
    async def fake_query(*a, **kw):
        calls.append(kw.get("stage", ""))
        return None
    orouter.query_model = fake_query

    try:
        result = await council.stage3_synthesize_final(
            "What is life?", _stage1(), _stage2(), session_id="llm-council-x"
        )
    finally:
        neuralwatt.get_client = orig
        orouter.query_model = orig_query
        await client.close()

    assert calls == [], f"OpenRouter query_model called for stage3: {calls}"
    return result


async def _test_happy_path() -> None:
    cap = CapturingTransport(content="Final synthesis from NeuralWatt.")
    client = openai_client_with(httpx.MockTransport(cap.handler))
    orig = neuralwatt.get_client
    neuralwatt.get_client = lambda: client
    try:
        result = await council.stage3_synthesize_final(
            "What is life?", _stage1(), _stage2(), session_id="llm-council-x"
        )
    finally:
        neuralwatt.get_client = orig
        await client.close()

    assert result["model"] == cfg.CHAIRMAN_MODEL == "glm-5.3", result
    assert result["response"] == "Final synthesis from NeuralWatt.", result
    assert "duration_ms" in result and result["duration_ms"] >= 0, result
    assert "fallback" not in result, result
    # Exactly one request, shaped like NeuralWatt (no session routing field).
    assert len(cap.requests) == 1
    body = cap.requests[0]
    assert body["model"] == "glm-5.3"
    assert "Chairman" in body["messages"][-1]["content"]
    assert "session" not in body, body
    print("OK  happy path: neuralwatt synthesis, glm-5.3, no session field")


async def _test_provider_failure_graceful() -> None:
    result = await _run_failure_case(500)
    assert result["response"] is None, result
    assert result["error"], result
    assert result["duration_ms"] >= 0, result
    assert "fallback" not in result, result
    print("OK  provider 500 -> graceful error, OpenRouter never called")


async def _test_auth_missing_graceful() -> None:
    result = await _run_failure_case(401)
    assert result["response"] is None, result
    assert result["error"], result
    print("OK  auth 401 -> graceful error, OpenRouter never called")


async def _test_timeout_graceful() -> None:
    orig_timeout = council.CHAIRMAN_TIMEOUT_S
    orig_query = neuralwatt.query_model

    async def slow_query(*a, **kw):
        await asyncio.sleep(0.5)
        return {"content": "too late", "duration_ms": 500}

    council.CHAIRMAN_TIMEOUT_S = 0.1
    neuralwatt.query_model = slow_query
    try:
        result = await council.stage3_synthesize_final(
            "What is life?", _stage1(), _stage2(), session_id="llm-council-x"
        )
    finally:
        council.CHAIRMAN_TIMEOUT_S = orig_timeout
        neuralwatt.query_model = orig_query

    assert result["response"] is None, result
    assert result["error"], result
    print("OK  timeout -> graceful error")


async def _test_request_shape_no_session() -> None:
    """Assert the exact JSON body sent to NeuralWatt: model + prompt, no
    OpenRouter session/routing field, no temperature/max_tokens overrides."""
    cap = CapturingTransport(content="ok")
    client = openai_client_with(httpx.MockTransport(cap.handler))
    orig = neuralwatt.get_client
    neuralwatt.get_client = lambda: client
    try:
        await council.stage3_synthesize_final(
            "What is life?", _stage1(), _stage2(), session_id="llm-council-x"
        )
    finally:
        neuralwatt.get_client = orig
        await client.close()

    assert len(cap.requests) == 1
    body = cap.requests[0]
    assert body["model"] == "glm-5.3", body
    messages = body["messages"]
    assert isinstance(messages, list) and len(messages) == 1, messages
    assert messages[0]["role"] == "user"
    assert "Chairman" in messages[0]["content"]
    # No OpenRouter session id leaks onto the NeuralWatt leg.
    assert "session_id" not in body and "session" not in body, body
    # Defaults: caller didn't force temperature / max_tokens.
    assert "temperature" not in body, body
    assert "max_tokens" not in body, body
    print("OK  request shape: glm-5.3, chairman prompt, no session/temperature/max_tokens")


async def _test_simulated_mode() -> None:
    # Simulated mode must short-circuit to the synthetic synthesis without
    # ever touching get_client / HTTP.
    neuralwatt.USE_SIMULATED_MODELS = True
    created = False
    orig = neuralwatt.get_client
    def boom_client():
        nonlocal created
        created = True
        raise AssertionError("get_client called in simulated mode")
    neuralwatt.get_client = boom_client
    try:
        result = await council.stage3_synthesize_final(
            "Sim question", _stage1(), _stage2(), session_id="llm-council-x"
        )
    finally:
        neuralwatt.USE_SIMULATED_MODELS = False
        neuralwatt.get_client = orig

    assert created is False, "get_client called in simulated mode"
    assert result["response"] and "simulated chairman synthesis" in result["response"].lower(), result
    assert result["model"] == "glm-5.3", result
    assert "duration_ms" in result, result
    assert "fallback" not in result, result
    print("OK  simulated mode returns synthetic synthesis without HTTP")


async def main() -> int:
    await _test_happy_path()
    await _test_provider_failure_graceful()
    await _test_auth_missing_graceful()
    await _test_timeout_graceful()
    await _test_request_shape_no_session()
    await _test_simulated_mode()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
