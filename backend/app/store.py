"""Where a visitor's API keys live between requests.

Two implementations behind one interface:

``MemoryKeyStore``     the default. Zero setup, and keys never touch a disk —
                       but they die with the process and cannot be shared
                       across instances, which forces a single always-on
                       container.

``FirestoreKeyStore``  keys encrypted at rest in Firestore. This is what lets
                       Cloud Run scale to zero and run more than one instance,
                       which is the difference between a paid always-on service
                       and one that fits inside the free tier.

Read-and-write budget matters here. Firestore's free tier allows 20,000 writes
a day, and a deep search charges quota over 500 times. Writing on every charge
would exhaust the day's budget in under 40 searches, so a session is read once
at the start of a request and written once at the end — see
``session_keyring`` in :mod:`app.main`.
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
from typing import Any, Protocol

from cryptography.fernet import Fernet, InvalidToken

from .keyring import InMemoryKeyring, KeyState, current_quota_day

COLLECTION = "prospector_sessions"

# Matches the cookie lifetime in app.main.
SESSION_TTL_SECONDS = 8 * 60 * 60


class MissingSecret(RuntimeError):
    """Firestore storage was requested without an encryption secret."""


def _fernet() -> Fernet:
    """Encryption key derived from PROSPECTOR_SECRET.

    A user's YouTube key is a credential that bills to their Google account, so
    it is encrypted before it reaches the database. A database dump alone is
    then not enough to use anyone's quota.
    """
    secret = os.getenv("PROSPECTOR_SECRET", "").strip()
    if not secret:
        raise MissingSecret(
            "Set PROSPECTOR_SECRET to a long random string before enabling "
            "Firestore storage. Without it, API keys would be stored in clear."
        )
    if len(secret) < 32:
        raise MissingSecret("PROSPECTOR_SECRET must be at least 32 characters.")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class KeyStore(Protocol):
    def load(self, session_id: str | None) -> tuple[str, InMemoryKeyring]:
        """Return (session_id, keyring). An unknown id yields a fresh session."""

    def save(self, session_id: str, keyring: InMemoryKeyring) -> None:
        """Persist the keyring's current state. A no-op for memory storage."""


# --------------------------------------------------------------------- memory
class MemoryKeyStore:
    """Process-local storage. Fine for development and single-instance hosts."""

    def __init__(self) -> None:
        from .sessions import SessionStore

        self._sessions = SessionStore()

    def load(self, session_id: str | None) -> tuple[str, InMemoryKeyring]:
        session = self._sessions.resolve(session_id)
        return session.id, session.keyring

    def save(self, session_id: str, keyring: InMemoryKeyring) -> None:
        # The keyring object is already the stored one; nothing to write back.
        return

    def count(self) -> int:
        return self._sessions.count()


# ------------------------------------------------------------------ firestore
class FirestoreKeyStore:
    """Encrypted key pools in Firestore, one document per session."""

    def __init__(self, client: Any | None = None) -> None:
        self._fernet = _fernet()
        if client is not None:
            self._db = client
        else:  # pragma: no cover - requires real credentials
            from google.cloud import firestore

            self._db = firestore.Client()

    # -- serialisation ---------------------------------------------------
    def _encode(self, keyring: InMemoryKeyring) -> list[dict[str, Any]]:
        return [
            {
                "label": state.label,
                "secret": self._fernet.encrypt(state.key.encode("utf-8")).decode(),
                "used": state.used,
                "day": state.day,
                "disabled_reason": state.disabled_reason,
            }
            for state in keyring.all()
        ]

    def _decode(self, rows: list[dict[str, Any]]) -> InMemoryKeyring:
        keyring = InMemoryKeyring()
        for row in rows:
            try:
                plain = self._fernet.decrypt(row["secret"].encode()).decode()
            except (InvalidToken, KeyError, AttributeError):
                # A row we cannot read is a row written under a different
                # secret. Dropping it is better than crashing the request; the
                # visitor re-adds the key.
                continue
            state = KeyState(
                key=plain,
                label=row.get("label") or "Chave",
                used=int(row.get("used") or 0),
                day=row.get("day") or current_quota_day(),
                disabled_reason=row.get("disabled_reason"),
            )
            keyring.adopt(state)
        return keyring

    # -- interface -------------------------------------------------------
    def load(self, session_id: str | None) -> tuple[str, InMemoryKeyring]:
        import secrets

        if session_id:
            snapshot = self._db.collection(COLLECTION).document(session_id).get()
            if snapshot.exists:
                data = snapshot.to_dict() or {}
                if time.time() - float(data.get("last_seen") or 0) < SESSION_TTL_SECONDS:
                    return session_id, self._decode(data.get("keys") or [])
        return secrets.token_urlsafe(32), InMemoryKeyring()

    def save(self, session_id: str, keyring: InMemoryKeyring) -> None:
        rows = self._encode(keyring)
        doc = self._db.collection(COLLECTION).document(session_id)
        if not rows:
            # Nothing worth a write: an empty session is indistinguishable from
            # no session, and writes are the scarcest part of the free tier.
            return
        doc.set(
            {
                "keys": rows,
                "last_seen": time.time(),
                # Firestore deletes documents whose TTL field is in the past,
                # once a TTL policy is configured on `expires_at`.
                "expires_at": time.time() + SESSION_TTL_SECONDS,
            }
        )


def build_store() -> KeyStore:
    """Pick storage from the environment.

    Defaults to memory so a clone of this repo runs with no setup at all.
    """
    backend = os.getenv("PROSPECTOR_STORE", "memory").strip().lower()
    if backend == "firestore":
        return FirestoreKeyStore()
    return MemoryKeyStore()
