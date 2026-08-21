"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "z-ai/glm-5.3",
    "qwen/qwen3.8-2.4t-a95b",
    "deepseek/deepseek-v4-pro-0813",
    "moonshotai/kimi-k3",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "anthropic/claude-opus-5"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
