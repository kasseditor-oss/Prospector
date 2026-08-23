"""YouTube Data API v3 client.

Only three endpoints are needed to prospect channels, and each is charged
differently, so the call pattern below is shaped around cost rather than
convenience:

    search.list        100 units   find candidate channels for a niche
    channels.list        1 unit    hydrate up to 50 channels in one call
    playlistItems.list   1 unit    per channel, newest upload date

Every request goes through :meth:`YouTubeClient._get`, which charges the
keyring before spending and rotates keys when one is exhausted.

A note on emails, because it is the most misunderstood part of this product:
the API does **not** expose the "Email" button shown on a channel's About tab —
that address sits behind a captcha and is not a field in any API response. What
is available is the channel description, where a large share of creators paste
a business contact themselves. We extract from that, and only that. If no
address is present we report ``None`` rather than guessing a pattern like
``contact@<channelname>.com``, which would produce plausible-looking addresses
that bounce and damage the sender's domain reputation.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import httpx

from .socials import Social, extract_socials, merge_from_videos
from .keyring import (
    COST_CHANNELS_LIST,
    COST_PLAYLIST_ITEMS_LIST,
    COST_SEARCH_LIST,
    InMemoryKeyring,
    QuotaExhausted,
)

API_ROOT = "https://www.googleapis.com/youtube/v3"

# How many history requests to keep in flight. Eight is comfortably inside
# YouTube's per-key rate limits while removing almost all of the latency wait;
# raising it further mostly buys 429s.
_ENRICH_CONCURRENCY = 8

# Deliberately conservative: no unicode local parts, no trailing punctuation.
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}"
)

# Addresses that appear in descriptions but are never the creator's contact.
_EMAIL_DENYLIST = re.compile(
    r"(?:^|@)(?:example\.|test\.|no-?reply|donotreply|sentry\.io|youtube\.com)",
    re.IGNORECASE,
)


class YouTubeError(RuntimeError):
    """The API rejected a request for a reason the caller should see."""


@dataclass
class Channel:
    id: str
    title: str
    handle: str | None
    description: str
    subscribers: int
    subscribers_hidden: bool
    video_count: int
    view_count: int
    country: str | None
    published_at: datetime | None
    thumbnail: str | None
    uploads_playlist: str | None
    email: str | None = None
    last_upload_at: datetime | None = None

    #: Other networks the channel published in its description.
    socials: list[Social] = field(default_factory=list)

    #: Uploads per calendar month for the last 12 months, oldest first.
    #: Empty until :meth:`YouTubeClient.enrich_upload_history` has run.
    cadence: list[int] = field(default_factory=list)

    @property
    def days_since_last_upload(self) -> int | None:
        if self.last_upload_at is None:
            return None
        delta = datetime.now(timezone.utc) - self.last_upload_at
        return max(0, delta.days)

    @property
    def lifetime_uploads_per_month(self) -> float:
        """Upload rate averaged over the channel's whole life."""
        if not self.published_at or not self.video_count:
            return 0.0
        months = max(1.0, (datetime.now(timezone.utc) - self.published_at).days / 30.44)
        return self.video_count / months

    @property
    def uploads_per_month(self) -> float:
        """Current upload rate.

        Prefers the measured last-12-months cadence over the lifetime average.
        A channel that published weekly for five years and stopped six months
        ago still shows a healthy lifetime average — which is exactly the lead
        an editor should not waste a pitch on.
        """
        if self.cadence:
            months = len(self.cadence)
            return sum(self.cadence) / months if months else 0.0
        return self.lifetime_uploads_per_month

    @property
    def cadence_trend(self) -> float:
        """Ratio of the last quarter's rate to the preceding three quarters.

        Above 1.0 the channel is accelerating — the moment it starts feeling
        the editing load. Returns 0.0 when there is not enough history.
        """
        if len(self.cadence) < 12:
            return 0.0
        recent = sum(self.cadence[-3:]) / 3
        earlier = sum(self.cadence[:-3]) / 9
        if earlier == 0:
            return 2.0 if recent > 0 else 0.0
        return recent / earlier


