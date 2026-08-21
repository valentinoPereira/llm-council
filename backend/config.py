"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "@preset/glm-5-2",
    "qwen/qwen3.8-2.4t-a95b",
    "@preset/minimax-m3",
    "x-ai/grok-4.6",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "moonshotai/kimi-k3"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
