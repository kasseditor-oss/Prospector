"""Prospector API.

Serves the Next.js frontend. The one job that cannot move to the browser is
holding the YouTube API key: keeping it here means it never ships to a client
where anyone can read it out of the network tab.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
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
    StatusIn,
    EstimateResponse,
    KeyIn,
    KeyOut,
    QuotaOut,
    ScoreDetail,
    SearchFilters,
    LeadOut,
    LeadsResponse,
    MailAccountIn,
    MailSendIn,
    MailSentOut,
    MailStateOut,
    MailTemplateIn,
    PostOut,
    PostsResponse,
    SearchResponse,
    SocialOut,
    TokenIn,
    TokenOut,
    XSearchFilters,
    XSearchResponse,
)
from .leads import LeadStore
from .localonly import LocalOnly
from . import mailer
from .posts import PostStore, hours_old
from .scoring import score_channel
from .status import STATUSES, is_valid
from .xsearch import DEFAULT_TERMS, XClient, XSearchError, account_credit
from .store import SecretStore, build_store, masked
from .xsearch import DEFAULT_ACTOR
from .youtube import Channel, YouTubeClient, YouTubeError

app = FastAPI(title="Prospector API", version="0.1.0")

# Answer only to this machine's own name. The port is local, but a web page
# can still make the browser aim at it under a borrowed hostname — see
# app.localonly for the attack this turns away.
app.add_middleware(LocalOnly)

# The lead base outlives the process on purpose: a search costs quota, so its
# results belong on disk, not in memory.
leads = LeadStore()

# The second base, kept apart from the first. See app.posts for why.
posts = PostStore()

# The Apify token, in the same vault as the YouTube keys.
secrets = SecretStore()

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


@app.get("/api/statuses")
async def statuses() -> dict[str, str]:
    """The funnel, named. Read by both bases so the words live in one place."""
    return dict(STATUSES)


@app.patch("/api/leads/{channel_id}/status", status_code=204)
async def set_lead_status(channel_id: str, payload: StatusIn) -> None:
    if not is_valid(payload.status):
        raise HTTPException(status_code=422, detail="Status desconhecido.")
    moved = await asyncio.to_thread(leads.set_status, channel_id, payload.status)
    if not moved:
        raise HTTPException(status_code=404, detail="Canal não encontrado na base.")


@app.patch("/api/posts/{post_id}/status", status_code=204)
async def set_post_status(post_id: str, payload: StatusIn) -> None:
    if not is_valid(payload.status):
        raise HTTPException(status_code=422, detail="Status desconhecido.")
    moved = await asyncio.to_thread(posts.set_status, post_id, payload.status)
    if not moved:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")


@app.get("/api/leads", response_model=LeadsResponse)
async def list_leads(
    q: str = "",
    sort: str = "first_seen",
    limit: int = 500,
    offset: int = 0,
    with_email: bool = False,
    status: str = "",
) -> LeadsResponse:
    """The accumulated base. Independent of any single search."""
    rows, total = await asyncio.to_thread(
        leads.list,
        query=q,
        sort=sort,
        limit=limit,
        offset=offset,
        with_email=with_email,
        status=status,
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


# ==================================================================== e-mail
# Writing to the channels that published an address. Only the channel base has
# addresses at all: a hiring post on X carries a profile, not a mailbox.
MAIL_ACCOUNT_SETTING = "smtp"
MAIL_TEMPLATE_SETTING = "mail_template"


def _mail_account() -> mailer.MailAccount | None:
    return mailer.MailAccount.loads(secrets.get(MAIL_ACCOUNT_SETTING) or "null")


def _require_mail_account() -> mailer.MailAccount:
    account = _mail_account()
    if account is None:
        raise HTTPException(
            status_code=428,
            detail="Nenhuma conta de e-mail configurada. Configure a sua para enviar.",
        )
    return account


def _mail_template() -> tuple[str, str]:
    try:
        saved = json.loads(secrets.get(MAIL_TEMPLATE_SETTING) or "{}")
        subject, body = str(saved["subject"]), str(saved["body"])
        if subject.strip() and body.strip():
            return subject, body
    except (ValueError, KeyError, TypeError):
        pass
    return mailer.DEFAULT_SUBJECT, mailer.DEFAULT_BODY


def _sent_today() -> int:
    """Messages in the last 24 hours — a rolling window, not a calendar day.

    A calendar day would let forty go out at 23:50 and forty more at 00:10,
    which is exactly the burst the cap exists to prevent.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return leads.emailed_since(since.isoformat(timespec="seconds"))


async def _mail_state() -> MailStateOut:
    account = _mail_account()
    subject, body = _mail_template()
    if account is None:
        return MailStateOut(
            configured=False,
            subject=subject,
            body=body,
            placeholders=list(mailer.PLACEHOLDERS),
        )
    sent = await asyncio.to_thread(_sent_today)
    return MailStateOut(
        configured=True,
        user=account.user,
        host=account.host,
        port=account.port,
        from_name=account.from_name,
        daily_limit=account.daily_limit,
        sent_today=sent,
        remaining_today=max(0, account.daily_limit - sent),
        subject=subject,
        body=body,
        placeholders=list(mailer.PLACEHOLDERS),
    )


