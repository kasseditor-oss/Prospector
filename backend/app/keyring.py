"""API key pool with quota accounting and automatic rotation.

The YouTube Data API bills in *units*, not requests, and every project gets
10,000 units per day that reset at midnight US/Pacific. Burning that budget by
accident is the single most common way a prospecting session dies halfway, so
this module tracks spend per key and rotates to the next key when one is spent.

The pool lives in memory. That is deliberate for now: keys belong to the user,
and not persisting them server-side means a stolen database contains no keys.
Swap ``InMemoryKeyring`` for a persistent implementation behind the same
interface when multi-user accounts land.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Documented unit costs, YouTube Data API v3.
COST_SEARCH_LIST = 100
COST_CHANNELS_LIST = 1
COST_PLAYLIST_ITEMS_LIST = 1

DAILY_UNITS_PER_KEY = 10_000

# Quota resets at midnight US/Pacific. Pacific is UTC-8 (UTC-7 on DST); we use
# -8 so the reset is never announced earlier than it actually happens.
_PACIFIC_OFFSET = timedelta(hours=-8)


class QuotaExhausted(RuntimeError):
    """Every key in the pool is out of units for the current quota day."""


def current_quota_day() -> str:
    """The Pacific-time calendar day that quota is billed against."""
    return (datetime.now(timezone.utc) + _PACIFIC_OFFSET).strftime("%Y-%m-%d")


@dataclass
class KeyState:
    key: str
    label: str
    used: int = 0
    day: str = field(default_factory=current_quota_day)
    disabled_reason: str | None = None

    def roll_day(self) -> None:
        today = current_quota_day()
        if self.day != today:
            self.day = today
            self.used = 0
            # A key disabled purely for quota gets a fresh chance after reset;
            # one disabled for being invalid stays disabled.
            if self.disabled_reason == "quota":
                self.disabled_reason = None

    @property
    def remaining(self) -> int:
        self.roll_day()
        if self.disabled_reason:
            return 0
        return max(0, DAILY_UNITS_PER_KEY - self.used)

    def masked(self) -> str:
        if len(self.key) <= 10:
            return "•" * len(self.key)
        return f"{self.key[:6]}{'•' * 12}{self.key[-4:]}"


class InMemoryKeyring:
    """Thread-safe pool of API keys ordered by remaining quota."""

    def __init__(self) -> None:
        self._keys: list[KeyState] = []
        self._lock = threading.Lock()

    # ---- pool management -------------------------------------------------
    def add(self, key: str, label: str | None = None) -> KeyState:
        with self._lock:
            for existing in self._keys:
                if existing.key == key:
                    return existing
            state = KeyState(key=key, label=label or f"Key {len(self._keys) + 1}")
            self._keys.append(state)
            return state

    def adopt(self, state: KeyState) -> None:
        """Insert an already-built KeyState, preserving its usage counters.

        Used when rehydrating a pool from storage: re-adding through ``add``
        would reset ``used`` to zero and hand the visitor quota they already
        spent.
        """
        with self._lock:
            if not any(existing.key == state.key for existing in self._keys):
                self._keys.append(state)

    def remove(self, key: str) -> bool:
        with self._lock:
            before = len(self._keys)
            self._keys = [k for k in self._keys if k.key != key]
            return len(self._keys) != before

    def all(self) -> list[KeyState]:
        with self._lock:
            for k in self._keys:
                k.roll_day()
            return list(self._keys)

    # ---- quota -----------------------------------------------------------
    def total_remaining(self) -> int:
        return sum(k.remaining for k in self.all())

    def acquire(self, cost: int) -> KeyState:
        """Return a key with at least ``cost`` units left.

        Picks the key with the most remaining quota so a large search is not
        split across keys mid-flight.
        """
        with self._lock:
            candidates = [k for k in self._keys if k.remaining >= cost]
            if candidates:
                return max(candidates, key=lambda k: k.remaining)

            # Why there is nothing to use changes what the user should do, so
            # the message has to distinguish the cases. Telling someone with a
            # mistyped key to "wait for the quota reset" sends them away for a
            # day over a problem they could fix in seconds.
            if not self._keys:
                raise QuotaExhausted(
                    "Nenhuma chave cadastrada. Adicione a sua chave da API do "
                    "YouTube para buscar."
                )

            invalid = [k for k in self._keys if k.disabled_reason == "invalid"]
            if len(invalid) == len(self._keys):
                if len(invalid) == 1:
                    raise QuotaExhausted(
                        "O YouTube recusou esta chave. Confira se você copiou "
                        "ela inteira e se a YouTube Data API v3 está ativada no "
                        "projeto do Google Cloud."
                    )
                raise QuotaExhausted(
                    "O YouTube recusou todas as chaves cadastradas. Confira se "
                    "foram copiadas por inteiro e se a YouTube Data API v3 está "
                    "ativada nos projetos."
                )

            if invalid:
                raise QuotaExhausted(
                    f"Sem quota disponível: {len(invalid)} de {len(self._keys)} "
                    f"chaves foram recusadas pelo YouTube e o resto atingiu o "
                    f"limite de hoje. A quota zera à meia-noite no Pacífico."
                )

            raise QuotaExhausted(
                f"As chaves cadastradas não têm as {cost} unidades que esta "
                f"busca precisa. Reduza o modo intensivo, adicione outra chave "
                f"ou espere o reset à meia-noite no Pacífico."
            )

    def charge(self, key_state: KeyState, cost: int) -> None:
        with self._lock:
            key_state.roll_day()
            key_state.used += cost

    def disable(self, key_state: KeyState, reason: str) -> None:
        with self._lock:
            key_state.disabled_reason = reason


def estimate_search_cost(*, niches: int, pages: int, enrich_last_upload: bool) -> int:
    """Predict the unit cost of a search *before* running it.

    This is the number the UI shows next to the search button. It has to match
    what :mod:`app.youtube` actually spends, so both read the same constants.
    """
    niches = max(1, niches)
    pages = max(1, pages)

    # One search.list call per niche per page.
    cost = niches * pages * COST_SEARCH_LIST
    # channels.list batches 50 ids per call; a page holds at most 50 results.
    cost += niches * pages * COST_CHANNELS_LIST
    if enrich_last_upload:
        # playlistItems.list is charged per channel, not per batch.
        cost += niches * pages * 50 * COST_PLAYLIST_ITEMS_LIST
    return cost
