"""Per-visitor isolation for API key pools.

The keyring cannot be a module-level global: that would hand every visitor the
same pool, so one person's key would pay for another person's searches and
everyone would see everyone else's (masked) keys.

Each browser gets an opaque session id in an httpOnly cookie, and each session
id maps to its own keyring. No account, no password, no personal data — the
cookie identifies a key pool and nothing else.

Idle sessions are evicted so a long-running server does not accumulate keys
forever. Eviction is lazy (checked on access) rather than a background thread,
which keeps the module free of lifecycle management.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from .keyring import InMemoryKeyring

SESSION_COOKIE = "prospector_session"

# A prospecting session is a work session. Eight hours covers a full day of use
# without keeping abandoned keys in memory overnight.
SESSION_TTL_SECONDS = 8 * 60 * 60

# Bound on concurrent sessions, so a flood of cookieless requests cannot grow
# the process without limit.
MAX_SESSIONS = 5_000


@dataclass
class Session:
    id: str
    keyring: InMemoryKeyring = field(default_factory=InMemoryKeyring)
    last_seen: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def is_idle(self, now: float) -> bool:
        return now - self.last_seen > SESSION_TTL_SECONDS


class SessionStore:
    """Thread-safe map of session id to keyring."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def _drop_idle(self, now: float) -> None:
        """Caller must hold the lock."""
        stale = [sid for sid, s in self._sessions.items() if s.is_idle(now)]
        for sid in stale:
            del self._sessions[sid]

    def _enforce_cap(self) -> None:
        """Shed the least recently used sessions until back under the cap.

        Runs *after* a new session is inserted, not before: trimming first
        leaves room for the insert and lands one session over the limit.
        """
        if len(self._sessions) <= MAX_SESSIONS:
            return
        ordered = sorted(self._sessions.values(), key=lambda s: s.last_seen)
        for session in ordered[: len(self._sessions) - MAX_SESSIONS]:
            self._sessions.pop(session.id, None)

    def resolve(self, session_id: str | None) -> Session:
        """Return the session for this id, minting a new one when needed.

        An unknown or expired id yields a fresh session rather than an error —
        the visitor simply starts over with an empty key pool.
        """
        now = time.monotonic()
        with self._lock:
            self._drop_idle(now)

            if session_id:
                existing = self._sessions.get(session_id)
                if existing is not None:
                    existing.touch()
                    return existing

            # 32 bytes of entropy: guessing another visitor's session id is not
            # a realistic attack path.
            new_id = secrets.token_urlsafe(32)
            session = Session(id=new_id)
            self._sessions[new_id] = session
            self._enforce_cap()
            return session

    def drop(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
