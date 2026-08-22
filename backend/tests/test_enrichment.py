"""History enrichment runs concurrently.

A deep search keeps up to 500 channels, and each needs its own
playlistItems.list call. In sequence that is two minutes of pure latency wait —
which is both a bad answer time and, on any host that meters wall time, a much
larger compute bill for identical YouTube quota.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.keyring import InMemoryKeyring
from app.youtube import Channel, YouTubeClient

LATENCY = 0.05  # seconds per simulated API call
CHANNELS = 40


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeClient:
    """Stands in for httpx.AsyncClient, with a fixed round-trip delay."""

    def __init__(self) -> None:
        self.calls = 0
        self.peak_in_flight = 0
        self._in_flight = 0

    async def get(self, url, params=None, timeout=None):
        self.calls += 1
        self._in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
        try:
            await asyncio.sleep(LATENCY)
        finally:
            self._in_flight -= 1

        now = datetime.now(timezone.utc)
        items = [
            {"snippet": {"publishedAt": (now - timedelta(days=30 * i)).isoformat()}}
            for i in range(6)
        ]
        return FakeResponse({"items": items})


def _channels(n: int) -> list[Channel]:
    return [
        Channel(
            id=f"c{i}", title=f"Canal {i}", handle=None, description="",
            subscribers=10_000, subscribers_hidden=False, video_count=50,
            view_count=0, country="BR", published_at=None, thumbnail=None,
            uploads_playlist=f"UU_{i}",
        )
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_enrichment_is_concurrent_not_sequential():
    ring = InMemoryKeyring()
    ring.add("A" * 30, "test")
    client_api = YouTubeClient(ring)
    channels = _channels(CHANNELS)
    http = FakeClient()

    started = time.perf_counter()
    await client_api.enrich_upload_history(http, channels)
    elapsed = time.perf_counter() - started

    sequential = CHANNELS * LATENCY
    assert http.calls == CHANNELS
    # Comfortably faster than one-at-a-time, without asserting an exact factor.
    assert elapsed < sequential / 3, (
        f"took {elapsed:.2f}s; sequential would be {sequential:.2f}s"
    )


@pytest.mark.asyncio
async def test_concurrency_stays_bounded():
    """Unbounded fan-out would earn rate limits, so the semaphore must hold."""
    from app.youtube import _ENRICH_CONCURRENCY

    ring = InMemoryKeyring()
    ring.add("A" * 30, "test")
    http = FakeClient()
    await YouTubeClient(ring).enrich_upload_history(http, _channels(CHANNELS))

    assert http.peak_in_flight <= _ENRICH_CONCURRENCY


@pytest.mark.asyncio
async def test_every_channel_gets_its_history():
    ring = InMemoryKeyring()
    ring.add("A" * 30, "test")
    channels = _channels(12)
    await YouTubeClient(ring).enrich_upload_history(FakeClient(), channels)

    assert all(c.cadence for c in channels)
    assert all(c.last_upload_at is not None for c in channels)


@pytest.mark.asyncio
async def test_quota_is_charged_once_per_channel():
    """Concurrency must not double-charge or skip units."""
    ring = InMemoryKeyring()
    key = ring.add("A" * 30, "test")
    client_api = YouTubeClient(ring)
    await client_api.enrich_upload_history(FakeClient(), _channels(25))

    assert client_api.units_spent == 25
    assert key.used == 25


@pytest.mark.asyncio
async def test_channels_without_an_uploads_playlist_are_skipped():
    ring = InMemoryKeyring()
    ring.add("A" * 30, "test")
    channels = _channels(5)
    channels[0].uploads_playlist = None
    channels[3].uploads_playlist = None

    http = FakeClient()
    await YouTubeClient(ring).enrich_upload_history(http, channels)

    assert http.calls == 3
    assert channels[0].cadence == []
    assert channels[1].cadence != []
