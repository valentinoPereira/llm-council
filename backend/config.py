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

# Data directory for conversation storage
DATA_DIR = "data/conversations"
