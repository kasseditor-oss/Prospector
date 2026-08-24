"""Refusing requests that arrive under someone else's name.

The API listens on 127.0.0.1 with no password, which is the normal shape of a
desktop app: only this machine can reach the port. Two browser rules do the
rest of the work — a page from another site cannot read a response that
carries no CORS header, and anything past a "simple" request needs a preflight
this server never approves.

Both of those rules hang on one word: *origin*. And there is a known trick for
changing what the browser thinks the origin is. The attacker's page is served
from a domain whose DNS record has a one-second life; a moment later the name
resolves to 127.0.0.1 instead. The browser still believes it is talking to
that domain, so every request it makes to this server is same-origin now, and
neither rule applies. The script can read the whole lead base and delete it.

The random port is not a defence — a page can knock on ports until one answers.

What the page *cannot* do is lie about the Host header: the browser writes it
from the address bar and JavaScript is forbidden from touching it. So a
rebound request always announces the attacker's domain, and refusing any name
other than this machine's own closes the hole for the price of a string
comparison.

Measured before and after: DELETE /api/leads with `Host: outro-dominio` used to
answer 200 and wipe the base.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

#: Every name that means "this machine". The port is stripped before the
#: comparison — it changes on every launch, so it carries no information.
LOCAL_NAMES = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def hostname(header: str) -> str:
    """The name out of a Host header, without the port.

    IPv6 arrives bracketed (``[::1]:8000``), and the address itself is full of
    colons, so the port cannot be found by splitting on the first one.
    """
    value = header.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[: end + 1] if end != -1 else value
    return value.rsplit(":", 1)[0] if ":" in value else value


def is_local(header: str | None) -> bool:
    """Is this Host header one of this machine's own names?

    A missing header is not local. Only HTTP/1.0 omits it, and nothing that
    talks to this app speaks HTTP/1.0 — but a hand-written request can, and
    accepting it would leave the door open beside the lock.
    """
    if not header:
        return False
    return hostname(header) in LOCAL_NAMES


class LocalOnly:
    """Turn away anything addressed to a name that is not this machine."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if not is_local(Headers(scope=scope).get("host")):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            # Plain text, and deliberately uninformative: whoever sent this is
            # not the user, and the reply should not help them map the app.
            response = PlainTextResponse(
                "Prospector só responde a http://127.0.0.1.\n", status_code=400
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
