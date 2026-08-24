"""Where a lead stands with you, and the one way that can be lost.

The dangerous case is not a wrong colour on a badge. It is a search running a
week later, finding the same channel, and quietly resetting "Contatado" to
"Não contatado" — because then the reader writes to someone twice and the app
never told them anything was wrong. Most of this file exists for that.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.leads import LeadStore
from app.posts import PostStore, score_post
from app.status import DEFAULT_STATUS, STATUSES, clean, is_valid


def channel(cid: str = "UC1", title: str = "Canal", email: str | None = "a@b.com"):
    return {
        "id": cid, "title": title, "handle": "@canal", "url": "https://y/c",
        "subscribers": 1000, "subscribers_hidden": False, "video_count": 10,
        "country": "BR", "thumbnail": None, "email": email, "socials": [],
        "uploads_per_month": 4.0, "cadence": [1, 2], "cadence_trend": 1.0,
        "days_since_last_upload": 3, "last_upload_at": None, "niche": "games",
        "score": {"total": 50, "reachability": 10, "rhythm": 10, "recency": 10, "fit": 20},
    }


def post(pid: str = "p1", text: str = "preciso de um editor de vídeo"):
    row = {
        "id": pid, "source": "x", "author": "alguem", "author_name": "Alguém",
        "author_followers": 900, "author_url": "https://x.com/alguem", "text": text,
        "url": "https://x.com/alguem/status/1", "posted_at": None, "replies": 0,
        "likes": 0, "budget": False, "ongoing": False, "matched": "preciso de um editor",
        "query": "teste",
    }
    row["score"] = score_post(row)
    return row


# ------------------------------------------------------------- o vocabulário
def test_the_funnel_has_the_four_steps_the_screen_shows():
    assert list(STATUSES) == ["novo", "contatado", "respondeu", "parceria"]


def test_a_lead_starts_as_not_contacted():
    assert DEFAULT_STATUS == "novo"


@pytest.mark.parametrize("value", ["", None, "   ", "inventado", "CONTATADO?"])
def test_anything_unreadable_draws_as_not_contacted(value):
    """A blank cell would be a third meaning nobody asked for."""
    assert clean(value) == "novo"


def test_a_known_name_survives_cleaning_whatever_the_case():
    assert clean("  Contatado ") == "contatado"


def test_only_the_four_are_accepted_from_outside():
    assert is_valid("parceria")
    assert not is_valid("fechado")


# --------------------------------------------------- the failure that matters
def test_a_later_search_does_not_reset_what_you_marked():
    """The whole reason status is absent from the refreshed columns.

    Find a channel, mark it contacted, find it again. If this ever fails, the
    app starts telling you to write to people you already wrote to.
    """
    store = LeadStore(":memory:")
    store.save_many([channel()])
    assert store.set_status("UC1", "contatado")

    # The same channel comes back in a later search, with fresher numbers.
    again = channel(title="Canal (novo nome)")
    again["subscribers"] = 5000
    store.save_many([again])

    rows, _ = store.list()
    assert rows[0]["status"] == "contatado"
    # ... and the refresh still did its job.
    assert rows[0]["subscribers"] == 5000
    assert rows[0]["title"] == "Canal (novo nome)"


def test_a_later_search_does_not_reset_a_posts_status(tmp_path):
    # A file, not ":memory:": PostStore opens a fresh connection per call, and
    # an in-memory database would be a different, empty one every time.
    store = PostStore(tmp_path / "posts.db")
    store.save_many([post()])
    assert store.set_status("p1", "respondeu")

    again = post()
    again["replies"] = 12
    store.save_many([again])

    rows, _ = store.list()
    assert rows[0]["status"] == "respondeu"
    assert rows[0]["replies"] == 12


# ------------------------------------------------------------------ o básico
def test_a_new_lead_is_not_contacted():
    store = LeadStore(":memory:")
    store.save_many([channel()])
    rows, _ = store.list()
    assert rows[0]["status"] == "novo"


def test_moving_a_lead_that_is_not_there_says_so():
    store = LeadStore(":memory:")
    assert store.set_status("UC-inexistente", "contatado") is False


def test_an_unknown_status_is_stored_as_not_contacted_never_raw():
    """The route rejects these, but the store is the last line: nothing
    unreadable reaches the database."""
    store = LeadStore(":memory:")
    store.save_many([channel()])
    store.set_status("UC1", "qualquer coisa")
    rows, _ = store.list()
    assert rows[0]["status"] == "novo"


# ------------------------------------------------------------------ filtrar
def test_the_base_can_be_narrowed_to_one_step():
    store = LeadStore(":memory:")
    store.save_many([channel("UC1"), channel("UC2"), channel("UC3")])
    store.set_status("UC2", "parceria")

    parceiros, total = store.list(status="parceria")
    assert [r["id"] for r in parceiros] == ["UC2"]
    assert total == 1

    novos, total = store.list(status="novo")
    assert {r["id"] for r in novos} == {"UC1", "UC3"}
    assert total == 2


def test_filtering_by_a_status_nobody_uses_returns_nothing_not_everything():
    """An unknown name must not fall through to "no filter" — that would show
    the whole base while the screen says it is showing one step of it."""
    store = LeadStore(":memory:")
    store.save_many([channel("UC1")])
    rows, total = store.list(status="parceria")
    assert rows == [] and total == 0


def test_posts_can_be_narrowed_the_same_way(tmp_path):
    store = PostStore(tmp_path / "posts.db")
    store.save_many([post("p1"), post("p2")])
    store.set_status("p1", "contatado")
    rows, total = store.list(status="contatado")
    assert [r["id"] for r in rows] == ["p1"]
    assert total == 1


# ----------------------------------------------------------------- migração
def test_a_base_written_before_this_column_existed_still_opens(tmp_path):
    """The bases on disk hold work that cost quota and money. Adding a column
    must not ask anyone to start over."""
    path = tmp_path / "leads.db"
    store = LeadStore(str(path))
    store.save_many([channel("UC1")])

    # Reproduce the old shape by dropping the column back off.
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE leads DROP COLUMN status")
        conn.commit()

    reopened = LeadStore(str(path))
    rows, total = reopened.list()
    assert total == 1
    assert rows[0]["id"] == "UC1"
    assert rows[0]["status"] == "novo"
    # And it is writable again, not merely readable.
    assert reopened.set_status("UC1", "contatado")
    assert reopened.list()[0][0]["status"] == "contatado"


def test_a_posts_base_written_before_the_column_still_opens(tmp_path):
    path = tmp_path / "posts.db"
    store = PostStore(str(path))
    store.save_many([post("p1")])

    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE posts DROP COLUMN status")
        conn.commit()

    reopened = PostStore(str(path))
    rows, total = reopened.list()
    assert total == 1
    assert rows[0]["status"] == "novo"
    assert reopened.set_status("p1", "parceria")
