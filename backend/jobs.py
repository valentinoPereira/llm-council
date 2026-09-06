"""Detached council runs: a run's lifetime is independent of any HTTP
connection. jobs.py owns the registry and event fan-out; the stage pipeline
itself stays in council.py (unmodified).

A run is an ``asyncio`` task created before the HTTP response starts
streaming, so a client disconnect, tab switch, page reload, or closed site
only closes that one subscription — the run keeps going and persists
progress stage-by-stage to SQLite inside `storage.py`. SSE here is a
subscribable *view* of the run (replay log + live tail), not its driver.
"""

import asyncio
import json
import time
from typing import Any, Coroutine, Dict, List, Optional

from . import storage
from .config import STAGE_HEARTBEAT_S
from .council import (
    calculate_aggregate_rankings,
    generate_conversation_metadata,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)

# Ordered (insertion order) conversation_id -> CouncilJob. Finished jobs are
# kept so a late subscriber can replay the buffered event log; they are
# pruned when replaced, deleted, or when more than this many accumulate.
_MAX_FINISHED_JOBS = 50

_JOBS: Dict[str, "CouncilJob"] = {}


class RunAlreadyActive(Exception):
    """Raised by start_run when a live job already exists for a conversation."""


class CouncilJob:
    def __init__(self, conversation_id: str, content: str, message_id: int | None):
        # message_id is set after the pending assistant row is inserted; the
        # job is registered in _JOBS before that insert, so a placeholder
        # (message_id=None) is valid transiently.
        self.conversation_id = conversation_id
        self.content = content
        self.message_id = message_id
        # Ordered replay log; a subscriber's sequence position = its cursor.
        self.events: List[dict] = []
        self.cond: asyncio.Condition = asyncio.Condition()
        self.done: bool = False  # terminal state reached
        self.task: "asyncio.Task | None" = None

    async def emit(self, event: dict) -> None:
        """Append an event to the replay log and wake waiting subscribers."""
        self.events.append(event)
        async with self.cond:
            self.cond.notify_all()

    async def subscribe(self):
        """Async generator yielding SSE frames (``{"data": json.dumps(...)}``).

        Safe to call concurrently by any number of subscribers. The cursor is
        a **local** variable in the generator (different subscribers attach at
        different times) — only the event list and condition are shared. A
        single cursor drives both the replay and the live tail, which is what
        makes the \"events arrived while replaying\" race safe. Returns once
        caught up to the end and the job is done.
        """
        cursor = 0
        while True:
            # Replay / catch-up: yield everything from our position.
            while cursor < len(self.events):
                event = self.events[cursor]
                cursor += 1
                yield {"data": json.dumps(event)}
            # Live tail: block until a new event or the terminal state.
            async with self.cond:
                await self.cond.wait_for(
                    lambda: len(self.events) > cursor or self.done
                )
            # Recheck after waking: either there are new events to replay
            # (loop again) or we are caught up and the job is done (exit).
            if cursor == len(self.events) and self.done:
                return


async def _await_with_progress(
    label: str,
    coro: Coroutine,
    heartbeat_s: float | None = None,
):
    """Run a stage coroutine and emit heartbeat ticks until it finishes.

    Yields ``stage_done`` frames carrying the result once the coroutine
    completes, and ``stage_progress`` frames while it runs. Only progress
    events are forwarded to the client; the final ``stage_done`` is consumed
    by the caller.

    The task is NOT shielded: in this design the only thing that closes this
    generator is the job body itself failing or being cancelled (e.g. by
    conversation deletion) — client disconnects never reach it because the
    job runs inside ``job.task``, outside the request/response cycle.
    """
    interval = heartbeat_s if heartbeat_s is not None else STAGE_HEARTBEAT_S
    start = time.perf_counter()
    task = asyncio.ensure_future(coro)
    try:
        while True:
            done, pending = await asyncio.wait(
                {task}, timeout=interval, return_when=asyncio.FIRST_COMPLETED
            )
            if task in done:
                yield {
                    "data": json.dumps(
                        {
                            "type": "stage_done",
                            "stage": label,
                            "result": task.result(),
                        }
                    )
                }
                return
            elapsed = time.perf_counter() - start
            yield {
                "data": json.dumps(
                    {"type": "stage_progress", "stage": label, "elapsed_s": round(elapsed, 1)}
                )
            }
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def _safe_update(job: CouncilJob, **kwargs) -> None:
    """Persist a stage/metadata update, logging (never raising) on failure.

    ``update_assistant_message`` may target a cascaded-away row and
    ``update_conversation_title`` raises ValueError when the conversation was
    deleted mid-run. A job cancelled by conversation deletion must exit via
    ``CancelledError`` cleanly, without secondary exceptions.
    """
    try:
        await storage.update_assistant_message(job.message_id, **kwargs)
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort
        print(f"[jobs] failed to persist message {job.message_id}: {exc}")


async def start_run(
    conversation_id: str,
    content: str,
    session_id: str,
    is_first_message: bool,
) -> CouncilJob:
    """Register a new detached run for a conversation (synchronous before the
    response starts) and return its job.

    Steps, in order, each awaited before continuing:

    1. Raise RunAlreadyActive if a **live** job already exists.
    2. Persist the user message (its ValueError propagates to the endpoint
       and becomes HTTP 400 — done before the response starts so the 400
       test stays deterministic).
    3. Create the pending assistant row.
    4. Construct + register the job.
    5. Spin up the detached task (before the response starts streaming).

    After step 3 the DB reflects \"user + pending assistant\", so any client
    that fetches the conversation can discover the run — there is no window
    where a run exists but is invisible to GET /api/conversations/{id}.
    """
    existing = _JOBS.get(conversation_id)
    if existing is not None and not existing.done:
        raise RunAlreadyActive()

    # Register the job synchronously, before the awaits below, so a concurrent
    # start_run for this conversation sees it and raises RunAlreadyActive. If
    # registration happened after the awaits, two requests could both pass the
    # check and one would silently evict the other from _JOBS.
    job = CouncilJob(conversation_id, content, message_id=None)
    _JOBS[conversation_id] = job
    try:
        await storage.add_user_message(conversation_id, content)
        job.message_id = await storage.create_pending_assistant_message(
            conversation_id
        )
    except BaseException:
        # Undo the placeholder registration so a failed start (e.g. the 400
        # over-length path) doesn't leave a broken entry poisoning retries.
        if _JOBS.get(conversation_id) is job:
            _JOBS.pop(conversation_id, None)
        raise

    job.task = asyncio.create_task(_run(job, session_id, is_first_message))
    _prune_finished_jobs()
    return job