@app.get("/api/mail", response_model=MailStateOut)
async def read_mail() -> MailStateOut:
    return await _mail_state()


@app.post("/api/mail/account", response_model=MailStateOut)
async def save_mail_account(payload: MailAccountIn) -> MailStateOut:
    current = _mail_account()
    user = payload.user.strip()
    password = payload.password or (
        current.password if current and current.user == user else ""
    )
    if not password:
        raise HTTPException(status_code=422, detail="Informe a senha de app da conta.")

    host, port = payload.host.strip(), payload.port
    if not host:
        guessed = mailer.guess_host(user)
        if guessed is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Não conheço o servidor desse provedor. Abra as opções e "
                    "informe o servidor SMTP e a porta."
                ),
            )
        host, port = guessed
    account = mailer.MailAccount(
        host=host,
        port=port or 587,
        user=user,
        # App passwords are shown in groups of four; the spaces are not part
        # of the secret and some servers reject them.
        password=password.replace(" ", ""),
        from_name=payload.from_name.strip(),
        daily_limit=min(payload.daily_limit, mailer.MAX_DAILY_LIMIT),
    )
    await asyncio.to_thread(secrets.set, MAIL_ACCOUNT_SETTING, account.dumps())
    return await _mail_state()


@app.delete("/api/mail/account", status_code=204)
async def forget_mail_account() -> None:
    await asyncio.to_thread(secrets.remove, MAIL_ACCOUNT_SETTING)


@app.put("/api/mail/template", response_model=MailStateOut)
async def save_mail_template(payload: MailTemplateIn) -> MailStateOut:
    await asyncio.to_thread(
        secrets.set,
        MAIL_TEMPLATE_SETTING,
        json.dumps({"subject": payload.subject, "body": payload.body}),
    )
    return await _mail_state()


#: What the placeholders become in a test message, which has no lead behind it.
_SAMPLE_LEAD = {
    "title": "Canal de Exemplo",
    "handle": "@canaldeexemplo",
    "niche": "finanças pessoais",
    "subscribers": 48_000,
}


@app.post("/api/mail/test", status_code=204)
async def send_mail_test() -> None:
    """Send the current template to the sender's own address.

    Proves the account works and shows the message as a recipient will see it,
    without spending a lead or a slot of the daily limit.
    """
    account = _require_mail_account()
    subject, body = _mail_template()
    try:
        await asyncio.to_thread(
            mailer.send,
            account,
            account.user,
            "[teste] " + mailer.render(subject, _SAMPLE_LEAD),
            mailer.render(body, _SAMPLE_LEAD),
        )
    except mailer.MailError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


# One message at a time, whatever the interface does. Without this, two
# requests could both read "39 sent" and both go out as the fortieth.
_mail_lock = asyncio.Lock()


@app.post("/api/mail/send", response_model=MailSentOut)
async def send_mail(payload: MailSendIn) -> MailSentOut:
    """Send the saved template to one lead, then mark the lead as contacted.

    One lead per request on purpose: the interface paces the batch and can stop
    between any two messages, and a failure names the one lead it happened on.
    """
    account = _require_mail_account()
    async with _mail_lock:
        lead = await asyncio.to_thread(leads.get, payload.lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Canal não encontrado na base.")
        to = (lead.get("email") or "").strip()
        if not to:
            raise HTTPException(
                status_code=422, detail="Esse canal não publicou um e-mail."
            )
        if lead.get("emailed_at") and not payload.resend:
            raise HTTPException(
                status_code=409, detail="Esse canal já recebeu um e-mail seu."
            )

        sent = await asyncio.to_thread(_sent_today)
        if sent >= account.daily_limit:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Limite de {account.daily_limit} e-mails em 24 horas atingido. "
                    "O envio volta a ficar disponível conforme os mais antigos "
                    "saem da janela."
                ),
            )

        subject, body = _mail_template()
        try:
            await asyncio.to_thread(
                mailer.send,
                account,
                to,
                mailer.render(subject, lead),
                mailer.render(body, lead),
            )
        except mailer.MailError as error:
            # 422 for an address the server would not take, 502 for an account
            # that is not working: the interface skips the first and stops on
            # the second.
            code = 422 if error.recipient else 502
            raise HTTPException(status_code=code, detail=str(error)) from error

        await asyncio.to_thread(leads.mark_emailed, payload.lead_id)
        sent += 1
    return MailSentOut(
        to=to,
        sent_today=sent,
        remaining_today=max(0, account.daily_limit - sent),
    )


# ============================================================= X / pedidos
# A second source with its own base. A channel and a hiring post are not the
# same kind of lead: one keeps for months, the other is stale in a day. They
# never share a table, and never share a screen.
ACTOR_SETTING = "apify_actor"
TOKEN_SETTING = "apify"


