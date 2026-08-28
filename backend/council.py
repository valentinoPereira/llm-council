"""3-stage LLM Council orchestration."""

import asyncio
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from .config import (
    CHAIRMAN_FALLBACK_MODEL,
    CHAIRMAN_MODEL,
    CHAIRMAN_TIMEOUT_S,
    COUNCIL_MODELS,
)
from .openrouter import query_model, query_models_parallel


async def stage1_collect_responses(user_query: str, session_id: str = "") -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question
        session_id: OpenRouter session id (conversation grouping)

    Returns:
        List of dicts with 'model', 'response', and 'duration_ms' keys
    """
    messages = [{"role": "user", "content": user_query}]

    # Query all models in parallel
    start = time.perf_counter()
    responses = await query_models_parallel(
        COUNCIL_MODELS, messages, stage="stage1", session_id=session_id
    )

    # Format results
    stage1_results = []
    for model, response in responses.items():
        if response is not None:  # Only include successful responses
            stage1_results.append({
                "model": model,
                "response": response.get('content', ''),
                "duration_ms": response.get('duration_ms'),
            })

    elapsed = time.perf_counter() - start
    if stage1_results:
        slowest = max(
            (r for r in stage1_results if r['duration_ms'] is not None),
            key=lambda r: r['duration_ms'],
            default=None,
        )
        slowest_tag = f" slowest={slowest['model']}" if slowest else ""
        print(f"[timing] stage=stage1 total={elapsed:.1f}s{slowest_tag}")

    return stage1_results


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    session_id: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1
        session_id: OpenRouter session id (conversation grouping)

    Returns:
        Tuple of (rankings list, label_to_model mapping)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Get rankings from all council models in parallel
    start = time.perf_counter()
    responses = await query_models_parallel(
        COUNCIL_MODELS, messages, stage="stage2", session_id=session_id
    )

    # Format results
    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed,
                "duration_ms": response.get('duration_ms'),
            })

    elapsed = time.perf_counter() - start
    if stage2_results:
        slowest = max(
            (r for r in stage2_results if r.get('duration_ms') is not None),
            key=lambda r: r['duration_ms'],
            default=None,
        )
        slowest_tag = f" slowest={slowest['model']}" if slowest else ""
        print(f"[timing] stage=stage2 total={elapsed:.1f}s{slowest_tag}")

    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    session_id: str = "",
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2
        session_id: OpenRouter session id (conversation grouping)

    Returns:
        Dict with 'model' and 'response' keys
    """
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model with a hard timeout. The SDK timeout applies per
    # request/response lifecycle and can be beaten by providers that drip
    # keepalive data slowly; wait_for enforces a wall-clock ceiling.
    start = time.perf_counter()
    primary_model = CHAIRMAN_MODEL
    fallback_model = CHAIRMAN_FALLBACK_MODEL
    response = None
    from_fallback = False

    try:
        response = await asyncio.wait_for(
            query_model(primary_model, messages, stage="stage3", session_id=session_id),
            timeout=CHAIRMAN_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        elapsed_s = round(time.perf_counter() - start, 1)
        print(
            f"[timing] stage=stage3 model={primary_model} elapsed={elapsed_s}s "
            f"TIMEOUT after {CHAIRMAN_TIMEOUT_S}s -> failing over to {fallback_model}"
        )

    # Primary failed or timed out: promote the fallback vice-chairman.
    if response is None:
        from_fallback = True
        try:
            response = await asyncio.wait_for(
                query_model(fallback_model, messages, stage="stage3", session_id=session_id),
                timeout=CHAIRMAN_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            elapsed_s = round(time.perf_counter() - start, 1)
            print(
                f"[timing] stage=stage3 model={fallback_model} elapsed={elapsed_s}s "
                f"TIMEOUT after {CHAIRMAN_TIMEOUT_S}s"
            )

    if response is None:
        total_elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        return {
            "model": CHAIRMAN_MODEL,
            "response": None,
            "error": (
                "The Council's Chairman was unable to deliver a synthesis. "
                "Please try again in a moment."
            ),
            "duration_ms": total_elapsed_ms,
        }

    delivering_model = fallback_model if from_fallback else primary_model
    elapsed_ms = response.get('duration_ms')
    total_elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    if elapsed_ms is not None:
        print(
            f"[timing] stage=stage3 model={delivering_model} "
            f"total={total_elapsed_ms}ms inference={elapsed_ms}ms"
        )

    result = {
        "model": delivering_model,
        "response": response.get('content', ''),
        "duration_ms": total_elapsed_ms,
    }
    if from_fallback:
        result["fallback"] = True
    return result


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            return re.findall(r'Response [A-Z]', ranking_section)

    # Fallback: try to find any "Response X" patterns in order
    return re.findall(r'Response [A-Z]', ranking_text)


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model (each must have 'parsed_ranking')
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    # Track positions for each model
    model_positions: Dict[str, List[int]] = defaultdict(list)

    for ranking in stage2_results:
        # Reuse the ranking already parsed during stage 2, falling back to a
        # fresh parse only if it wasn't provided.
        parsed_ranking = ranking.get('parsed_ranking') or parse_ranking_from_text(
            ranking['ranking']
        )

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str, session_id: str = "") -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message
        session_id: OpenRouter session id (conversation grouping)

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model(
        "google/gemini-2.5-flash", messages, timeout=30.0, stage="title",
        session_id=session_id,
    )

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(
    user_query: str,
    session_id: str = "",
) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Args:
        user_query: The user's question
        session_id: OpenRouter session id (conversation grouping)

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    # Stage 1: Collect individual responses
    stage1_results = await stage1_collect_responses(user_query, session_id=session_id)

    # If no models responded successfully, return error
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }, {}

    # Stage 2: Collect rankings
    stage2_results, label_to_model = await stage2_collect_rankings(
        user_query, stage1_results, session_id=session_id
    )

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3: Synthesize final answer
    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results,
        session_id=session_id,
    )

    # Prepare metadata
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings
    }

    return stage1_results, stage2_results, stage3_result, metadata
