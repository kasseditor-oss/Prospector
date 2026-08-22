"""Each visitor must get their own key pool.

These tests exist because the first version of the API kept one module-level
keyring, which would have shared one visitor's YouTube key — and quota — with
every other visitor.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app, store
from app.sessions import SESSION_COOKIE, SessionStore

KEY_A = "AIzaSyAAAA" + "A" * 25
KEY_B = "AIzaSyBBBB" + "B" * 25


@pytest.fixture
def alice() -> TestClient:
    """A TestClient keeps its own cookie jar, so it behaves as one browser."""
    return TestClient(app)


@pytest.fixture
def bob() -> TestClient:
    return TestClient(app)


def test_two_visitors_do_not_share_keys(alice: TestClient, bob: TestClient):
    alice.post("/api/keys", json={"key": KEY_A, "label": "Alice"})

    assert [k["label"] for k in alice.get("/api/keys").json()] == ["Alice"]
    assert bob.get("/api/keys").json() == []


def test_two_visitors_do_not_share_quota(alice: TestClient, bob: TestClient):
    alice.post("/api/keys", json={"key": KEY_A, "label": "Alice"})
    bob.post("/api/keys", json={"key": KEY_B, "label": "Bob"})

    # Two separate pools of 10,000 — not one pool of 20,000.
    assert alice.get("/api/quota").json()["units_total"] == 10_000
    assert bob.get("/api/quota").json()["units_total"] == 10_000
    assert alice.get("/api/quota").json()["keys"] == 1


def test_a_visitor_cannot_delete_another_visitors_key(alice: TestClient, bob: TestClient):
    alice.post("/api/keys", json={"key": KEY_A, "label": "Alice"})

    # Bob knows the last four characters and tries to remove it anyway.
    assert bob.delete(f"/api/keys/{KEY_A[-4:]}").status_code == 404
    assert len(alice.get("/api/keys").json()) == 1


def test_search_without_own_key_is_refused_even_when_others_have_one(
    alice: TestClient, bob: TestClient
):
    alice.post("/api/keys", json={"key": KEY_A, "label": "Alice"})

    body = {
        "niches": ["edicao de video"],
        "country": "BR",
        "language": "pt",
        "min_subscribers": 1000,
        "max_subscribers": 100000,
        "activity_days": 90,
        "email_only": False,
        "deep": False,
    }
    response = bob.post("/api/search", json=body)
    assert response.status_code == 428


def test_session_cookie_is_httponly_and_not_the_api_key(alice: TestClient):
    response = alice.get("/api/quota")
    header = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE in header
    assert "httponly" in header.lower()
    # The cookie is an opaque id; the key itself never leaves the server.
    alice.post("/api/keys", json={"key": KEY_A, "label": "Alice"})
    assert KEY_A not in alice.cookies.get(SESSION_COOKIE, "")


def test_masked_key_never_exposes_the_full_value(alice: TestClient):
    alice.post("/api/keys", json={"key": KEY_A, "label": "Alice"})
    masked = alice.get("/api/keys").json()[0]["masked"]
    assert masked != KEY_A
    assert KEY_A[6:-4] not in masked


# ------------------------------------------------------------ store internals
def test_unknown_session_id_yields_a_fresh_pool():
    store = SessionStore()
    session = store.resolve("a-session-id-that-was-never-issued")
    assert session.keyring.all() == []
    assert session.id != "a-session-id-that-was-never-issued"


def test_same_id_returns_the_same_pool():
    store = SessionStore()
    first = store.resolve(None)
    first.keyring.add(KEY_A, "mine")
    again = store.resolve(first.id)
    assert again is first
    assert len(again.keyring.all()) == 1


def test_idle_sessions_are_evicted(monkeypatch):
    store = SessionStore()
    session = store.resolve(None)
    session.keyring.add(KEY_A, "mine")

    # Push the session past its TTL.
    monkeypatch.setattr("app.sessions.SESSION_TTL_SECONDS", 0)
    session.last_seen = time.monotonic() - 1

    revived = store.resolve(session.id)
    assert revived.id != session.id
    assert revived.keyring.all() == []


def test_store_is_bounded(monkeypatch):
    monkeypatch.setattr("app.sessions.MAX_SESSIONS", 5)
    store = SessionStore()
    for _ in range(20):
        store.resolve(None)
    assert store.count() <= 5


def test_app_has_no_module_level_keyring():
    """Regression guard for the bug this module was written to fix."""
    import app.main as main

    assert not hasattr(main, "keyring"), (
        "A module-level keyring would be shared by every visitor."
    )
    # Every pool now comes from the store, never from a module global.
    assert hasattr(store, "load") and hasattr(store, "save")


def test_default_store_is_memory_so_a_clone_runs_with_no_setup():
    from app.store import MemoryKeyStore

    assert isinstance(store, MemoryKeyStore)
