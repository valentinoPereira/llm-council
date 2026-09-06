"""NeuralWatt API access via the OpenAI Python SDK.

NeuralWatt exposes an OpenAI-compatible API (base url
https://api.neuralwatt.com/v1). This module is a thin adapter so the rest of
the backend only deals with plain dicts, with the same response contract as
openrouter.query_model.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from .config import (
    NEURALWATT_API_KEY,
    NEURALWATT_BASE_URL,
    SIMULATED_MODEL_DELAY_S,
    USE_SIMULATED_MODELS,
)

# Module-level shared SDK client. Initialized lazily on first use and closed
# by the FastAPI lifespan handler. The SDK's underlying httpx.AsyncClient
# provides HTTP keep-alive / connection pooling across requests.
_client: Optional[AsyncOpenAI] = None

# Default request timeout (in seconds), mirroring the app-level chairman
# ceiling. The wall-clock ceiling is enforced by asyncio.wait_for in
# council.py; this SDK-level timeout is the in-between bound per request.
_DEFAULT_TIMEOUT_S = 180.0


def get_client() -> AsyncOpenAI:
    """Return the shared SDK client, creating it on first use."""
    global _client
    if _client is None:
        if not NEURALWATT_API_KEY:
            print(
                "[config] NEURALWATT_API_KEY missing - chairman calls will "
                "fail and stage 3 will return a graceful error"
            )
        _client = AsyncOpenAI(
            base_url=NEURALWATT_BASE_URL,
            api_key=NEURALWATT_API_KEY,
            timeout=_DEFAULT_TIMEOUT_S,
            max_retries=1,  # 429/5xx handled by the SDK with backoff
        )
    return _client


async def close_client() -> None:
    """Close the shared SDK client. Safe to call multiple times."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 180.0,
    stage: str = "",
    **_ignored: Any,
) -> Optional[Dict[str, Any]]:
    """
    Query a single NeuralWatt model via the OpenAI SDK.

    Returns a dict with 'content', 'duration_ms', and optional
    'reasoning_details' (populated when the provider returns the OpenAI-style
    'reasoning_content' extension), or None if failed.
    """
    start = time.perf_counter()
    stage_tag = f" stage={stage}" if stage else ""
    print(f"[timing]{stage_tag} model={model} provider=neuralwatt start")

    if USE_SIMULATED_MODELS:
        # Reuse openrouter's simulator so simulated mode keeps covering
        # stage 3 end-to-end without credits.
        from .openrouter import _simulate_query
        result = await _simulate_query(model, messages, stage=stage)
        print(f"[timing]{stage_tag} model={model} elapsed={result['duration_ms']}ms SIMULATED")
        return result

    try:
        completion = await get_client().chat.completions.create(
            model=model,
            messages=messages,
        )
        message = completion.choices[0].message
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        print(f"[timing]{stage_tag} model={model} elapsed={elapsed_ms}ms ok")
        return {
            'content': message.content,
            'reasoning_details': getattr(message, 'reasoning_content', None) or None,
            'duration_ms': elapsed_ms,
        }
    except asyncio.CancelledError:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        print(f"[timing]{stage_tag} model={model} elapsed={elapsed_ms}ms CANCELLED")
        raise
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        print(f"[timing]{stage_tag} model={model} elapsed={elapsed_ms}ms FAILED: {e}")
        return None
