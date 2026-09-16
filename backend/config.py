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
    "x-ai/grok-4.6",
    "anthropic/claude-opus-5",
]

# Reasoning effort requested from all council models (stages 1–2) and the
# chairman (stage 3). Valid values match the OpenRouter/OpenAI union:
# "minimal" | "low" | "medium" | "high" | "xhigh" | "max" (OpenRouter also
# allows "none"). The title-generation model is excluded — it is a fast
# classifier and thinking would only waste latency/cost.
REASONING_EFFORT = "high"

# Chairman model — synthesizes final response. Runs on NeuralWatt
# (OpenAI-compatible API) with model id "glm-5.3". There is no fallback
# model: if NeuralWatt fails or times out, stage 3 degrades gracefully.
CHAIRMAN_MODEL = "glm-5.3"

# Title generation model — fast and cheap, called through OpenRouter after
# the first user message to produce the conversation title + category.
TITLE_MODEL = "ibm-granite/granite-4.2-8b"

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

# Rankings endpoint -----------------------------------------------------------

# Conversation titles that identify dummy/test runs; their peer-review votes
# are excluded from the model ranking statistics. Full-match only (a
# legitimate "Testing waters" conversation still counts).
RANKINGS_DUMMY_TITLES = frozenset({
    "test", "test es", "test1", "test2", "abcd", "dear", "hey jude",
    "erwrwer", "rwerwerwer", "tell me a story", "new conversation",
})  # lowercase — matched case-insensitively

# Default number of top models returned by the rankings endpoint when the
# caller does not pass an explicit ?top= value.
RANKINGS_TOP_N_DEFAULT = 4

# Bayesian prior weight (in "appearances") used to shrink win rates toward
# the global mean, so newly added models with a lucky small sample cannot
# dominate the leaderboard. Higher = stronger damping of small samples.
# adjusted = (wins + m * prior) / (appearances + m), where prior is the
# global win rate across the filtered pool (empirical Bayes).
RANKINGS_PRIOR_WEIGHT = 10

# Wilson-score lower bound z-value ranking: models are ordered by the
# pessimistic end of the Wilson confidence interval on their win rate, so a
# model needs a decent sample of actual wins before it can lead. Using the
# lower bound (rather than the point estimate) makes small samples rank
# low automatically, without hand-tuned magic numbers.
RANKINGS_WILSON_Z = 1.96  # ~95% one-sided confidence

# Minimum number of council run appearances a model needs before it is
# eligible for the leaderboard. New models sit out until they have enough
# runs for their stats to be meaningful (they also cannot "take the
# spotlight" on a lucky few runs). Models below the quorum are excluded
# from /api/rankings, not merely shrunk.
#
# 15 (not 5): with the Wilson lower bound (z=1.96) as the sort key, small
# samples only produce a *meaningful* ordering once n is large enough that
# the LB separates. Live data showed 1 win in 7 runs out-ranking 2 wins in
# 22 runs by 0.0004 — pure noise. At n>=15 a win rate needs a real win
# sample before its lower bound can lead; a 1-of-7 newcomer stays out.
RANKINGS_MIN_APPEARANCES = 15

# Simulated model mode — for UI testing without spending credits.
# When true, query_model / query_models_parallel return synthetic responses
# instead of calling the OpenRouter API.
USE_SIMULATED_MODELS = (
    os.getenv("USE_SIMULATED_MODELS", "false").lower() in ("true", "1", "yes")
)

# Base per-call delay in simulated mode (seconds). Increase this to mimic
# slower models / long-running stages for loader and heartbeat testing.
SIMULATED_MODEL_DELAY_S = float(os.getenv("SIMULATED_MODEL_DELAY_S", "0.5"))
