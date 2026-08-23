"""Prospector API.

Serves the Next.js frontend. The one job that cannot move to the browser is
holding the YouTube API key: keeping it here means it never ships to a client
where anyone can read it out of the network tab.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
from fastapi.staticfiles import StaticFiles
from fastapi import Depends, FastAPI, HTTPException

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
    LeadOut,
    LeadsResponse,
    SearchResponse,
    SocialOut,
)
from .leads import LeadStore
from .scoring import score_channel
from .store import build_store
from .youtube import Channel, YouTubeClient, YouTubeError

app = FastAPI(title="Prospector API", version="0.1.0")

# The lead base outlives the process on purpose: a search costs quota, so its
# results belong on disk, not in memory.
leads = LeadStore()

store = build_store()


def active_keyring():
    """The key pool, read once per request and written back once after it.

    That ordering is a cost decision as much as a correctness one: a deep
    search charges quota over 500 times, and persisting each charge separately
    would mean hundreds of disk writes for a single search.
    """
    keyring = store.keyring()
    try:
        yield keyring
    finally:
        store.flush()


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
    keyring: InMemoryKeyring = Depends(active_keyring),
) -> list[KeyOut]:
    return [_key_out(k) for k in keyring.all()]


@app.post("/api/keys", response_model=KeyOut, status_code=201)
async def add_key(
    payload: KeyIn, keyring: InMemoryKeyring = Depends(active_keyring)
) -> KeyOut:
    state = keyring.add(payload.key.strip(), payload.label)
    return _key_out(state)


@app.delete("/api/keys/{masked_suffix}", status_code=204)
async def remove_key(
    masked_suffix: str, keyring: InMemoryKeyring = Depends(active_keyring)
) -> None:
    """Delete by the last 4 characters, so the full key never rides in a URL."""
    for state in keyring.all():
        if state.key.endswith(masked_suffix):
            keyring.remove(state.key)
            return
    raise HTTPException(status_code=404, detail="Chave não encontrada.")


def _describe_storage() -> str:
    """What actually happens to a key, so the UI never overpromises."""
    describe = getattr(store, "describe", None)
    if describe is None:
        return "não são salvas (some ao fechar o programa)"
    return f"salvas neste PC — {describe()}"


@app.get("/api/quota", response_model=QuotaOut)
async def quota(keyring: InMemoryKeyring = Depends(active_keyring)) -> QuotaOut:
    keys = keyring.all()
    return QuotaOut(
        keys=len(keys),
        units_remaining=keyring.total_remaining(),
        units_total=len(keys) * DAILY_UNITS_PER_KEY,
        quota_day=current_quota_day(),
        key_storage=_describe_storage(),
    )


# ------------------------------------------------------------------- search
@app.post("/api/search/estimate", response_model=EstimateResponse)
async def estimate(
    filters: SearchFilters, keyring: InMemoryKeyring = Depends(active_keyring)
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
        socials=[
            SocialOut(network=s.network, handle=s.handle, url=s.url)
            for s in channel.socials
        ],
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
    filters: SearchFilters, keyring: InMemoryKeyring = Depends(active_keyring)
) -> SearchResponse:
    if not keyring.all():
        raise HTTPException(
            status_code=428,
            detail=(
                "Nenhuma chave cadastrada. Adicione a sua chave da API do "
                "YouTube para buscar."
            ),
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

    # Persist before answering. SQLite writes are quick but they are still
    # blocking file I/O, so they run off the event loop.
    payload = [c.model_dump() for c in out]
    new_count, updated = await asyncio.to_thread(leads.save_many, payload)
    total_saved = await asyncio.to_thread(leads.count)

    return SearchResponse(
        channels=out,
        units_spent=client_api.units_spent,
        units_remaining=keyring.total_remaining(),
        examined=examined,
        filtered_out=examined - len(out),
        saved_new=new_count,
        saved_updated=updated,
        total_saved=total_saved,
    )


@app.get("/api/leads", response_model=LeadsResponse)
async def list_leads(
    q: str = "",
    sort: str = "first_seen",
    limit: int = 500,
    offset: int = 0,
    with_email: bool = False,
) -> LeadsResponse:
    """The accumulated base. Independent of any single search."""
    rows, total = await asyncio.to_thread(
        leads.list, query=q, sort=sort, limit=limit, offset=offset, with_email=with_email
    )
    return LeadsResponse(leads=[LeadOut(**row) for row in rows], total=total)


@app.delete("/api/leads/{channel_id}", status_code=204)
async def delete_lead(channel_id: str) -> None:
    removed = await asyncio.to_thread(leads.delete, channel_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")


@app.delete("/api/leads", status_code=200)
async def clear_leads() -> dict[str, int]:
    """Empty the base. The UI asks for confirmation before calling this."""
    removed = await asyncio.to_thread(leads.clear)
    return {"removed": removed}


# --------------------------------------------------------------- desktop web
# In the desktop build there is no Node process: FastAPI serves the exported
# pages and the API from the same origin. That removes the proxy, CORS and the
# third-party-cookie problem in one move, because there is only one origin.
#
# Mounted last on purpose. Starlette matches routes in registration order, so
# every /api route above is found before this catch-all sees the request.
def _frontend_dir() -> Path | None:
    candidates = [
        # Packaged by PyInstaller: the export is bundled next to the code.
        Path(getattr(sys, "_MEIPASS", "")) / "web",
        # Running from the repo.
        Path(__file__).resolve().parent.parent.parent / "frontend" / "out",
    ]
    for path in candidates:
        if path.is_dir() and (path / "index.html").is_file():
            return path
    return None


_WEB = _frontend_dir()
if _WEB is not None:
    app.mount("/", StaticFiles(directory=_WEB, html=True), name="web")
