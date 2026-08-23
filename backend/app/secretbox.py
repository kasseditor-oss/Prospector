"""Encrypting small secrets for storage on the user's own machine.

A YouTube API key bills to the owner's Google account, so it must not sit on
disk in clear text — a synced folder, a backup, or a shared screen would leak
real quota.

Each platform has a vault the OS itself guards, and the point of using it is
that the encryption key is never written beside the data:

* **Windows — DPAPI.** The ciphertext decrypts only for the same Windows
  account on the same machine.
* **macOS — Keychain.** The file stays Fernet-encrypted, but the Fernet key
  lives in the login Keychain instead of on disk, which gives the same shape of
  guarantee: copy the data folder to another Mac and it is noise.

Where neither exists the fallback is Fernet with a locally generated secret.
That is weaker on purpose-stated terms — the secret sits near the ciphertext,
so it protects against a casual copy, not against someone who already has your
files — and :func:`describe` says so, rather than implying a guarantee that is
not there.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

_UI_FORBIDDEN = 0x01

#: How the Fernet key is filed in the macOS Keychain.
_KEYCHAIN_SERVICE = "Prospector"
_KEYCHAIN_ACCOUNT = "prospector-local-key"


def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi(encrypt: bool, data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    buffer_in = ctypes.create_string_buffer(data, len(data))
    blob_in = Blob(len(data), ctypes.cast(buffer_in, ctypes.POINTER(ctypes.c_char)))
    blob_out = Blob()

    function = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    ok = function(
        ctypes.byref(blob_in),
        ctypes.c_wchar_p("Prospector"),
        None,          # no extra entropy: the user account is the boundary
        None,
        None,
        _UI_FORBIDDEN,  # never pop a prompt; this runs during a request
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError(ctypes.get_last_error() or "DPAPI recusou a operação")

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _new_key() -> bytes:
    import secrets

    return base64.urlsafe_b64encode(secrets.token_bytes(32))


def _security(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """Run macOS's `security` tool without ever showing a window."""
    return subprocess.run(
        ["security", *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _keychain_available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        return _security("list-keychains").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _keychain_key() -> bytes | None:
    """The Fernet key from the login Keychain, creating it on first use."""
    try:
        found = _security(
            "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-a", _KEYCHAIN_ACCOUNT, "-w"
        )
        if found.returncode == 0 and found.stdout.strip():
            return found.stdout.strip().encode("ascii")

        key = _new_key()
        # -U updates in place if a stale entry exists. The key is visible in
        # this process's arguments for the instant the call runs; `security`
        # offers no stdin form, and the exposure is to the user's own session
        # on their own machine.
        stored = _security(
            "add-generic-password",
            "-s", _KEYCHAIN_SERVICE,
            "-a", _KEYCHAIN_ACCOUNT,
            "-w", key.decode("ascii"),
            "-U",
        )
        return key if stored.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _file_key(directory: Path) -> bytes:
    """A locally generated Fernet key, created once and reused."""
    path = directory / "secret.key"
    if path.is_file():
        return path.read_bytes().strip()

    key = _new_key()
    directory.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best effort: some filesystems do not carry POSIX modes.
        pass
    return key


class SecretBox:
    """Encrypt and decrypt short strings for this machine and user."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._mode = self._pick_mode()
        self._key: bytes | None = None

    def _pick_mode(self) -> str:
        """Prove the vault works now, not at the moment a key is saved."""
        if _dpapi_available():
            try:
                _dpapi(False, _dpapi(True, b"ping"))
                return "dpapi"
            except Exception:
                pass
        if _keychain_available() and _keychain_key() is not None:
            return "keychain"
        return "file"

    def describe(self) -> str:
        return {
            "dpapi": "DPAPI do Windows (só a sua conta neste PC abre)",
            "keychain": "Chaveiro do macOS (só a sua conta neste Mac abre)",
        }.get(self._mode, "arquivo local cifrado (protege contra cópia casual)")

    def _fernet(self):
        from cryptography.fernet import Fernet

        if self._key is None:
            self._key = (
                _keychain_key() if self._mode == "keychain" else None
            ) or _file_key(self._directory)
        return Fernet(self._key)

    def encrypt(self, plain: str) -> str:
        raw = plain.encode("utf-8")
        if self._mode == "dpapi":
            return base64.b64encode(_dpapi(True, raw)).decode("ascii")
        return self._fernet().encrypt(raw).decode("ascii")

    def decrypt(self, token: str) -> str | None:
        """The plain secret, or None when this machine cannot read it."""
        try:
            if self._mode == "dpapi":
                return _dpapi(False, base64.b64decode(token)).decode("utf-8")
            return self._fernet().decrypt(token.encode()).decode("utf-8")
        except Exception:
            # Written by another user, another machine, or under a secret that
            # is gone. Unreadable is not a crash: the app asks for the key again.
            return None
