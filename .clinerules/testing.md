---
paths:
  - "tests/**"
---

# Testing Guidelines

## Mock injection pattern

- Tests inject a mock via `OpenRouter(async_client=httpx.AsyncClient(transport=httpx.MockTransport(...)))` and patch `openrouter.get_client()` — the SDK applies auth itself; the injected client only supplies the transport. Follow the pattern in `tests/test_pipeline.py` for new model-call tests.