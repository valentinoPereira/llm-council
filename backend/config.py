"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "moonshotai/kimi-k3",
    "openai/gpt-5.6-sol",
    "google/gemini-3.7-flash",
    "anthropic/claude-opus-5",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "z-ai/glm-5.3"

# Hard timeout for the chairman stage (in seconds). A single-provider
# reasoning model can stall despite SDK timeouts, so we enforce an app-level
# ceiling that triggers a failover.
CHAIRMAN_TIMEOUT_S = 180.0

# Fallback chairman if the primary times out or fails. Grok has multiple
# providers on OpenRouter, making it a good vice-chairman.
CHAIRMAN_FALLBACK_MODEL = "x-ai/grok-4.6"

# Interval at which the SSE stream reports stage progress so the UI can show
# live elapsed time and detect long-running stages.
STAGE_HEARTBEAT_S = 10.0

# Data directory for conversation storage
DATA_DIR = "data/conversations"
