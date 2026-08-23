"""Prospector as a desktop application.

One process does everything: it serves the exported interface and the API from
the same local origin, then shows that origin in its own window. No Node, no
port to remember, no browser tab left behind.

The window is a Chromium already installed on the machine, launched in app
mode: no address bar, no tabs, its own taskbar entry. That is deliberate.
The obvious alternative, an embedded webview through pywebview, drags in
pythonnet and the .NET WinForms bridge, which crashes on Python 3.14 here —
and a broken window is worse than a borrowed one. App mode costs nothing to
ship and uses a renderer the user already trusts and updates.

Closing the window ends the process, because the window is what the app is.
"""

from __future__ import annotations

import glob
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Uvicorn writes to stderr. A windowed build has no console attached, and on
# Windows writing to a missing handle raises, so give it somewhere to go before
# anything imports the server.
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")  # noqa: SIM115
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")  # noqa: SIM115

APP_NAME = "Prospector"


def user_data_dir() -> Path:
    # One definition, in app.paths, so the launcher's browser profile and the
    # lead base can never disagree about where this user's folder is.
    from app.paths import user_data_dir as _shared

    return _shared()


def free_port() -> int:
    """A port the OS says is free right now.

    Binding to 0 and reading back the assignment avoids the classic desktop
    failure where a hardcoded port is already taken and the app dies on launch
    with nothing on screen to explain why.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_up(url: str, timeout: float = 40.0) -> bool:
    """Block until the server answers, so the window never opens on an error."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.15)
    return False


def _find_browser_macos() -> str | None:
    """A Chromium-family browser in /Applications or the user's own folder.

    Safari is deliberately not a candidate: it has no --app mode, so it would
    open a tab with an address bar instead of something that looks like an app.
    Falling back to the default browser is handled by the caller.
    """
    apps = [
        "Brave Browser.app/Contents/MacOS/Brave Browser",
        "Google Chrome.app/Contents/MacOS/Google Chrome",
        "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "Chromium.app/Contents/MacOS/Chromium",
    ]
    roots = [Path("/Applications"), Path.home() / "Applications"]
    for root in roots:
        for rel in apps:
            candidate = root / rel
            if candidate.is_file():
                return str(candidate)
    return None


def find_browser() -> str | None:
    """A Chromium-family browser that supports --app mode.

    Edge is on every Windows 11 machine and Chrome is on most Macs, so this
    usually resolves; Brave and Chrome are checked first only because someone
    who installed one probably prefers it.
    """
    if sys.platform == "darwin":
        return _find_browser_macos()

    program_files = [
        os.getenv("ProgramFiles", r"C:\Program Files"),
        os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.getenv("LOCALAPPDATA", ""),
    ]
    relative = [
        r"BraveSoftware\Brave-Browser\Application\brave.exe",
        r"Google\Chrome\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
    ]
    for root in program_files:
        if not root:
            continue
        for rel in relative:
            candidate = Path(root) / rel
            if candidate.is_file():
                return str(candidate)

    # Newer Edge installs live under a versioned EdgeCore folder.
    for root in program_files:
        if not root:
            continue
        matches = sorted(glob.glob(str(Path(root) / "Microsoft" / "EdgeCore" / "*" / "msedge.exe")))
        if matches:
            return matches[-1]
    return None


def serve(port: int) -> None:
    import uvicorn

    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> int:
    # A fixed port and a windowless run make the packaged app debuggable;
    # without them a failure inside a frozen GUI build is a silent one.
    port = int(os.getenv("PROSPECTOR_PORT") or 0) or free_port()
    base = f"http://127.0.0.1:{port}"
    home = f"{base}/"

    # Daemon: when this function returns the server goes with it.
    threading.Thread(target=serve, args=(port,), daemon=True).start()

    if not wait_until_up(f"{base}/api/health"):
        _fatal(
            "O servidor local não subiu a tempo.\n\n"
            "Se isso continuar, um antivírus pode estar bloqueando a porta local."
        )
        return 1

    if os.getenv("PROSPECTOR_NO_WINDOW") == "1":
        print(f"{APP_NAME} servindo em {home}", flush=True)
        threading.Event().wait()
        return 0

    browser = find_browser()
    if browser is None:
        # No Chromium: the default browser is still a window. Worse framing,
        # working app.
        import webbrowser

        webbrowser.open(home)
        _fatal(
            f"{APP_NAME} está aberto no seu navegador.\n\n"
            "Feche esta mensagem quando terminar para encerrar o programa."
        )
        return 0

    # A private profile keeps this window out of the user's browsing session
    # and, more importantly, makes it a standalone process — so waiting on it
    # actually means "waiting for the app window to close".
    profile = user_data_dir() / "window"
    profile.mkdir(parents=True, exist_ok=True)

    process = subprocess.Popen(
        [
            browser,
            f"--app={home}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1440,920",
        ]
    )
    process.wait()
    return 0


def _fatal(message: str) -> None:
    """Say something visible: a windowed build has no console to print to."""
    try:
        if sys.platform == "darwin":
            # osascript is always present; quotes must be escaped or the whole
            # AppleScript fails to compile and the user sees nothing at all.
            body = message.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display dialog "{body}" with title "{APP_NAME}" '
                    'buttons {"OK"} default button "OK"',
                ],
                check=False,
                timeout=300,
            )
            return

        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x40)
    except Exception:
        print(message, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
