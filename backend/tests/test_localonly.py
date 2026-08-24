"""Only this machine's own name gets an answer.

These are the requests a rebinding attack actually makes. The interesting ones
are not the obvious foreign domain but the near-misses: a name that merely
*starts* with 127.0.0.1, an IPv6 address full of colons, a Host header that
isn't there at all.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.localonly import LocalOnly, hostname, is_local


# ------------------------------------------------------------- reading a Host
@pytest.mark.parametrize(
    "header, esperado",
    [
        ("127.0.0.1:8000", "127.0.0.1"),
        ("127.0.0.1", "127.0.0.1"),
        ("localhost:53211", "localhost"),
        ("LOCALHOST:80", "localhost"),
        ("  127.0.0.1:9000  ", "127.0.0.1"),
        # IPv6 is the case a naive split on ":" gets wrong.
        ("[::1]:8000", "[::1]"),
        ("[::1]", "[::1]"),
    ],
)
def test_the_port_comes_off_and_the_name_stays(header, esperado):
    assert hostname(header) == esperado


@pytest.mark.parametrize("header", ["127.0.0.1:8000", "localhost:80", "[::1]:1", "127.0.0.1"])
def test_this_machine_is_recognised(header):
    assert is_local(header)


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "site-malicioso.exemplo:8000",
        # The near-misses. Each one is a real hostname somebody can register or
        # point at 127.0.0.1, and each one would sail through a `startswith`.
        "127.0.0.1.exemplo.com",
        "localhost.exemplo.com",
        "meu127.0.0.1",
        "0.0.0.0",
        "192.168.0.10",
        # A second Host smuggled in behind a comma.
        "127.0.0.1, site-malicioso.exemplo",
    ],
)
def test_anything_else_is_not_this_machine(header):
    assert not is_local(header)


# --------------------------------------------------------- through the server
@pytest.fixture
def servidor():
    app = FastAPI()
    app.add_middleware(LocalOnly)

    @app.get("/api/leads")
    async def leads():
        return {"leads": ["segredo"]}

    @app.delete("/api/leads")
    async def apagar():
        return {"deleted": 27}

    return app


def pedir(app, method, host):
    # base_url sets the Host header, which is the whole point of these.
    with TestClient(app, base_url=f"http://{host}") as client:
        return client.request(method, "/api/leads")


def test_the_app_answers_its_own_address(servidor):
    assert pedir(servidor, "GET", "127.0.0.1:8000").status_code == 200


def test_a_page_wearing_another_domain_is_turned_away(servidor):
    """The attack, in one line: DNS points at 127.0.0.1, the browser still
    writes the attacker's domain into Host, and the read must fail."""
    resposta = pedir(servidor, "GET", "site-malicioso.exemplo:8000")
    assert resposta.status_code == 400
    assert "segredo" not in resposta.text


def test_it_cannot_delete_the_base_either(servidor):
    """Measured before the fix: this answered 200 and wiped the base."""
    assert pedir(servidor, "DELETE", "site-malicioso.exemplo:8000").status_code == 400


def test_the_refusal_says_nothing_useful_to_whoever_sent_it(servidor):
    """Whoever sent this is not the user, so the reply should not help them
    map the app."""
    texto = pedir(servidor, "GET", "site-malicioso.exemplo").text
    assert "127.0.0.1" in texto
    assert len(texto) < 120
