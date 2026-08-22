"""Encrypted key storage.

A visitor's YouTube key bills to their Google account, so it is encrypted
before it reaches Firestore: a database dump alone must not be enough to spend
anyone's quota.
"""

from __future__ import annotations

import time

import pytest

from app.store import COLLECTION, FirestoreKeyStore, MissingSecret

KEY = "AIzaSyREAL" + "R" * 25
SECRET = "a" * 48
OTHER_SECRET = "b" * 48


class FakeDoc:
    def __init__(self, store: dict, doc_id: str) -> None:
        self._store = store
        self._id = doc_id

    def get(self) -> "FakeDoc":
        return self

    @property
    def exists(self) -> bool:
        return self._id in self._store

    def to_dict(self) -> dict | None:
        return self._store.get(self._id)

    def set(self, data: dict) -> None:
        self._store[self._id] = data


class FakeCollection:
    def __init__(self, store: dict) -> None:
        self._store = store

    def document(self, doc_id: str) -> FakeDoc:
        return FakeDoc(self._store, doc_id)


class FakeFirestore:
    """Just enough of google.cloud.firestore.Client for these tests."""

    def __init__(self) -> None:
        self.data: dict[str, dict] = {}
        self.writes = 0

    def collection(self, name: str) -> FakeCollection:
        assert name == COLLECTION
        return FakeCollection(_CountingDict(self.data, self))


class _CountingDict(dict):
    """Counts writes so a test can prove the write budget is respected."""

    def __init__(self, backing: dict, owner: FakeFirestore) -> None:
        super().__init__()
        self._backing = backing
        self._owner = owner

    def __contains__(self, key: object) -> bool:
        return key in self._backing

    def get(self, key, default=None):
        return self._backing.get(key, default)

    def __setitem__(self, key, value) -> None:
        self._owner.writes += 1
        self._backing[key] = value


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("PROSPECTOR_SECRET", SECRET)


def test_a_secret_is_required(monkeypatch):
    monkeypatch.delenv("PROSPECTOR_SECRET", raising=False)
    with pytest.raises(MissingSecret):
        FirestoreKeyStore(client=FakeFirestore())


def test_a_short_secret_is_refused(monkeypatch):
    monkeypatch.setenv("PROSPECTOR_SECRET", "muito-curto")
    with pytest.raises(MissingSecret):
        FirestoreKeyStore(client=FakeFirestore())


def test_key_survives_a_round_trip(secret):
    db = FakeFirestore()
    store = FirestoreKeyStore(client=db)

    session_id, keyring = store.load(None)
    keyring.add(KEY, "Principal")
    store.save(session_id, keyring)

    # A fresh store instance, as a new Cloud Run instance would be.
    _, restored = FirestoreKeyStore(client=db).load(session_id)
    assert [k.key for k in restored.all()] == [KEY]
    assert restored.all()[0].label == "Principal"


def test_the_stored_document_never_contains_the_plain_key(secret):
    db = FakeFirestore()
    store = FirestoreKeyStore(client=db)
    session_id, keyring = store.load(None)
    keyring.add(KEY, "Principal")
    store.save(session_id, keyring)

    raw = str(db.data[session_id])
    assert KEY not in raw
    assert "AIzaSy" not in raw


def test_spent_quota_is_preserved_not_reset(secret):
    """Rehydrating must not hand back quota the visitor already spent."""
    db = FakeFirestore()
    store = FirestoreKeyStore(client=db)

    session_id, keyring = store.load(None)
    state = keyring.add(KEY, "Principal")
    keyring.charge(state, 4_200)
    store.save(session_id, keyring)

    _, restored = store.load(session_id)
    assert restored.all()[0].used == 4_200
    assert restored.total_remaining() == 10_000 - 4_200


def test_a_key_written_under_another_secret_is_dropped_not_crashed(secret, monkeypatch):
    db = FakeFirestore()
    session_id, keyring = FirestoreKeyStore(client=db).load(None)
    keyring.add(KEY, "Principal")
    FirestoreKeyStore(client=db).save(session_id, keyring)

    monkeypatch.setenv("PROSPECTOR_SECRET", OTHER_SECRET)
    _, restored = FirestoreKeyStore(client=db).load(session_id)
    assert restored.all() == []  # unreadable, but the request still serves


def test_unknown_session_yields_a_fresh_id_and_empty_pool(secret):
    store = FirestoreKeyStore(client=FakeFirestore())
    session_id, keyring = store.load("nunca-emitido")
    assert session_id != "nunca-emitido"
    assert keyring.all() == []


def test_expired_session_is_not_restored(secret):
    db = FakeFirestore()
    store = FirestoreKeyStore(client=db)
    session_id, keyring = store.load(None)
    keyring.add(KEY, "Principal")
    store.save(session_id, keyring)

    db.data[session_id]["last_seen"] = time.time() - (9 * 60 * 60)
    new_id, restored = store.load(session_id)
    assert new_id != session_id
    assert restored.all() == []


def test_an_empty_pool_costs_no_write(secret):
    """Writes are the scarcest part of the free tier; do not spend one on nothing."""
    db = FakeFirestore()
    store = FirestoreKeyStore(client=db)
    session_id, keyring = store.load(None)
    store.save(session_id, keyring)
    assert db.writes == 0


def test_one_request_costs_exactly_one_write(secret):
    db = FakeFirestore()
    store = FirestoreKeyStore(client=db)
    session_id, keyring = store.load(None)
    state = keyring.add(KEY, "Principal")

    # Simulate a deep search charging quota hundreds of times in memory.
    for _ in range(500):
        keyring.charge(state, 1)
    store.save(session_id, keyring)

    assert db.writes == 1, "per-charge writes would exhaust the daily free budget"
