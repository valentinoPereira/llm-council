"""FastAPI backend for LLM Council."""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import jobs, storage
from .config import USE_SIMULATED_MODELS
from .openrouter import close_client, get_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open the SQLite database and ensure the schema exists before serving
    # any request.
    await storage.init_db()
    # A fresh backend process has no jobs, so any 'pending' assistant row at
    # startup is an orphan from a crash/restart — flip it to an error state.
    await storage.fail_orphan_pending_messages()
    # Eagerly initialize the shared httpx client so the first request doesn't
    # pay the connection-pool setup cost. Skip this in simulated mode so no
    # OpenRouter API key is required for local UI testing.
    if not USE_SIMULATED_MODELS:
        get_client()
    try:
        yield
    finally:
        await close_client()
        await storage.close_db()


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
    category: Optional[str] = None
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    category: Optional[str] = None
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return await storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation, or return the existing empty one if present."""
    conversation_id = str(uuid.uuid4())
    conversation = await storage.get_or_create_empty_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str):
    """Permanently delete a conversation and all of its messages."""
    deleted = await storage.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Stop any live run for the deleted conversation so it exits cleanly
    # (its task's finally handles terminal-state cleanup).
    jobs.cancel_and_remove(conversation_id)


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process (detached).
    Returns the complete response with all stages.
    """
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Pre-flight the input-length guard into a clean HTTP 400.
    if len(request.content) > storage.MAX_USER_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Message content exceeds maximum length of "
                f"{storage.MAX_USER_MESSAGE_LENGTH} characters"
            ),
        )

    is_first_message = len(conversation["messages"]) == 0
    session_id = openrouter_session_id(conversation_id)
    try:
        job = await jobs.start_run(
            conversation_id, request.content, session_id, is_first_message
        )
    except ValueError as e:  # over-length from add_user_message
        raise HTTPException(status_code=400, detail=str(e))
    except jobs.RunAlreadyActive:
        raise HTTPException(
            status_code=409,
            detail="A council run is already in progress for this conversation",
        )

    await job.task  # do not swallow CancelledError; re-raise it

    # Read the freshly-persisted assistant row (matches what the job wrote).
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        # The conversation was deleted while we were awaiting — mirror the
        # 404 from the initial check instead of crashing on None.
        raise HTTPException(status_code=404, detail="Conversation not found")
    last = conversation["messages"][-1]
    return {
        "stage1": last["stage1"],
        "stage2": last["stage2"],
        "stage3": last["stage3"],
        "metadata": last["metadata"],
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Start a detached council run and stream it as Server-Sent Events.

    The run's lifetime is owned by the backend (``jobs.start_run`` spins up
    ``job.task`` before the response starts), so a client disconnect only
    closes this subscription — the run survives and persists to SQLite. This
    endpoint contains no stage logic; it never touches council.py.
    """
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

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

    is_first_message = len(conversation["messages"]) == 0
    session_id = openrouter_session_id(conversation_id)
    try:
        job = await jobs.start_run(
            conversation_id, request.content, session_id, is_first_message
        )
    except ValueError as e:  # over-length from add_user_message
        raise HTTPException(status_code=400, detail=str(e))
    except jobs.RunAlreadyActive:
        raise HTTPException(
            status_code=409,
            detail="A council run is already in progress for this conversation",
        )

    # The stage coroutines live in job.task (created by create_task before
    # the response starts), so a client disconnect only closes this
    # subscription generator — the run survives.
    return EventSourceResponse(job.subscribe(), ping=15)


@app.get("/api/conversations/{conversation_id}/run/events")
async def run_events(conversation_id: str):
    """Attach/reattach to a conversation's run event stream.

    If a job exists (live *or* finished), replay its entire event log, then
    tail live events, closing after ``complete``/``error`` is yielded. If no
    job exists, send a single ``run_inactive`` event and close. (The orphan
    sweeper at startup makes stale pending rows resolve to ``error``.)
    """
    job = jobs.get_job(conversation_id)
    if job is not None:
        return EventSourceResponse(job.subscribe(), ping=15)

    async def inactive_generator():
        yield {"data": json.dumps({"type": "run_inactive"})}

    return EventSourceResponse(inactive_generator(), ping=15)


@app.get("/api/conversations/{conversation_id}/run/status")
async def run_status(conversation_id: str):
    """Run-status metadata for a conversation (sidebar badge / debugging)."""
    job = jobs.get_job(conversation_id)
    if job is None:
        return {"active": False, "done": False}
    return {"active": not job.done, "done": job.done}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
