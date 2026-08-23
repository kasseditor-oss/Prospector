"""The hiring-post base, and turning a raw tweet into one.

Separate from the lead base on purpose, so these tests also pin the thing that
makes the separation worth it: a post is scored by how fast it needs an answer,
which is nothing like how a channel is scored.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.posts import PostStore, hours_old, score_post
from app.xsearch import to_post


def post(pid: str, **over):
    base = {
        "id": pid,
        "source": "x",
        "author": f"user{pid}",
        "author_name": f"User {pid}",
        "author_followers": 1000,
        "author_url": f"https://x.com/user{pid}",
        "text": "Preciso de um editor de vídeo",
        "url": f"https://x.com/user{pid}/status/{pid}",
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "replies": 0,
        "likes": 0,
        "budget": False,
        "ongoing": False,
        "matched": "preciso de um editor",
        "query": "",
    }
    base.update(over)
    return base


@pytest.fixture
def store(tmp_path):
    return PostStore(tmp_path / "posts.db")


# --------------------------------------------------------------------- store
def test_the_base_grows_instead_of_being_replaced(store):
    store.save_many([post("1"), post("2")])
    store.save_many([post("3")])
    assert store.count() == 3


def test_finding_a_post_again_refreshes_it_without_moving_its_entry_date(store):
    store.save_many([post("1", replies=0)])
    original = store.list()[0][0]["first_seen"]
    store.save_many([post("1", replies=25)])

    row = store.list()[0][0]
    assert row["replies"] == 25
    assert row["first_seen"] == original, "reencontrar não é descobrir"


def test_new_and_refreshed_are_counted_apart(store):
    assert store.save_many([post("1"), post("2")]) == (2, 0)
    assert store.save_many([post("2"), post("3")]) == (1, 1)


def test_the_text_and_the_author_are_searchable(store):
    store.save_many([
        post("1", text="Procuro editor para canal de futebol", author="fut"),
        post("2", text="Preciso de editor de Minecraft", author="mine"),
    ])
    assert [p["id"] for p in store.list(query="futebol")[0]] == ["1"]
    assert [p["id"] for p in store.list(query="mine")[0]] == ["2"]


def test_only_posts_that_mention_money_can_be_isolated(store):
    store.save_many([post("1", budget=True), post("2", budget=False)])
    assert [p["id"] for p in store.list(with_budget=True)[0]] == ["1"]


def test_tiny_accounts_can_be_filtered_out(store):
    store.save_many([post("1", author_followers=12), post("2", author_followers=9000)])
    assert [p["id"] for p in store.list(min_followers=1000)[0]] == ["2"]


def test_an_injected_sort_cannot_reach_the_database(store):
    store.save_many([post("1")])
    assert store.list(sort="'; DROP TABLE posts; --")[1] == 1
    assert store.count() == 1


def test_a_post_can_be_removed(store):
    store.save_many([post("1"), post("2")])
    assert store.delete("1") is True
    assert store.delete("1") is False
    assert [p["id"] for p in store.list()[0]] == ["2"]


def test_saving_nothing_is_not_an_error(store):
    assert store.save_many([]) == (0, 0)


# --------------------------------------------------------------------- score
def _aged(hours: float, **over):
    when = datetime.now(timezone.utc) - timedelta(hours=hours)
    return post("x", posted_at=when.isoformat(), **over)


def test_freshness_dominates_everything_else():
    """A perfect post from last week loses to a plain one from this morning.

    This is the whole thesis of the source: these posts collect twenty replies
    in an afternoon, so being early beats being a better fit.
    """
    stale_but_perfect = _aged(200, budget=True, ongoing=True, author_followers=50_000)
    fresh_but_plain = _aged(1)
    assert score_post(fresh_but_plain) > score_post(stale_but_perfect)


def test_a_crowded_post_scores_below_an_untouched_one():
    assert score_post(_aged(2, replies=0)) > score_post(_aged(2, replies=40))


def test_naming_money_lifts_the_score():
    assert score_post(_aged(2, budget=True)) > score_post(_aged(2, budget=False))


def test_recurring_work_lifts_the_score():
    assert score_post(_aged(2, ongoing=True)) > score_post(_aged(2, ongoing=False))


def test_the_score_stays_inside_its_range():
    best = _aged(0.5, budget=True, ongoing=True, author_followers=900_000, replies=0)
    worst = _aged(5000, replies=500, author_followers=0)
    assert 1 <= score_post(worst) <= score_post(best) <= 99


def test_a_post_with_no_date_is_not_treated_as_fresh():
    assert hours_old(None) is None
    assert score_post(post("x", posted_at=None)) < score_post(_aged(1))


def test_x_date_format_is_understood():
    """The actor returns 'Fri Aug 21 16:20:39 +0000 2026', not ISO."""
    assert hours_old("Fri Aug 21 16:20:39 +0000 2026") is not None


# ------------------------------------------------------- raw tweet -> a post
REAL_TWEET = {
    "id": "1958800000000000001",
    "text": "Procuro editor de vídeo curto (tiktok/reels) para conteúdo de futebol.",
    "url": "https://x.com/FalaSerante/status/1958800000000000001",
    "createdAt": "Sat Aug 22 18:00:16 +0000 2026",
    "replyCount": 3,
    "likeCount": 11,
    "author": {"userName": "FalaSerante", "name": "Serante", "followers": 19},
}

REAL_COMPETITOR = {
    "id": "1958800000000000002",
    "text": "A Long-form that I recently Edited Hiring a video editor? Dm me let's work together!",
    "url": "https://x.com/WebflowXs/status/1958800000000000002",
    "createdAt": "Sat Aug 22 19:00:16 +0000 2026",
    "replyCount": 0,
    "likeCount": 2,
    "author": {"userName": "WebflowXs", "name": "Webflow", "followers": 29},
}


def test_a_real_hiring_tweet_becomes_a_post():
    result = to_post(REAL_TWEET)
    assert result is not None
    assert result["author"] == "FalaSerante"
    assert result["author_url"] == "https://x.com/FalaSerante"
    assert result["author_followers"] == 19
    assert result["replies"] == 3
    assert result["source"] == "x"
    assert result["score"] >= 1


def test_a_real_competitor_tweet_is_dropped():
    """The advert disguised as a client's question, from the live search."""
    assert to_post(REAL_COMPETITOR) is None


def test_a_tweet_without_an_id_is_dropped():
    assert to_post({"text": "Preciso de um editor de vídeo", "author": {}}) is None