async def _run(job: CouncilJob, session_id: str, is_first_message: bool) -> None:
    """The job body: run the 3-stage council and emit/persist as it goes.

    This is the former ``event_generator`` from main.py, adapted to emit +
    persist instead of yield. The event sequence/payloads are unchanged, so
    the existing frontend reducer and tests keep working.
    """
    title_task: "asyncio.Task | None" = None
    # Accumulated metadata from the stages (label_to_model, aggregate_rankings);
    # reused on success (status: complete) and on error (status: error).
    meta: Dict[str, Any] = {}
    try:
        if is_first_message:
            title_task = asyncio.create_task(
                generate_conversation_metadata(job.content, session_id=session_id)
            )

        # -- Stage 1 --------------------------------------------------------
        await job.emit({"type": "stage1_start"})
        stage1_results: List = []
        async for item in _await_with_progress(
            "stage1",
            stage1_collect_responses(job.content, session_id=session_id),
        ):
            _payload = json.loads(item["data"])
            if _payload.get("type") == "stage_done":
                stage1_results = _payload["result"]
            else:
                await job.emit(_payload)
        await job.emit({"type": "stage1_complete", "data": stage1_results})
        await _safe_update(job, stage1=stage1_results)

        # -- Stage 2 --------------------------------------------------------
        await job.emit({"type": "stage2_start"})
        stage2_raw = None
        async for item in _await_with_progress(
            "stage2",
            stage2_collect_rankings(
                job.content, stage1_results, session_id=session_id
            ),
        ):
            _payload = json.loads(item["data"])
            if _payload.get("type") == "stage_done":
                stage2_raw = _payload["result"]
            else:
                await job.emit(_payload)
        stage2_results, label_to_model = stage2_raw
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
        meta = {
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings,
        }
        await job.emit(
            {
                "type": "stage2_complete",
                "data": stage2_results,
                "metadata": dict(meta),
            }
        )
        await _safe_update(job, stage2=stage2_results, metadata={"status": "pending", **meta})

        # -- Stage 3 --------------------------------------------------------
        await job.emit({"type": "stage3_start"})
        stage3_result = None
        async for item in _await_with_progress(
            "stage3",
            stage3_synthesize_final(
                job.content, stage1_results, stage2_results, session_id=session_id
            ),
        ):
            _payload = json.loads(item["data"])
            if _payload.get("type") == "stage_done":
                stage3_result = _payload["result"]
            else:
                await job.emit(_payload)
        await job.emit({"type": "stage3_complete", "data": stage3_result})
        # If stage3_result contains an `error` key this is the existing
        # total-failure shape — the run genuinely finished; keep
        # status: "complete" and let the error travel inside the payload.
        await _safe_update(
            job,
            stage3=stage3_result,
            metadata={"status": "complete", **meta},
        )

        # -- Title ----------------------------------------------------------
        if title_task is not None:
            title, category = await title_task
            try:
                await storage.update_conversation_title(
                    job.conversation_id, title, category
                )
            except Exception as exc:  # noqa: BLE001 - conversation may be gone
                print(f"[jobs] failed to persist title for {job.conversation_id}: {exc}")
            await job.emit(
                {"type": "title_complete", "data": {"title": title, "category": category}}
            )

        # -- Done -----------------------------------------------------------
        await job.emit({"type": "complete"})

    except asyncio.CancelledError:
        # Job cancelled by conversation deletion: exit cleanly, no error event.
        raise
    except Exception as exc:  # noqa: BLE001 - never let an exception escape
        if title_task is not None and not title_task.done():
            title_task.cancel()
        message = str(exc)
        # Persist partial state as an error so a reload shows an error
        # assistant message, not a dangling pending row.
        await _safe_update(
            job, metadata={"status": "error", "error": message, **meta}
        )
        await job.emit({"type": "error", "message": message})
    finally:
        if title_task is not None and not title_task.done():
            title_task.cancel()
        job.done = True
        async with job.cond:
            job.cond.notify_all()


def get_job(conversation_id: str) -> Optional[CouncilJob]:
    """Return the job for a conversation, if any (live *or* finished)."""
    return _JOBS.get(conversation_id)


def cancel_and_remove(conversation_id: str) -> None:
    """Cancel a live job and drop it from the registry.

    Cancelling ``job.task`` runs its ``finally`` (terminal state + cleanup);
    ``_run``'s except/finally handles the rest.
    """
    job = _JOBS.pop(conversation_id, None)
    if job is not None and job.task is not None and not job.task.done():
        job.task.cancel()


def _prune_finished_jobs() -> None:
    """Drop the oldest finished jobs once more than _MAX_FINISHED_JOBS exist."""
    finished = [(k, v) for k, v in _JOBS.items() if v.done]
    excess = len(finished) - _MAX_FINISHED_JOBS
    if excess <= 0:
        return
    for key, _ in finished[:excess]:
        _JOBS.pop(key, None)
