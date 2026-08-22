"""Upload cadence — the data behind the strip shown on every lead row.

The strip is the one thing an editor reads to decide whether a channel is
worth a pitch, so wrong numbers here are worse than no numbers at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.youtube import Channel, monthly_cadence

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def _channel(**overrides) -> Channel:
    base = dict(
        id="x", title="C", handle=None, description="", subscribers=50_000,
        subscribers_hidden=False, video_count=120, view_count=0, country="BR",
        published_at=NOW - timedelta(days=365), thumbnail=None,
        uploads_playlist="UU_x",
    )
    base.update(overrides)
    return Channel(**base)


# ------------------------------------------------------------------ bucketing
def test_window_length_matches_request():
    assert len(monthly_cadence([], now=NOW)) == 12
    assert len(monthly_cadence([], months=6, now=NOW)) == 6


def test_current_month_is_the_last_bucket():
    cadence = monthly_cadence([NOW - timedelta(days=1)], now=NOW)
    assert cadence[-1] == 1
    assert sum(cadence) == 1


def test_uploads_land_in_their_own_month():
    dates = [
        NOW,                                        # august, current
        datetime(2026, 7, 5, tzinfo=timezone.utc),  # july
        datetime(2026, 7, 20, tzinfo=timezone.utc), # july
    ]
    cadence = monthly_cadence(dates, now=NOW)
    assert cadence[-1] == 1
    assert cadence[-2] == 2


def test_uploads_older_than_the_window_are_dropped():
    old = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert sum(monthly_cadence([old], now=NOW)) == 0


def test_naive_datetimes_are_treated_as_utc():
    naive = datetime(2026, 8, 1)  # no tzinfo
    assert sum(monthly_cadence([naive], now=NOW)) == 1


# ------------------------------------------------------------------ the rate
def test_measured_cadence_beats_the_lifetime_average():
    """A channel that stopped six months ago must not look active."""
    dormant = _channel(video_count=600, published_at=NOW - timedelta(days=1825))
    assert dormant.lifetime_uploads_per_month > 9  # looks prolific

    dormant.cadence = [10, 10, 10, 10, 10, 10, 0, 0, 0, 0, 0, 0]
    assert dormant.uploads_per_month == 5.0  # measured, and falling


def test_rate_falls_back_to_lifetime_without_history():
    channel = _channel(video_count=120, published_at=NOW - timedelta(days=365))
    assert channel.cadence == []
    assert 9.0 < channel.uploads_per_month < 11.0


# ----------------------------------------------------------------- the trend
def test_trend_detects_acceleration():
    channel = _channel()
    channel.cadence = [1, 1, 1, 1, 1, 1, 1, 1, 1, 4, 4, 4]
    assert channel.cadence_trend == 4.0


def test_trend_detects_a_channel_going_quiet():
    channel = _channel()
    channel.cadence = [4, 4, 4, 4, 4, 4, 4, 4, 4, 1, 1, 1]
    assert channel.cadence_trend == 0.25


def test_trend_is_unknown_without_a_full_year():
    channel = _channel()
    channel.cadence = [3, 3, 3]  # truncated window
    assert channel.cadence_trend == 0.0


def test_trend_handles_a_channel_that_just_started():
    channel = _channel()
    channel.cadence = [0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 3, 2]
    assert channel.cadence_trend == 2.0  # capped, not a division by zero


# ------------------------------------------------------------------ truncation
def test_a_prolific_channel_is_not_misread_as_newly_awake():
    """50 uploads is one page. If they all fall inside three months, the nine
    months we cannot see must not be drawn as silence."""
    dates = [NOW - timedelta(days=d) for d in range(0, 90, 2)]
    assert len(dates) == 45  # spanning may through august, four calendar months

    full = monthly_cadence(dates, months=12, now=NOW)
    assert full[:8] == [0] * 8  # the misleading picture: eight months of silence
    assert all(count > 0 for count in full[8:])

    narrowed = monthly_cadence(dates, months=4, now=NOW)
    assert len(narrowed) == 4
    assert sum(narrowed) == 45
    assert all(count > 0 for count in narrowed)
