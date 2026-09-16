"""Tests for the model rankings statistics (peer-review win rates).

Follows test_smoke.py's sandbox pattern: DATA_DIR points at a temp dir
before the backend is imported, so the real council.db is never touched.
"""
import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SANDBOX = tempfile.mkdtemp(prefix="llmc-rankings-")
os.environ["OPENROUTER_API_KEY"] = "test-key-not-used"

import importlib

import backend.config as cfg

cfg.DATA_DIR = os.path.join(SANDBOX, "conversations")
MODELS = ["model-a", "model-b", "model-c"]
cfg.COUNCIL_MODELS = MODELS  # endpoint filters to council models; sandbox them
import backend.storage  # noqa: E402
importlib.reload(backend.storage)
import backend.main  # noqa: E402 (needed for slice 2)
importlib.reload(backend.main)
from backend import storage  # noqa: E402
from backend.main import app  # noqa: E402

import httpx  # noqa: E402

MODELS = ["model-a", "model-b", "model-c"]


def agg(model, rank, count=3):
    return {"model": model, "average_rank": rank, "rankings_count": count}


async def seed_run(title, label_to_model, aggregate_rankings):
    """Insert one conversation with a single assistant message."""
    conversation_id = str(uuid.uuid4())
    await storage.create_conversation(conversation_id)
    await storage.update_conversation_title(conversation_id, title)
    await storage.add_assistant_message(
        conversation_id,
        stage1=[],
        stage2=[],
        stage3={},
        metadata={
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings,
        },
    )
    return conversation_id



