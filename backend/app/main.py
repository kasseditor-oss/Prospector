"""Prospector API.

Serves the Next.js frontend. The one job that cannot move to the browser is
holding the YouTube API key: keeping it here means it never ships to a client
where anyone can read it out of the network tab.
"""

from __future__ import annotations

import os

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .keyring import (
    DAILY_UNITS_PER_KEY,
    InMemoryKeyring,
    QuotaExhausted,
    current_quota_day,
    estimate_search_cost,
)
from .schemas import (
    ChannelOut,
    EstimateResponse,
    KeyIn,
    KeyOut,
    QuotaOut,
    ScoreDetail,
    SearchFilters,
    SearchResponse,
)
from .scoring import score_channel
from .sessions import SESSION_COOKIE
from .store import build_store
from .youtube import Channel, YouTubeClient, YouTubeError

app = FastAPI(title="Prospector API", version="0.1.0")

# In development the frontend sits on another port; in production it sits on
# another host. Both come from the environment so a deploy never needs a code
# change — and so a wildcard can never sneak in, which would be unsafe here:
# credentials are allowed, and the session cookie is what guards each key pool.
_DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("PROSPECTOR_ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if origin.strip() and origin.strip() != "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

store = build_store()

# Cookies must be Secure in production; over plain http on localhost a Secure
# cookie is dropped by the browser, which would silently break development.
_SECURE_COOKIES = os.getenv("PROSPECTOR_ENV", "development") == "production"


def session_keyring(request: Request, response: Response):
    """The key pool belonging to this visitor.

    Reads the pool once here and writes it back once after the response. That
    ordering is a cost decision as much as a correctness one: a deep search
    charges quota over 500 times, and persisting each charge separately would
    burn a day of Firestore's free write budget in under 40 searches.
    """
    session_id, keyring = store.load(request.cookies.get(SESSION_COOKIE))
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=8 * 60 * 60,
        httponly=True,   # unreadable from JavaScript
        samesite="lax",
        secure=_SECURE_COOKIES,
        path="/",
    )
    try:
        yield keyring
    finally:
        store.save(session_id, keyring)


def _key_out(state) -> KeyOut:
    return KeyOut(
        label=state.label,
        masked=state.masked(),
        used=state.used,
        remaining=state.remaining,
        disabled_reason=state.disabled_reason,
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "quota_day": current_quota_day()}


# --------------------------------------------------------------------- keys
@app.get("/api/keys", response_model=list[KeyOut])
async def list_keys(
    keyring: InMemoryKeyring = Depends(session_keyring),
) -> list[KeyOut]:
    return [_key_out(k) for k in keyring.all()]


@app.post("/api/keys", response_model=KeyOut, status_code=201)
async def add_key(
    payload: KeyIn, keyring: InMemoryKeyring = Depends(session_keyring)
) -> KeyOut:
    state = keyring.add(payload.key.strip(), payload.label)
    return _key_out(state)


@app.delete("/api/keys/{masked_suffix}", status_code=204)
async def remove_key(
    masked_suffix: str, keyring: InMemoryKeyring = Depends(session_keyring)
) -> None:
    """Delete by the last 4 characters, so the full key never rides in a URL."""
    for state in keyring.all():
        if state.key.endswith(masked_suffix):
            keyring.remove(state.key)
            return
    raise HTTPException(status_code=404, detail="Key not found.")


@app.get("/api/quota", response_model=QuotaOut)
async def quota(keyring: InMemoryKeyring = Depends(session_keyring)) -> QuotaOut:
    keys = keyring.all()
    return QuotaOut(
        keys=len(keys),
        units_remaining=keyring.total_remaining(),
        units_total=len(keys) * DAILY_UNITS_PER_KEY,
        quota_day=current_quota_day(),
    )


# ------------------------------------------------------------------- search
@app.post("/api/search/estimate", response_model=EstimateResponse)
async def estimate(
    filters: SearchFilters, keyring: InMemoryKeyring = Depends(session_keyring)
) -> EstimateResponse:
    """What this search will cost, before committing to it."""
    units = estimate_search_cost(
        niches=len(filters.niches),
        pages=filters.pages,
        enrich_last_upload=filters.enrich_last_upload,
    )
    remaining = keyring.total_remaining()
    return EstimateResponse(
        units=units, units_remaining=remaining, affordable=units <= remaining
    )


def _to_out(channel: Channel, niche: str) -> ChannelOut:
    breakdown = score_channel(
        subscribers=channel.subscribers,
        uploads_per_month=channel.uploads_per_month,
        days_since_last_upload=channel.days_since_last_upload,
        has_email=bool(channel.email),
    )
    handle = channel.handle
    url = (
        f"https://www.youtube.com/{handle}"
        if handle and handle.startswith("@")
        else f"https://www.youtube.com/channel/{channel.id}"
    )
    return ChannelOut(
        id=channel.id,
        title=channel.title,
        handle=handle,
        url=url,
        subscribers=channel.subscribers,
        subscribers_hidden=channel.subscribers_hidden,
        video_count=channel.video_count,
        country=channel.country,
        thumbnail=channel.thumbnail,
        email=channel.email,
        uploads_per_month=round(channel.uploads_per_month, 2),
        cadence=channel.cadence,
        cadence_trend=round(channel.cadence_trend, 2),
        days_since_last_upload=channel.days_since_last_upload,
        last_upload_at=channel.last_upload_at,
        niche=niche,
        score=ScoreDetail(
            total=breakdown.total,
            reachability=breakdown.reachability,
            rhythm=breakdown.rhythm,
            recency=breakdown.recency,
            fit=breakdown.fit,
        ),
    )


@app.post("/api/search", response_model=SearchResponse)
async def search(
    filters: SearchFilters, keyring: InMemoryKeyring = Depends(session_keyring)
) -> SearchResponse:
    if not keyring.all():
        raise HTTPException(
            status_code=428,
            detail="Add a YouTube API key before searching.",
        )

    client_api = YouTubeClient(keyring)
    seen: dict[str, str] = {}  # channel id -> the niche that surfaced it
    examined = 0

    try:
        async with httpx.AsyncClient() as http:
            for niche in filters.niches:
                ids = await client_api.search_channel_ids(
                    http,
                    query=niche,
                    region_code=filters.country,
                    relevance_language=filters.language,
                    pages=filters.pages,
                )
                for cid in ids:
                    seen.setdefault(cid, niche)

            channels = await client_api.hydrate_channels(http, list(seen))
            examined = len(channels)

            # Cut on the cheap criteria first, so recency enrichment is only
            # ever paid for on channels that already passed everything else.
            kept = [
                c
                for c in channels
                if filters.min_subscribers <= c.subscribers <= filters.max_subscribers
                and not (filters.email_only and not c.email)
            ]

            if filters.enrich_last_upload:
                await client_api.enrich_upload_history(http, kept)
                kept = [
                    c
                    for c in kept
                    if c.days_since_last_upload is None
                    or c.days_since_last_upload <= filters.activity_days
                ]
    except QuotaExhausted as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except YouTubeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    out = [_to_out(c, seen.get(c.id, filters.niches[0])) for c in kept]
    out.sort(key=lambda c: c.score.total, reverse=True)

    return SearchResponse(
        channels=out,
        units_spent=client_api.units_spent,
        units_remaining=keyring.total_remaining(),
        examined=examined,
        filtered_out=examined - len(out),
    )
