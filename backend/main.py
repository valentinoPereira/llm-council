"""FastAPI backend for LLM Council."""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import storage
from .council import (
    calculate_aggregate_rankings,
    generate_conversation_title,
    run_full_council,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from .openrouter import close_client, get_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eagerly initialize the shared httpx client so the first request doesn't
    # pay the connection-pool setup cost.
    get_client()
    try:
        yield
    finally:
        await close_client()


app = FastAPI(title="LLM Council API", lifespan=lifespan)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Storage helpers ----------------------------------------------------------

# OpenRouter caps session ids at 256 characters.
OPENROUTER_SESSION_ID_MAX = 256


def openrouter_session_id(conversation_id: str) -> str:
    """Deterministic OpenRouter session id: one conversation = one session.

    Derived purely from the conversation id so it is stable across every
    turn, every stage (1-3), and title generation — even after the title
    changes mid-conversation. OpenRouter uses it as a sticky routing key
    (same provider per session, maximizing prompt cache hits) and to group
    requests in its console/dashboard.
    """
    return f"llm-council-{conversation_id}"[:OPENROUTER_SESSION_ID_MAX]

# Storage functions are sync and touch the disk; run them in the default
# thread pool so they don't block the event loop. Wrap them once here so
# endpoint handlers stay readable.
def _to_thread(func, *args, **kwargs):
    return asyncio.to_thread(func, *args, **kwargs)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return await _to_thread(storage.list_conversations)


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = await _to_thread(storage.create_conversation, conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = await _to_thread(storage.get_conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = await _to_thread(storage.get_conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message (translates the input-length guard into a client error
    # instead of a bare 500)
    try:
        await _to_thread(storage.add_user_message, conversation_id, request.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # One conversation = one OpenRouter session, across all model calls
    # (stages 1-3 and title generation).
    session_id = openrouter_session_id(conversation_id)

    # Start title generation in parallel with the council run, mirroring the
    # streaming endpoint's pattern.
    title_task: asyncio.Task[str] | None = None
    if is_first_message:
        title_task = asyncio.create_task(
            generate_conversation_title(request.content, session_id=session_id)
        )

    try:
        # Run the 3-stage council process
        stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
            request.content, session_id=session_id
        )
    except BaseException:
        # Don't leak the background title task if the council run fails.
        if title_task is not None:
            title_task.cancel()
        raise

    # Add assistant message with all stages
    await _to_thread(
        storage.add_assistant_message,
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result,
        metadata,
    )

    # Persist the title if it was being generated.
    if title_task is not None:
        title = await title_task
        await _to_thread(storage.update_conversation_title, conversation_id, title)

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata,
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = await _to_thread(storage.get_conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Pre-flight the input-length guard so oversized messages get a proper
    # HTTP 400 (matching the non-streaming endpoint) instead of an SSE error
    # event on a 200 response.
    if len(request.content) > storage.MAX_USER_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Message content exceeds maximum length of "
                f"{storage.MAX_USER_MESSAGE_LENGTH} characters"
            ),
        )

    async def event_generator():
        # One conversation = one OpenRouter session, across all model calls
        # (stages 1-3 and title generation).
        session_id = openrouter_session_id(conversation_id)
        title_task: asyncio.Task[str] | None = None
        try:
            # Add user message
            await _to_thread(storage.add_user_message, conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content, session_id=session_id)
                )

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(
                request.content, session_id=session_id
            )
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(
                request.content, stage1_results, session_id=session_id
            )
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(
                request.content, stage1_results, stage2_results, session_id=session_id
            )
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                await _to_thread(storage.update_conversation_title, conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            await _to_thread(
                storage.add_assistant_message,
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                {"label_to_model": label_to_model, "aggregate_rankings": aggregate_rankings},
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Don't leak the background title task on failure.
            if title_task is not None:
                title_task.cancel()
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Client disconnect cancels this generator with CancelledError /
            # GeneratorExit (BaseException, not caught above) — make sure the
            # title task never outlives the stream. Cancelling an
            # already-finished task is a no-op.
            if title_task is not None and not title_task.done():
                title_task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
