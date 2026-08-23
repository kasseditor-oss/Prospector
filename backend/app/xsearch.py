"""Finding hiring posts on X, through an Apify actor.

X's own API starts at US$100 a month for search, so this goes through a scraper
hosted on Apify instead. That has consequences worth stating plainly:

* It is a scraper. When X changes its site the actor breaks until its author
  fixes it, and the app will look broken through no fault of its own.
* The actor is **not** hard-coded. ``apidojo/tweet-scraper`` — the most used
  one — caps free-plan accounts at 10 results per run, which makes it useless
  to anyone who is not paying, and that was only discovered by reading a run
  log. Being able to switch actors without a code change is the whole defence
  against that happening again.

Billing is per result returned, not per result requested, so an over-generous
``max_items`` costs nothing when the search is narrow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .hiring import classify
from .posts import score_post

#: Free-plan friendly. See the module docstring for why this is a default and
#: not a constant buried in the call.
DEFAULT_ACTOR = "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest"

APIFY = "https://api.apify.com/v2"

#: Phrases people actually use when they want to pay someone to edit. Drawn
#: from a real search, not invented: the Portuguese ones outnumber the English
#: because that is what the results looked like.
DEFAULT_TERMS = [
    '"procuro editor"',
    '"preciso de um editor"',
    '"busco editor"',
    '"contrato editor"',
    '"looking for a video editor"',
    '"need a video editor"',
    '"hiring a video editor"',
]


class XSearchError(RuntimeError):
    """Something the user should see, in words they can act on."""


@dataclass
class XSearchResult:
    posts: list[dict[str, Any]] = field(default_factory=list)
    examined: int = 0
    #: Rejected as an editor advertising rather than a client hiring.
    competitors: int = 0
    #: Neither one thing nor the other.
    unrelated: int = 0


def _text(tweet: dict[str, Any]) -> str:
    return tweet.get("text") or tweet.get("fullText") or ""


def _author(tweet: dict[str, Any]) -> dict[str, Any]:
    return tweet.get("author") or {}


def to_post(tweet: dict[str, Any], query: str = "") -> dict[str, Any] | None:
    """A raw tweet as a stored post, or None when it is not a hiring post."""
    text = _text(tweet)
    verdict = classify(text)
    if not verdict.is_lead:
        return None

    author = _author(tweet)
    handle = author.get("userName") or author.get("screen_name") or ""
    post = {
        "id": str(tweet.get("id") or tweet.get("id_str") or ""),
        "source": "x",
        "author": handle,
        "author_name": author.get("name") or "",
        "author_followers": int(author.get("followers") or author.get("followers_count") or 0),
        "author_url": f"https://x.com/{handle}" if handle else "",
        "text": text,
        "url": tweet.get("url") or tweet.get("twitterUrl") or "",
        "posted_at": tweet.get("createdAt") or tweet.get("created_at"),
        "replies": int(tweet.get("replyCount") or 0),
        "likes": int(tweet.get("likeCount") or 0),
        "budget": verdict.budget,
        "ongoing": verdict.ongoing,
        "matched": verdict.matched,
        "query": query,
    }
    if not post["id"]:
        return None
    post["score"] = score_post(post)
    return post


class XClient:
    """Runs the actor and hands back only the posts worth reading."""

    def __init__(self, token: str, actor: str = DEFAULT_ACTOR) -> None:
        if not token.strip():
            raise XSearchError("Nenhum token do Apify cadastrado.")
        self._token = token.strip()
        self._actor = (actor or DEFAULT_ACTOR).replace("/", "~")

    async def search(
        self,
        *,
        terms: list[str] | None = None,
        days: int = 7,
        max_items: int = 200,
        min_followers: int = 0,
    ) -> XSearchResult:
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        payload = {
            "searchTerms": terms or DEFAULT_TERMS,
            "maxItems": max(1, min(max_items, 1000)),
            "queryType": "Latest",
            "since_time": since.strftime("%Y-%m-%d_%H:%M:%S_UTC"),
        }

        url = f"{APIFY}/acts/{self._actor}/run-sync-get-dataset-items"
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except httpx.HTTPError as error:
            raise XSearchError(f"Não consegui falar com o Apify: {error}") from error

        if response.status_code in (401, 403):
            raise XSearchError("O Apify recusou o token. Confira se ele foi copiado inteiro.")
        if response.status_code == 402:
            raise XSearchError(
                "O crédito do Apify acabou. Ele renova no início do próximo ciclo."
            )
        if response.status_code >= 400:
            raise XSearchError(f"O Apify respondeu {response.status_code}.")

        try:
            raw = response.json()
        except ValueError as error:
            raise XSearchError("O Apify devolveu algo que não é JSON.") from error
        if not isinstance(raw, list):
            raise XSearchError("O ator não devolveu uma lista de tweets.")

        result = XSearchResult(examined=len(raw))
        seen: set[str] = set()
        for tweet in raw:
            if not isinstance(tweet, dict):
                continue
            post = to_post(tweet, query=" ".join(terms or DEFAULT_TERMS)[:200])
            if post is None:
                kind = classify(_text(tweet)).kind
                if kind == "offering":
                    result.competitors += 1
                else:
                    result.unrelated += 1
                continue
            if post["id"] in seen:
                continue
            if post["author_followers"] < min_followers:
                # Filtered here rather than in the query: X search has no
                # follower operator, so the actor cannot do it for us.
                continue
            seen.add(post["id"])
            result.posts.append(post)

        result.posts.sort(key=lambda p: p["score"], reverse=True)
        return result


async def account_credit(token: str) -> dict[str, Any]:
    """What is left of the month's Apify credit.

    Shown next to the search the way YouTube quota already is: the free plan
    stops rather than bills, so running out is a surprise unless the number is
    on screen before the button is pressed.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{APIFY}/users/me/limits",
                headers={"Authorization": f"Bearer {token.strip()}"},
            )
    except httpx.HTTPError as error:
        raise XSearchError(f"Não consegui falar com o Apify: {error}") from error

    if response.status_code in (401, 403):
        raise XSearchError("O Apify recusou o token.")
    if response.status_code >= 400:
        raise XSearchError(f"O Apify respondeu {response.status_code}.")

    data = (response.json() or {}).get("data") or {}
    current = data.get("current") or {}
    limits = data.get("limits") or {}
    spent = float(current.get("monthlyUsageUsd") or 0)
    total = float(limits.get("maxMonthlyUsageUsd") or 0)
    return {
        "spent_usd": round(spent, 4),
        "total_usd": round(total, 2),
        "remaining_usd": round(max(0.0, total - spent), 4),
    }
