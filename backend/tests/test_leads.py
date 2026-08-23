"""The lead base.

A search costs quota, so what it found has to survive the tab that ran it.
These tests pin the two properties that make the base worth keeping: nothing
already there is lost when a new search runs, and a channel found twice is one
lead, not two.
"""

from __future__ import annotations

import pytest

from app.leads import LeadStore


def channel(cid: str, *, title: str = "Canal", subs: int = 1000, score: int = 50,
            email: str | None = None, niche: str = "edição") -> dict:
    return {
        "id": cid,
        "title": title,
        "handle": "@" + cid.lower(),
        "url": f"https://youtube.com/@{cid.lower()}",
        "subscribers": subs,
        "subscribers_hidden": False,
        "video_count": 120,
        "country": "BR",
        "thumbnail": None,
        "email": email,
        "socials": [{"network": "instagram", "handle": "x", "url": "https://instagram.com/x"}],
        "uploads_per_month": 4.0,
        "cadence": [1, 2, 3],
        "cadence_trend": 1.2,
        "days_since_last_upload": 5,
        "last_upload_at": None,
        "niche": niche,
        "score": {"total": score, "reachability": 1, "rhythm": 2, "recency": 3, "fit": 4},
    }


@pytest.fixture
def store(tmp_path):
    return LeadStore(tmp_path / "leads.db")


def test_a_second_search_adds_to_the_base_instead_of_replacing_it():
    """The whole point: search two niches, keep both."""
    store = LeadStore(":memory:")
    store.save_many([channel("A"), channel("B")])
    store.save_many([channel("C")])
    ids = {lead["id"] for lead in store.list()[0]}
    assert ids == {"A", "B", "C"}


def test_the_same_channel_found_twice_is_one_lead(store):
    store.save_many([channel("A", subs=1000)])
    store.save_many([channel("A", subs=1500)])
    leads, total = store.list()
    assert total == 1
    assert leads[0]["subscribers"] == 1500, "the newer numbers should win"


def test_first_seen_is_not_rewritten_by_a_later_search(store):
    """When a lead entered the base is history; re-finding it is not a new lead."""
    store.save_many([channel("A")])
    original = store.list()[0][0]["first_seen"]
    store.save_many([channel("A", subs=99_000)])
    refreshed = store.list()[0][0]
    assert refreshed["first_seen"] == original
    assert refreshed["last_seen"] >= original


def test_save_reports_what_was_new(store):
    assert store.save_many([channel("A"), channel("B")]) == (2, 0)
    assert store.save_many([channel("B"), channel("C")]) == (1, 1)


def test_the_base_survives_a_restart(tmp_path):
    """A new process must find what the last one saved — that is the feature."""
    path = tmp_path / "leads.db"
    LeadStore(path).save_many([channel("A"), channel("B")])
    assert LeadStore(path).count() == 2


def test_rich_fields_survive_the_round_trip(store):
    store.save_many([channel("A")])
    lead = store.list()[0][0]
    assert lead["cadence"] == [1, 2, 3]
    assert lead["socials"][0]["network"] == "instagram"
    assert lead["score"]["total"] == 50
    assert lead["subscribers_hidden"] is False


def test_search_matches_title_handle_and_niche(store):
    store.save_many([
        channel("A", title="Cozinha Fácil", niche="culinária"),
        channel("B", title="Minecraft BR", niche="games"),
    ])
    assert [l["id"] for l in store.list(query="cozinha")[0]] == ["A"]
    assert [l["id"] for l in store.list(query="games")[0]] == ["B"]
    assert [l["id"] for l in store.list(query="@b")[0]] == ["B"]


def test_email_filter_keeps_only_reachable_leads(store):
    store.save_many([channel("A", email="a@canal.com"), channel("B")])
    assert [l["id"] for l in store.list(with_email=True)[0]] == ["A"]


def test_sorting_by_score_puts_the_best_lead_first(store):
    store.save_many([channel("A", score=30), channel("B", score=90)])
    assert [l["id"] for l in store.list(sort="score")[0]] == ["B", "A"]


def test_an_unknown_sort_falls_back_instead_of_breaking(store):
    """Sort names reach SQL, so an unexpected one must not reach it as-is."""
    store.save_many([channel("A")])
    assert store.list(sort="'; DROP TABLE leads; --")[1] == 1
    assert store.count() == 1


def test_deleting_a_lead_removes_only_that_one(store):
    store.save_many([channel("A"), channel("B")])
    assert store.delete("A") is True
    assert store.delete("A") is False
    assert [l["id"] for l in store.list()[0]] == ["B"]


def test_clearing_empties_the_base(store):
    store.save_many([channel("A"), channel("B")])
    assert store.clear() == 2
    assert store.count() == 0


def test_total_counts_the_whole_base_not_the_page(store):
    store.save_many([channel(f"C{i}") for i in range(30)])
    leads, total = store.list(limit=10)
    assert len(leads) == 10
    assert total == 30


def test_saving_nothing_is_not_an_error(store):
    assert store.save_many([]) == (0, 0)
