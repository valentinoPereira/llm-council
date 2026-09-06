"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# NeuralWatt API key — used only by the Chairman model (stage 3), which is
# called directly via the OpenAI SDK instead of through OpenRouter.
NEURALWATT_API_KEY = os.getenv("NEURALWATT_API_KEY")
NEURALWATT_BASE_URL = os.getenv(
    "NEURALWATT_BASE_URL", "https://api.neuralwatt.com/v1"
)

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "moonshotai/kimi-k3",
    "openai/gpt-5.6-sol",
    "google/gemini-3.7-flash",
    "anthropic/claude-opus-5",
]

# Chairman model — synthesizes final response. Runs on NeuralWatt
# (OpenAI-compatible API) with model id "glm-5.3". There is no fallback
# model: if NeuralWatt fails or times out, stage 3 degrades gracefully.
CHAIRMAN_MODEL = "glm-5.3"

# Hard timeout for the chairman stage (in seconds). A single-provider
# reasoning model can stall despite SDK timeouts, so we enforce an app-level
# wall-clock ceiling on the single chairman attempt.
CHAIRMAN_TIMEOUT_S = 180.0

# Interval at which the SSE stream reports stage progress so the UI can show
# live elapsed time and detect long-running stages.
STAGE_HEARTBEAT_S = 10.0

# Fixed conversation category taxonomy. Title generation asks the model to
# pick exactly one of these for the sidebar. Anything the model returns that
# is not in this list is normalized to UNCATEGORIZED.
CONVERSATION_CATEGORIES = [
    "Science",
    "Mathematics",
    "Philosophy",
    "Technology",
    "Business & Markets",
    "Health",
    "History",
    "Law & Policy",
    "Current Affairs",
    "Arts & Culture",
    "General",
]

# Category stored/displayed when the classifier returns nothing usable.
UNCATEGORIZED = "Unclassified"

# Data directory for conversation storage
DATA_DIR = "data/conversations"

# Simulated model mode — for UI testing without spending credits.
# When true, query_model / query_models_parallel return synthetic responses
# instead of calling the OpenRouter API.
USE_SIMULATED_MODELS = (
    os.getenv("USE_SIMULATED_MODELS", "false").lower() in ("true", "1", "yes")
)

# Base per-call delay in simulated mode (seconds). Increase this to mimic
# slower models / long-running stages for loader and heartbeat testing.
SIMULATED_MODEL_DELAY_S = float(os.getenv("SIMULATED_MODEL_DELAY_S", "0.5"))
