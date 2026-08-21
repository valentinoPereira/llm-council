"""OpenRouter API access via the official `openrouter` Python SDK.

This module is a thin adapter over the SDK so the rest of the backend only
deals with plain dicts. The SDK owns authentication, request validation,
response typing, connection pooling, timeouts, and retries.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from openrouter import OpenRouter
from openrouter.utils.retries import BackoffStrategy, RetryConfig

from .config import OPENROUTER_API_KEY

# Module-level shared SDK client. Initialized lazily on first use and closed
# by the FastAPI lifespan handler. The SDK's underlying httpx.AsyncClient
# provides HTTP keep-alive / connection pooling across requests.
_client: Optional[OpenRouter] = None

# Default request timeout (in seconds), mirroring the previous httpx setup:
# generous overall timeout for slow reasoning models.
_DEFAULT_TIMEOUT_S = 120.0

# Retry policy (SDK-managed):
# - Retry on 429 (rate limited) and 5xx (transient server errors).
# - Retry on connection-level network errors.
# - Exponential backoff starting at 500ms, bounded to ~2.5s total, which
#   approximates the previous "max 2 attempts" policy.
# Note: unlike the previous hand-rolled client, the SDK cannot distinguish
# connect timeouts from read timeouts, so a read timeout may be retried once.
_RETRY_CONFIG = RetryConfig(
    strategy="backoff",
    backoff=BackoffStrategy(
        initial_interval=500,
        max_interval=2000,
        exponent=2.0,
        max_elapsed_time=2500,
    ),
    retry_connection_errors=True,
    status_codes_override=["429", "5XX"],
)


def get_client() -> OpenRouter:
    """Return the shared SDK client, creating it on first use."""
    global _client
    if _client is None:
        _client = OpenRouter(
            api_key=OPENROUTER_API_KEY,
            timeout_ms=int(_DEFAULT_TIMEOUT_S * 1000),
            retry_config=_RETRY_CONFIG,
        )
    return _client


async def close_client() -> None:
    """Close the shared SDK client. Safe to call multiple times."""
    global _client
    if _client is not None:
        async_client = _client.sdk_configuration.async_client
        if async_client is not None:
            await async_client.aclose()
        _client = None


def _serialize_reasoning_details(details: Any) -> Optional[List[Dict[str, Any]]]:
    """Convert the SDK's typed reasoning details into plain JSON-safe dicts."""
    if not details:
        return None
    return [
        item.model_dump() if hasattr(item, "model_dump") else item
        for item in details
    ]


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    stage: str = "",
    session_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via the OpenRouter SDK.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        stage: Human-readable stage label for timing logs (e.g., "stage1")
        session_id: OpenRouter session id for grouping related requests.
            Acts as a sticky routing key (maximizes prompt cache hits by
            routing to the same provider) and groups requests in the
            OpenRouter console. Max 256 characters.

    Returns:
        Response dict with 'content', 'duration_ms', and optional
        'reasoning_details', or None if failed
    """
    start = time.perf_counter()
    try:
        result = await get_client().chat.send_async(
            model=model,
            messages=messages,
            timeout_ms=int(timeout * 1000),
            session_id=session_id,
        )
        message = result.choices[0].message
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

        stage_tag = f" stage={stage}" if stage else ""
        print(f"[timing]{stage_tag} model={model} elapsed={elapsed_ms}ms ok")

        return {
            'content': message.content,
            'reasoning_details': _serialize_reasoning_details(message.reasoning_details),
            'duration_ms': elapsed_ms,
        }

    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        stage_tag = f" stage={stage}" if stage else ""
        print(f"[timing]{stage_tag} model={model} elapsed={elapsed_ms}ms FAILED: {e}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    stage: str = "",
    session_id: Optional[str] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        stage: Human-readable stage label for timing logs
        session_id: OpenRouter session id applied to every request
            (see query_model for details)

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    # Create tasks for all models
    tasks = [
        query_model(model, messages, stage=stage, session_id=session_id)
        for model in models
    ]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return dict(zip(models, responses))
