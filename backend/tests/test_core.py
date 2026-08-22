"""Tests for the parts that decide what a user sees and pays for."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.keyring import (
    COST_CHANNELS_LIST,
    COST_SEARCH_LIST,
    DAILY_UNITS_PER_KEY,
    InMemoryKeyring,
    QuotaExhausted,
    estimate_search_cost,
)
from app.schemas import SearchFilters
from app.scoring import score_channel
from app.youtube import Channel, extract_email


# ------------------------------------------------------------------ scoring
def test_score_is_bounded():
    best = score_channel(
        subscribers=50_000, uploads_per_month=12, days_since_last_upload=1, has_email=True
    )
    worst = score_channel(
        subscribers=10, uploads_per_month=0, days_since_last_upload=900, has_email=False
    )
    assert 1 <= worst.total <= best.total <= 99


def test_email_dominates_an_otherwise_identical_channel():
    with_mail = score_channel(
        subscribers=50_000, uploads_per_month=4, days_since_last_upload=10, has_email=True
    )
    without = score_channel(
        subscribers=50_000, uploads_per_month=4, days_since_last_upload=10, has_email=False
    )
    assert with_mail.total - without.total == 21


def test_mega_channel_scores_below_mid_channel():
    """The whole point of the score: 2M subs is a worse lead than 80k."""
    mid = score_channel(
        subscribers=80_000, uploads_per_month=6, days_since_last_upload=5, has_email=True
    )
    mega = score_channel(
        subscribers=2_000_000, uploads_per_month=6, days_since_last_upload=5, has_email=True
    )
    assert mid.total > mega.total


def test_unknown_recency_is_not_treated_as_dead():
    unknown = score_channel(
        subscribers=50_000, uploads_per_month=4, days_since_last_upload=None, has_email=True
    )
    dead = score_channel(
        subscribers=50_000, uploads_per_month=4, days_since_last_upload=400, has_email=True
    )
    assert unknown.total > dead.total


# ------------------------------------------------------------------- emails
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Contato: parcerias@canal.com.br", "parcerias@canal.com.br"),
        ("business inquiries -> hello@studio.tv.", "hello@studio.tv"),
        ("Sem contato aqui", None),
        ("no-reply@youtube.com only", None),
        ("test@example.com", None),
        ("", None),
    ],
)
def test_extract_email(text, expected):
    assert extract_email(text) == expected


def test_email_never_invented():
    """A channel with no address must report None, not a guessed pattern."""
    channel = Channel(
        id="x", title="Canal", handle="@canal", description="Inscreva-se!",
        subscribers=1000, subscribers_hidden=False, video_count=10, view_count=1,
        country="BR", published_at=None, thumbnail=None, uploads_playlist=None,
        email=extract_email("Inscreva-se!"),
    )
    assert channel.email is None


# -------------------------------------------------------------------- quota
def test_estimate_matches_documented_costs():
    """One niche, two pages, no enrichment: 2 searches + 2 hydrations."""
    units = estimate_search_cost(niches=1, pages=2, enrich_last_upload=False)
    assert units == 2 * COST_SEARCH_LIST + 2 * COST_CHANNELS_LIST


def test_deep_mode_costs_more_than_normal():
    normal = estimate_search_cost(niches=2, pages=2, enrich_last_upload=True)
    deep = estimate_search_cost(niches=2, pages=5, enrich_last_upload=True)
    assert deep > normal * 2


def test_keyring_rotates_to_the_key_with_most_quota():
    ring = InMemoryKeyring()
    a = ring.add("A" * 30, "first")
    b = ring.add("B" * 30, "second")
    ring.charge(a, 9_500)
    assert ring.acquire(100) is b


def test_keyring_raises_when_every_key_is_spent():
    ring = InMemoryKeyring()
    k = ring.add("A" * 30)
    ring.charge(k, DAILY_UNITS_PER_KEY)
    with pytest.raises(QuotaExhausted):
        ring.acquire(1)


def test_disabled_key_reports_no_remaining_quota():
    ring = InMemoryKeyring()
    k = ring.add("A" * 30)
    ring.disable(k, "invalid")
    assert k.remaining == 0
    assert ring.total_remaining() == 0


# ------------------------------------------------------------------ filters
def test_subscriber_range_must_be_coherent():
    with pytest.raises(ValueError):
        SearchFilters(niches=["edição"], min_subscribers=500_000, max_subscribers=1_000)


def test_niches_are_capped_at_three():
    with pytest.raises(ValueError):
        SearchFilters(niches=["a", "b", "c", "d"])


def test_blank_niches_are_rejected():
    with pytest.raises(ValueError):
        SearchFilters(niches=["   "])


def test_unsupported_country_is_rejected():
    with pytest.raises(ValueError):
        SearchFilters(niches=["edição"], country="JP")


def test_activity_any_skips_enrichment_cost():
    """Choosing 'any activity' should not pay for recency data."""
    assert SearchFilters(niches=["x"], activity_days=0).enrich_last_upload is False
    assert SearchFilters(niches=["x"], activity_days=90).enrich_last_upload is True


# ----------------------------------------------------------------- channels
def test_uploads_per_month_uses_channel_lifetime():
    started = datetime.now(timezone.utc) - timedelta(days=365)
    channel = Channel(
        id="x", title="C", handle=None, description="", subscribers=1,
        subscribers_hidden=False, video_count=120, view_count=0, country="BR",
        published_at=started, thumbnail=None, uploads_playlist=None,
    )
    assert 9.0 < channel.uploads_per_month < 11.0


def test_days_since_last_upload_is_none_without_data():
    channel = Channel(
        id="x", title="C", handle=None, description="", subscribers=1,
        subscribers_hidden=False, video_count=1, view_count=0, country="BR",
        published_at=None, thumbnail=None, uploads_playlist=None,
    )
    assert channel.days_since_last_upload is None
