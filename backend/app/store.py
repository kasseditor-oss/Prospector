"""Where the API keys live between runs.

Two implementations behind one interface:

``MemoryKeyStore``  the default when running from source. Keys never touch a
                    disk, and they die with the process.

``LocalKeyStore``   keys encrypted at rest on this machine, surviving a
                    restart. This is what the packaged app uses.

Both hold a *single* key pool. Prospector is one person on one computer, so
there is no second visitor to isolate: reopening the window has to look like
the same user coming back, not like a stranger arriving with an empty pool.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Protocol

from .keyring import InMemoryKeyring, KeyState, current_quota_day
from .paths import data_dir
from .secretbox import SecretBox


class KeyStore(Protocol):
    def keyring(self) -> InMemoryKeyring:
        """The key pool. The same object on every call."""

    def flush(self) -> None:
        """Write the pool's current state out. A no-op for memory storage."""


# --------------------------------------------------------------------- memory
class MemoryKeyStore:
    """Process-local storage. Used when running from source, and by the tests."""

    def __init__(self) -> None:
        self._keyring = InMemoryKeyring()

    def keyring(self) -> InMemoryKeyring:
        return self._keyring

    def flush(self) -> None:
        # The keyring object is already the stored one; nothing to write back.
        return


# ---------------------------------------------------------------------- local
class LocalKeyStore:
    """Keys saved on this machine, encrypted, surviving restarts.

    Quota counters are saved alongside the keys. Without them a restart would
    look like a fresh 10,000 units, and the app would promise searches the
    YouTube API is going to refuse.
    """

    FILENAME = "keys.json"

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = Path(directory) if directory else data_dir()
        self._path = self._dir / self.FILENAME
        self._box = SecretBox(self._dir)
        self._lock = threading.Lock()
        self._keyring = InMemoryKeyring()
        self._read()

    def describe(self) -> str:
        return self._box.describe()

    # -- disk ------------------------------------------------------------
    def _read(self) -> None:
        try:
            rows = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(rows, list):
            return
        for row in rows:
            plain = self._box.decrypt(str(row.get("secret") or ""))
            if not plain:
                # Unreadable here: written by another account or machine. The
                # app asks for the key again rather than failing to start.
                continue
            self._keyring.adopt(
                KeyState(
                    key=plain,
                    label=row.get("label") or "Chave",
                    used=int(row.get("used") or 0),
                    day=row.get("day") or current_quota_day(),
                    disabled_reason=row.get("disabled_reason"),
                )
            )

    def _write(self) -> None:
        rows = [
            {
                "label": state.label,
                "secret": self._box.encrypt(state.key),
                "used": state.used,
                "day": state.day,
                "disabled_reason": state.disabled_reason,
            }
            for state in self._keyring.all()
        ]
        self._dir.mkdir(parents=True, exist_ok=True)
        # Write beside the target and rename: a crash mid-write must not leave
        # a truncated file where the keys used to be.
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        os.replace(temporary, self._path)

    # -- interface -------------------------------------------------------
    def keyring(self) -> InMemoryKeyring:
        return self._keyring

    def flush(self) -> None:
        with self._lock:
            self._write()


def build_store() -> KeyStore:
    """Pick storage from the environment.

    Memory when running from source, so a clone of this repo starts with no
    setup at all. Disk in the packaged app, where losing the key on every
    restart would mean pasting it again every single time.
    """
    default = "local" if getattr(sys, "frozen", False) else "memory"
    backend = os.getenv("PROSPECTOR_STORE", default).strip().lower()
    return LocalKeyStore() if backend == "local" else MemoryKeyStore()


# --------------------------------------------------------------- named secrets
class SecretStore:
    """Single named secrets — today just the Apify token.

    Kept apart from the keyring rather than folded into it: a YouTube key
    belongs to a pool with quota, rotation and a daily reset, and none of that
    applies here. One token, which either works or does not. Sharing the
    keyring's shape would mean pretending it has state it does not have.

    Same vault as the keys, so the guarantee is identical: DPAPI on Windows,
    Keychain on macOS.
    """

    FILENAME = "tokens.json"

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = Path(directory) if directory else data_dir()
        self._path = self._dir / self.FILENAME
        self._box = SecretBox(self._dir)
        self._lock = threading.Lock()
        self._values: dict[str, str] = {}
        self._read()

    def describe(self) -> str:
        return self._box.describe()

    def _read(self) -> None:
        try:
            stored = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(stored, dict):
            return
        for name, token in stored.items():
            plain = self._box.decrypt(str(token or ""))
            if plain:
                self._values[str(name)] = plain

    def _write(self) -> None:
        payload = {name: self._box.encrypt(value) for name, value in self._values.items()}
        self._dir.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        os.replace(temporary, self._path)

    def get(self, name: str) -> str:
        return self._values.get(name, "")

    def set(self, name: str, value: str) -> None:
        with self._lock:
            self._values[name] = value.strip()
            self._write()

    def remove(self, name: str) -> bool:
        with self._lock:
            existed = self._values.pop(name, None) is not None
            if existed:
                self._write()
            return existed


def masked(secret: str) -> str:
    """Enough to recognise it, never enough to use it."""
    if len(secret) <= 12:
        return "•" * len(secret)
    return f"{secret[:9]}{'•' * 12}{secret[-4:]}"