def extract_email(description: str) -> str | None:
    """First plausible contact address in a channel description, or None."""
    for match in _EMAIL_RE.finditer(description or ""):
        candidate = match.group(0).rstrip(".,;:")
        if _EMAIL_DENYLIST.search(candidate):
            continue
        return candidate
    return None


def monthly_cadence(
    dates: Sequence[datetime], *, months: int = 12, now: datetime | None = None
) -> list[int]:
    """Uploads per calendar month over the trailing window, oldest first.

    The last element is always the current (partial) month, so the strip a
    reader sees always ends at today rather than at the channel's last upload.
    """
    reference = now or datetime.now(timezone.utc)
    buckets = [0] * months

    def month_index(dt: datetime) -> int:
        """0 = oldest month in the window, months - 1 = current month."""
        delta = (reference.year - dt.year) * 12 + (reference.month - dt.month)
        return months - 1 - delta

    for dt in dates:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        index = month_index(dt)
        if 0 <= index < months:
            buckets[index] += 1
    return buckets


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _chunk(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class YouTubeClient:
    def __init__(self, keyring: InMemoryKeyring, *, timeout: float = 20.0) -> None:
        self._keyring = keyring
        self._timeout = timeout
        self.units_spent = 0

    async def _get(
        self, client: httpx.AsyncClient, endpoint: str, params: dict[str, Any], cost: int
    ) -> dict[str, Any]:
        """One billed request, with key rotation on quota errors."""
        attempts = 0
        while True:
            attempts += 1
            key_state = self._keyring.acquire(cost)
            self._keyring.charge(key_state, cost)
            self.units_spent += cost

            response = await client.get(
                f"{API_ROOT}/{endpoint}",
                params={**params, "key": key_state.key},
                timeout=self._timeout,
            )
            if response.status_code == 200:
                return response.json()

            payload: dict[str, Any] = {}
            try:
                payload = response.json()
            except ValueError:
                pass
            reason = ""
            errors = payload.get("error", {}).get("errors") or []
            if errors:
                reason = errors[0].get("reason", "")

            if reason in {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
                # This key is done for the day; mark it and let the loop pick another.
                self._keyring.disable(key_state, "quota")
                if attempts < 5:
                    continue
                raise QuotaExhausted("All keys hit their daily quota.")

            if reason in {"keyInvalid", "badRequest"} or response.status_code == 400:
                self._keyring.disable(key_state, "invalid")
                if attempts < 5:
                    continue

            message = payload.get("error", {}).get("message") or response.text[:200]
            raise YouTubeError(f"YouTube API {response.status_code}: {message}")

    async def search_channel_ids(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        region_code: str | None,
        relevance_language: str | None,
        pages: int,
    ) -> list[str]:
        """Candidate channel ids for one niche query."""
        ids: list[str] = []
        page_token: str | None = None
        for _ in range(max(1, pages)):
            params: dict[str, Any] = {
                "part": "snippet",
                "type": "channel",
                "q": query,
                "maxResults": 50,
                "order": "relevance",
            }
            if region_code:
                params["regionCode"] = region_code
            if relevance_language:
                params["relevanceLanguage"] = relevance_language
            if page_token:
                params["pageToken"] = page_token

            data = await self._get(client, "search", params, COST_SEARCH_LIST)
            for item in data.get("items", []):
                cid = (item.get("id") or {}).get("channelId")
                if cid and cid not in ids:
                    ids.append(cid)

            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return ids

    async def hydrate_channels(
        self, client: httpx.AsyncClient, channel_ids: Sequence[str]
    ) -> list[Channel]:
        """Full channel records, 50 per billed unit."""
        out: list[Channel] = []
        for batch in _chunk(list(channel_ids), 50):
            data = await self._get(
                client,
                "channels",
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(batch),
                    "maxResults": 50,
                },
                COST_CHANNELS_LIST,
            )
            for item in data.get("items", []):
                snippet = item.get("snippet") or {}
                stats = item.get("statistics") or {}
                content = item.get("contentDetails") or {}
                thumbs = snippet.get("thumbnails") or {}
                description = snippet.get("description") or ""

                out.append(
                    Channel(
                        id=item.get("id", ""),
                        title=snippet.get("title") or "",
                        handle=(snippet.get("customUrl") or None),
                        description=description,
                        subscribers=int(stats.get("subscriberCount") or 0),
                        subscribers_hidden=bool(stats.get("hiddenSubscriberCount")),
                        video_count=int(stats.get("videoCount") or 0),
                        view_count=int(stats.get("viewCount") or 0),
                        country=snippet.get("country"),
                        published_at=_parse_dt(snippet.get("publishedAt")),
                        thumbnail=(thumbs.get("default") or {}).get("url"),
                        uploads_playlist=(
                            (content.get("relatedPlaylists") or {}).get("uploads")
                        ),
                        email=extract_email(description),
                        socials=extract_socials(description),
                    )
                )
        return out

    async def enrich_upload_history(
        self, client: httpx.AsyncClient, channels: Sequence[Channel]
    ) -> None:
        """Fill ``last_upload_at`` and ``cadence`` in place.

        Costs 1 unit per channel — the same as asking for a single item, because
        playlistItems.list is billed per call and part, not per result. Asking
        for 50 therefore buys a year of publishing history for free, which is
        what makes the cadence strip possible without raising the quota bill.

        Runs the calls concurrently. This is one request per channel and a deep
        search can keep 500 of them, so doing it in sequence meant two minutes
        of waiting on latency. The quota cost is identical either way — units
        are charged per call, not per second — so the only thing serialising
        bought was a slower answer and a much larger compute bill on any host
        that meters wall time.
        """
        semaphore = asyncio.Semaphore(_ENRICH_CONCURRENCY)

        async def one(channel: Channel) -> None:
            if not channel.uploads_playlist:
                return
            async with semaphore:
                try:
                    data = await self._get(
                        client,
                        "playlistItems",
                        {
                            "part": "snippet",
                            "playlistId": channel.uploads_playlist,
                            "maxResults": 50,
                        },
                        COST_PLAYLIST_ITEMS_LIST,
                    )
                except (YouTubeError, QuotaExhausted):
                    # History is an enrichment, never a reason to fail the search.
                    return
            self._apply_history(channel, data)

        await asyncio.gather(*(one(channel) for channel in channels))

    @staticmethod
    def _apply_history(channel: Channel, data: dict[str, Any]) -> None:
        """Fold one playlistItems response into a channel's cadence."""
        dates = [
            dt
            for dt in (
                _parse_dt((item.get("snippet") or {}).get("publishedAt"))
                for item in data.get("items") or []
            )
            if dt is not None
        ]
        # Video descriptions ride along with the history we already paid for,
        # and they are where most creators actually keep their links.
        descriptions = [
            (item.get("snippet") or {}).get("description") or ""
            for item in data.get("items") or []
        ]
        if descriptions:
            channel.socials = merge_from_videos(channel.socials, descriptions)

        if not dates:
            return
        channel.last_upload_at = max(dates)

        # 50 is the page limit. If a channel published 50 videos inside the
        # window, everything older is invisible to us — reporting those months
        # as zero would draw a channel that is merely prolific as one that just
        # woke up. Narrow the window to what we can actually see.
        now = datetime.now(timezone.utc)
        oldest = min(dates)
        months_seen = (now.year - oldest.year) * 12 + (now.month - oldest.month) + 1
        window = 12 if len(dates) < 50 else min(12, months_seen)
        channel.cadence = monthly_cadence(dates, months=max(1, window), now=now)
