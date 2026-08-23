"""Keys that survive closing the app.

The desktop app is a new process on every launch, so an in-memory key pool
meant pasting the YouTube key again every single time. These tests pin the two
things that make saving it acceptable: it comes back after a restart, and it
is never on disk in clear text.
"""

from __future__ import annotations

import json

import pytest

from app.keyring import DAILY_UNITS_PER_KEY
from app.secretbox import SecretBox
from app.store import LocalKeyStore

KEY = "AIzaSyREAL" + "R" * 25


@pytest.fixture
def store(tmp_path):
    return LocalKeyStore(tmp_path)


# ------------------------------------------------------------------ crypto
def test_the_key_is_never_written_in_clear(tmp_path):
    store = LocalKeyStore(tmp_path)
    store.keyring().add(KEY, "Principal")
    store.flush()

    raw = (tmp_path / LocalKeyStore.FILENAME).read_text(encoding="utf-8")
    assert KEY not in raw
    assert "AIzaSy" not in raw


def test_the_label_is_readable_but_the_secret_is_not(tmp_path):
    """Labels help the user pick a key; they are not credentials."""
    store = LocalKeyStore(tmp_path)
    store.keyring().add(KEY, "Conta pessoal")
    store.flush()

    rows = json.loads((tmp_path / LocalKeyStore.FILENAME).read_text(encoding="utf-8"))
    assert rows[0]["label"] == "Conta pessoal"
    assert KEY not in rows[0]["secret"]


def test_a_round_trip_returns_the_exact_key(tmp_path):
    box = SecretBox(tmp_path)
    assert box.decrypt(box.encrypt(KEY)) == KEY


def test_unreadable_ciphertext_yields_none_rather_than_raising(tmp_path):
    assert SecretBox(tmp_path).decrypt("isto-nao-e-um-token") is None


# ----------------------------------------------------------------- restart
def test_the_key_survives_a_restart(tmp_path):
    """The whole point: close the app, open it, the key is still there."""
    first = LocalKeyStore(tmp_path)
    first.keyring().add(KEY, "Principal")
    first.flush()

    # A new process would build a new store from the same folder.
    restored = LocalKeyStore(tmp_path).keyring()
    assert [k.key for k in restored.all()] == [KEY]
    assert restored.all()[0].label == "Principal"


def test_spent_quota_survives_too(tmp_path):
    """Restarting must not promise units the YouTube API will refuse."""
    first = LocalKeyStore(tmp_path)
    keyring = first.keyring()
    state = keyring.add(KEY, "Principal")
    keyring.charge(state, 4_200)
    first.flush()

    restored = LocalKeyStore(tmp_path).keyring()
    assert restored.all()[0].used == 4_200
    assert restored.total_remaining() == DAILY_UNITS_PER_KEY - 4_200


def test_a_key_rejected_by_youtube_stays_rejected(tmp_path):
    first = LocalKeyStore(tmp_path)
    keyring = first.keyring()
    state = keyring.add(KEY)
    keyring.disable(state, "invalid")
    first.flush()

    restored = LocalKeyStore(tmp_path).keyring()
    assert restored.all()[0].disabled_reason == "invalid"


def test_removing_a_key_removes_it_from_disk(tmp_path):
    store = LocalKeyStore(tmp_path)
    keyring = store.keyring()
    keyring.add(KEY)
    store.flush()

    keyring.remove(KEY)
    store.flush()
    assert LocalKeyStore(tmp_path).keyring().all() == []


# ----------------------------------------------------------------- desktop
def test_there_is_one_pool_not_one_per_window(store):
    """One person, one computer: a new window is not a new user."""
    store.keyring().add(KEY, "Principal")
    assert [k.key for k in store.keyring().all()] == [KEY]


def test_an_unreadable_file_does_not_stop_the_app(tmp_path):
    """A file from another machine must cost the key, not the launch."""
    (tmp_path / LocalKeyStore.FILENAME).write_text(
        json.dumps([{"label": "Alheia", "secret": "AQAAlixo=="}]), encoding="utf-8"
    )
    assert LocalKeyStore(tmp_path).keyring().all() == []


def test_corrupt_json_does_not_stop_the_app(tmp_path):
    (tmp_path / LocalKeyStore.FILENAME).write_text("{ nao json", encoding="utf-8")
    assert LocalKeyStore(tmp_path).keyring().all() == []


def test_no_file_yet_is_an_empty_pool_not_an_error(tmp_path):
    assert LocalKeyStore(tmp_path).keyring().all() == []


def test_a_failed_write_leaves_the_previous_keys_intact(tmp_path, monkeypatch):
    """Saving must never destroy working keys by half-writing over them."""
    store = LocalKeyStore(tmp_path)
    keyring = store.keyring()
    keyring.add(KEY, "Principal")
    store.flush()

    def explode(*args, **kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr("os.replace", explode)
    keyring.add("AIzaSyOUTRA" + "X" * 24, "Segunda")
    with pytest.raises(OSError):
        store.flush()

    assert [k.label for k in LocalKeyStore(tmp_path).keyring().all()] == ["Principal"]