def _apify_token() -> str:
    token = secrets.get(TOKEN_SETTING)
    if not token:
        raise HTTPException(
            status_code=428,
            detail=(
                "Nenhum token do Apify cadastrado. Adicione o seu na aba "
                "Chaves de API para buscar no X."
            ),
        )
    return token


@app.get("/api/x/token", response_model=TokenOut)
async def read_token() -> TokenOut:
    """Whether a token is set, and what is left of the month's credit."""
    token = secrets.get(TOKEN_SETTING)
    if not token:
        return TokenOut(configured=False)
    try:
        credit = await account_credit(token)
    except XSearchError as error:
        return TokenOut(configured=True, masked=masked(token), error=str(error))
    return TokenOut(
        configured=True,
        masked=masked(token),
        remaining_usd=credit["remaining_usd"],
        total_usd=credit["total_usd"],
    )


@app.post("/api/x/token", response_model=TokenOut, status_code=201)
async def save_token(payload: TokenIn) -> TokenOut:
    await asyncio.to_thread(secrets.set, TOKEN_SETTING, payload.token)
    if payload.actor:
        await asyncio.to_thread(secrets.set, ACTOR_SETTING, payload.actor)
    return await read_token()


@app.delete("/api/x/token", status_code=204)
async def forget_token() -> None:
    await asyncio.to_thread(secrets.remove, TOKEN_SETTING)


@app.get("/api/x/terms")
async def default_terms() -> dict[str, list[str]]:
    """The built-in phrase list, so the screen can show it rather than say it."""
    return {"terms": list(DEFAULT_TERMS)}


@app.post("/api/x/search", response_model=XSearchResponse)
async def search_x(filters: XSearchFilters) -> XSearchResponse:
    """Search X for people asking to hire an editor, and keep what is found."""
    token = _apify_token()
    client = XClient(token, actor=secrets.get(ACTOR_SETTING) or DEFAULT_ACTOR)
    try:
        found = await client.search(
            terms=[t for t in filters.terms if t.strip()] or None,
            days=filters.days,
            max_items=filters.max_items,
            min_followers=filters.min_followers,
        )
    except XSearchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    new, updated = await asyncio.to_thread(posts.save_many, found.posts)
    total = await asyncio.to_thread(posts.count)

    remaining = None
    try:
        remaining = (await account_credit(token))["remaining_usd"]
    except XSearchError:
        # The search already succeeded; not knowing the balance must not turn
        # a good result into an error.
        pass

    return XSearchResponse(
        posts=[PostOut(**p, hours_old=hours_old(p.get("posted_at"))) for p in found.posts],
        examined=found.examined,
        competitors=found.competitors,
        unrelated=found.unrelated,
        saved_new=new,
        saved_updated=updated,
        total_saved=total,
        remaining_usd=remaining,
    )


@app.get("/api/posts", response_model=PostsResponse)
async def list_posts(
    q: str = "",
    sort: str = "posted_at",
    limit: int = 500,
    offset: int = 0,
    with_budget: bool = False,
    min_followers: int = 0,
    status: str = "",
) -> PostsResponse:
    """The saved hiring posts. Separate from the channel base, on purpose."""
    rows, total = await asyncio.to_thread(
        posts.list,
        query=q,
        sort=sort,
        limit=limit,
        offset=offset,
        with_budget=with_budget,
        min_followers=min_followers,
        status=status,
    )
    return PostsResponse(posts=[PostOut(**row) for row in rows], total=total)


@app.delete("/api/posts/{post_id}", status_code=204)
async def delete_post(post_id: str) -> None:
    removed = await asyncio.to_thread(posts.delete, post_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")


@app.delete("/api/posts", status_code=200)
async def clear_posts() -> dict[str, int]:
    removed = await asyncio.to_thread(posts.clear)
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


class WebFiles(StaticFiles):
    """The exported pages, with the one header the default is missing.

    StaticFiles sends ETag and Last-Modified but no Cache-Control, and without
    it Chromium applies *heuristic* freshness: it may serve a stored copy for
    hours without asking the server whether it changed. In a browser that is a
    reasonable default. Here it means the user installs an update, opens the
    app, and is shown the previous interface with no way to tell why — which
    happened twice while this was being built, both times looking exactly like
    the new code had failed to ship.

    So the HTML shell always revalidates. That costs one conditional request
    per launch and the answer is normally a 304 with no body. The files under
    ``_next/static`` keep the opposite rule: their names contain a hash of
    their contents, so a name that still exists is by definition unchanged.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        # Starlette hands this over already joined for the local filesystem, so
        # on Windows the separators are backslashes and a "_next/static/" test
        # silently never matches. Measured, not assumed: the first version of
        # this check marked every hashed chunk no-cache on Windows and would
        # have looked correct on the Mac runner.
        if path.replace("\\", "/").startswith("_next/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


_WEB = _frontend_dir()
if _WEB is not None:
    app.mount("/", WebFiles(directory=_WEB, html=True), name="web")
