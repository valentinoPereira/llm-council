"""OpenRouter API client for making LLM requests."""

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL

# Module-level shared client. Initialized lazily on first use and replaced
# (if needed) by the FastAPI lifespan handler. Reusing a single client across
# requests enables HTTP keep-alive / connection pooling, which avoids the
# per-request TCP + TLS handshake cost to openrouter.ai (~10 handshakes per
# user message in the council flow).
_client: Optional[httpx.AsyncClient] = None

# Default pool sizes are generous enough to run the 4-model stage 1/2 fan-out
# in parallel plus the chairman and title-generation requests.
_DEFAULT_LIMITS = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10,
    keepalive_expiry=30.0,
)


def get_client() -> httpx.AsyncClient:
    """Return the shared AsyncClient, creating it on first use."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=_DEFAULT_LIMITS,
        )
    return _client


async def close_client() -> None:
    """Close the shared AsyncClient. Safe to call multiple times."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _build_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }


async def _post_with_retry(
    payload: Dict[str, Any],
    *,
    timeout: float,
    max_attempts: int = 2,
) -> httpx.Response:
    """
    POST with a single retry on transient failures. Each attempt has its own
    timeout.

    Retry policy:
    - Connection failures (network errors, connect timeouts): safe to retry,
      the request never reached the server.
    - 429 (rate limited) and 5xx: transient server-side, safe to retry.
    - Read/write timeouts are NOT retried: the server may already have
      processed the request, and a retry would pay for a duplicate
      generation.
    """
    client = get_client()
    for attempt in range(max_attempts):
        try:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=_build_headers(),
                json=payload,
                timeout=timeout,
            )
        except (httpx.NetworkError, httpx.ConnectTimeout):
            if attempt + 1 >= max_attempts:
                raise
            await asyncio.sleep(0.5 * (2 ** attempt))
            continue

        # Retry on rate limiting and transient server errors
        if (response.status_code == 429 or response.status_code >= 500) and attempt + 1 < max_attempts:
            await asyncio.sleep(0.5 * (2 ** attempt))
            continue
        return response

    # Unreachable in practice: the loop above either returns a response or
    # raises. This satisfies type-checkers that don't know the loop must exit
    # via one of those two paths.
    raise RuntimeError("_post_with_retry exited without returning or raising")


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        response = await _post_with_retry(payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        message = data['choices'][0]['message']

        return {
            'content': message.get('content'),
            'reasoning_details': message.get('reasoning_details'),
        }

    except Exception as e:
        print(f"Error querying model {model}: {e}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    # Create tasks for all models
    tasks = [query_model(model, messages) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return dict(zip(models, responses))
