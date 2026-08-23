"""Where Prospector keeps the user's own data.

Packaged, the code runs from a temporary folder the OS deletes on exit, so
anything written next to the code is lost when the app closes. User data — the
lead base, the saved API keys — belongs in the per-user data folder, which
survives reinstalls and updates of the program itself.

Each platform has one right answer and the others are wrong in ways users
notice: on macOS a folder outside ``~/Library/Application Support`` does not
get backed up by Time Machine the way an app's data is expected to, and on
Windows anything under ``Roaming`` would follow the user onto other machines
where the encrypted keys cannot be read anyway.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Prospector"


def user_data_dir() -> Path:
    """The per-user folder this platform expects an app to write to.

    Honoured even from a source checkout by :func:`data_dir` when frozen, and
    used directly by the desktop launcher for the browser profile.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or str(Path.home())
        return Path(base) / APP_NAME
    # Linux and the rest: the XDG basedir spec.
    base = os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def data_dir() -> Path:
    """The folder holding the lead base and the saved keys."""
    override = os.getenv("PROSPECTOR_DATA_DIR")
    if override:
        return Path(override)

    if getattr(sys, "frozen", False):
        return user_data_dir()

    # From a source checkout, keeping data in the repo is friendlier: it is
    # visible, and deleting the checkout deletes the scratch data with it.
    return Path(__file__).resolve().parent.parent / "data"