async def main() -> int:
    await storage.init_db()
    try:
        # -- Seed data -------------------------------------------------------
        # Named runs: distinct shapes (win, tie, rookie, dummy, single-model).
        seed = [
            (
                "Meaning of life",
                {"Response A": "model-a", "Response B": "model-b", "Response C": "model-c"},
                [agg("model-a", 1.0), agg("model-b", 2.0), agg("model-c", 3.0)],
            ),
            (
                "Rule of 72",
                {"Response A": "model-a", "Response B": "model-b", "Response C": "model-c"},
                [agg("model-a", 1.0), agg("model-b", 1.0), agg("model-c", 2.0)],  # tie
            ),
            (
                "Doppler effect",
                {"Response A": "model-a", "Response B": "model-b", "Response C": "model-c"},
                [agg("model-b", 1.0), agg("model-a", 2.0), agg("model-c", 3.0)],
            ),
            (
                "Test naming",
                {"Response A": "model-c"},
                [agg("model-c", 1.0)],  # legit title — counts as c win
            ),
            (
                "Strawman fallacy",
                {"Response A": "model-a", "Response B": "model-b", "Response C": "retired-model"},
                [agg("retired-model", 1.0), agg("model-a", 2.0), agg("model-b", 3.0)],
            ),
            # Near-miss best: no model at exact 1.0 — model-a still wins at
            # 1.25 (best-in-run), the case the old == 1.0 rule dropped.
            (
                "Near-miss leader",
                {"Response A": "model-a", "Response B": "model-b", "Response C": "model-c"},
                [agg("model-a", 1.25), agg("model-b", 1.5), agg("model-c", 3.5)],
            ),
            # Near-miss co-leaders: shared best (1.5) — BOTH a and c win.
            (
                "Near-miss tie",
                {"Response A": "model-a", "Response B": "model-b", "Response C": "model-c"},
                [agg("model-a", 1.5), agg("model-b", 2.0), agg("model-c", 1.5)],
            ),
            # Dummy runs (excluded by title).
            (
                "test",
                {"Response A": "model-a", "Response B": "model-b", "Response C": "model-c"},
                [agg("model-c", 1.0), agg("model-a", 2.0), agg("model-b", 3.0)],
            ),
            (
                "abcd",
                {"Response A": "model-c", "Response B": "model-b"},
                [agg("model-c", 1.0), agg("model-b", 2.0)],
            ),
        ]

        for title, l2m, rankings in seed:
            await seed_run(title, l2m, rankings)

        # Bulk-fill so the council members clear the rankings quorum
        # (RANKINGS_MIN_APPEARANCES = 10): model-a wins 3 of 10, model-b 5 of
        # 10, model-c 2 of 10.
        for i in range(10):
            winner = ["model-b"] * 5 + ["model-a"] * 3 + ["model-c"] * 2
            l2m = {"Response A": "model-a", "Response B": "model-b", "Response C": "model-c"}
            # deterministic rotation over the winner plan
            win = winner[i % 10]
            others = [m for m in ["model-a", "model-b", "model-c"] if m != win]
            await seed_run(
                "History %d" % i,
                l2m,
                [agg(win, 1.0), agg(others[0], 2.0), agg(others[1], 3.0)],
            )

        # Extra unused empty conversation.
        await storage.create_conversation(str(uuid.uuid4()))

        # -- storage.get_model_rankings() ------------------------------------
        stats = {s["model"]: s for s in await storage.get_model_rankings()}

        # model-a: 16 appearances (3 named + 2 near-miss + 10 bulk + strawman),
        # 7 wins: 2 named + 2 near-miss (1.25 best, 1.5 tie) + 3 bulk
        assert stats["model-a"]["appearances"] == 16, stats["model-a"]
        assert stats["model-a"]["wins"] == 7, stats["model-a"]
        assert stats["model-a"]["win_rate"] == round(7 / 16, 4), stats["model-a"]

        # model-b: 16 appearances, 7 wins (tie in run 2 + run 3 + 5 bulk)
        assert stats["model-b"]["appearances"] == 16, stats["model-b"]
        assert stats["model-b"]["wins"] == 7, stats["model-b"]
        assert stats["model-b"]["win_rate"] == round(7 / 16, 4), stats["model-b"]

        # model-c: 16 appearances, 4 wins ("Test naming" + 1.5 tie + 2 bulk)
        assert stats["model-c"]["appearances"] == 16, stats["model-c"]
        assert stats["model-c"]["wins"] == 4, stats["model-c"]

        # models filter drops non-council models (retired-model is below
        # quorum anyway, but the filter also removes it pre-prior)
        filtered = await storage.get_model_rankings(models=MODELS)
        assert {s["model"] for s in filtered} == {"model-a", "model-b", "model-c"}

        # sorted by adjusted win rate desc. retired-model (1 appearance
        # 1 win = raw 1.0) is below the quorum (RANKINGS_MIN_APPEARANCES)
        # and is excluded entirely — new models cannot take the spotlight
        # on a tiny sample, however lucky.
        all_stats = await storage.get_model_rankings()
        by_model = {s["model"]: s for s in all_stats}
        assert "retired-model" not in by_model, all_stats  # below quorum
        # ordering by Wilson lower bound (ties fall back to adjusted rate,
        # then appearances): b and a share the same Wilson LB on 7/16, a
        # edges b only via the second key... both 7/16 → equal LB and
        # adjusted; a has more total wins vs c below. b vs a identical
        # stats → stable original dict order (a inserted first).
        assert [s["model"] for s in all_stats] == ["model-a", "model-b", "model-c"], all_stats
        # shrinkage: adjusted rates sit between the raw rate and the pooled
        # prior (computed over ALL models incl. below-quorum ones)
        prior = (7 + 7 + 4 + 1) / (16 * 3 + 1)
        for m, raw in (("model-a", 7 / 16), ("model-b", 7 / 16), ("model-c", 4 / 16)):
            adj = by_model[m]["adjusted_win_rate"]
            assert min(raw, prior) <= adj <= max(raw, prior) or adj == raw, (m, raw, adj, prior)

        # dummy runs did not leak appearances: model-b never appeared in a
        # dummy run only — its count matches legit runs alone.
        print("OK  storage.get_model_rankings()")

        # -- GET /api/rankings -----------------------------------------------
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/rankings")
            assert r.status_code == 200, r.text
            body = r.json()
            # Dummy-title conversations asked for model-c stats are excluded,
            # so retired-model (strawman run win) is filtered out by the
            # council filter and never appears.
            assert [s["model"] for s in body] == ["model-a", "model-b", "model-c"], body
            assert body[0]["win_rate"] == round(7 / 16, 4), body[0]
            # shares sum to exactly 1 across the returned slice
            total_share = sum(s["share"] for s in body)
            assert abs(total_share - 1.0) < 1e-6, total_share
            assert all(s["share"] > 0 for s in body), body
            # top? param slicing by adjusted rate — a and b tie on
            # wilson LB and adjusted rate; a wins on the stable insertion
            # order tie-break, b follows, c last.
            r = await client.get("/api/rankings", params={"top": 1})
            assert r.status_code == 200, r.text
            assert len(r.json()) == 1, r.json()
            assert r.json()[0]["model"] in ("model-a", "model-b"), r.json()
            # single-model slice: share is exactly 1
            assert r.json()[0]["share"] == 1.0, r.json()
            # top=0 falls back to 1 (guarded, never an empty list by accident)
            r = await client.get("/api/rankings", params={"top": 0})
            assert len(r.json()) == 1, r.json()
            print("OK  GET /api/rankings")

        return 0
    finally:
        await storage.close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
