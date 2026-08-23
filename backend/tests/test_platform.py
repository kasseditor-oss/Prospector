"""Cross-platform behaviour.

The macOS build has to be produced on a Mac, so these tests cannot prove the
.app runs. What they can prove — and what actually breaks silently otherwise —
is that every platform branch picks the right folder, the right browser and the
right vault, instead of quietly falling back to the weakest option.

Each test fakes ``sys.platform`` so the branch under test runs on whatever
machine happens to be executing the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app import paths, secretbox


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("PROSPECTOR_DATA_DIR", "LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)


# ------------------------------------------------------------------- folders
def test_macos_data_lives_in_application_support(monkeypatch, clean_env):
    """Anywhere else and Time Machine does not treat it as app data."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/ana")))
    assert paths.user_data_dir() == Path("/Users/ana/Library/Application Support/Prospector")


def test_windows_data_lives_in_localappdata(monkeypatch, clean_env):
    """Asserted as parent + name, never as a literal string.

    On a Mac ``\\`` is an ordinary character, so ``Path(r"C:\\a\\b")`` is a
    single component and comparing it to a spelled-out Windows path fails for
    a reason that has nothing to do with this code.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    base = r"C:\Users\ana\AppData\Local"
    monkeypatch.setenv("LOCALAPPDATA", base)

    result = paths.user_data_dir()
    assert result.name == "Prospector"
    assert result.parent == Path(base)


def test_linux_follows_the_xdg_spec(monkeypatch, clean_env):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/home/ana/.local/share")
    assert paths.user_data_dir() == Path("/home/ana/.local/share/Prospector")


def test_the_override_wins_on_every_platform(monkeypatch, tmp_path):
    for platform in ("darwin", "win32", "linux"):
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setenv("PROSPECTOR_DATA_DIR", str(tmp_path))
        assert paths.data_dir() == tmp_path


def test_frozen_builds_write_to_the_user_folder_not_beside_the_code(monkeypatch, clean_env):
    """Packaged, the code lives in a temp dir the OS deletes; data must not."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/ana")))
    assert paths.data_dir() == Path("/Users/ana/Library/Application Support/Prospector")


# ------------------------------------------------------------------ browsers
def _desktop():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import desktop

    return desktop


def test_macos_finds_a_chromium_in_applications(monkeypatch, tmp_path):
    """The search roots are replaced, not just $HOME.

    A Mac running this suite has its own /Applications, and a test that reads
    it would pass on a machine with Chrome and fail on one without — telling
    you about the machine instead of about this code.
    """
    desktop = _desktop()
    chrome = tmp_path / "Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome.parent.mkdir(parents=True)
    chrome.write_text("#!/bin/sh\n")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "mac_app_roots", lambda: [tmp_path])

    found = desktop._find_browser_macos()
    assert found == str(chrome)


def test_macos_prefers_brave_over_chrome(monkeypatch, tmp_path):
    """Someone who installed Brave chose Brave."""
    desktop = _desktop()
    for name in ("Brave Browser", "Google Chrome"):
        binary = tmp_path / f"{name}.app/Contents/MacOS/{name}"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\n")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "mac_app_roots", lambda: [tmp_path])
    assert desktop._find_browser_macos().endswith("Brave Browser")


def test_macos_reports_no_browser_rather_than_guessing(monkeypatch, tmp_path):
    """Safari has no --app mode, so 'none found' must stay 'none found' and
    let the caller fall back to the default browser."""
    desktop = _desktop()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "mac_app_roots", lambda: [tmp_path])
    assert desktop._find_browser_macos() is None


# -------------------------------------------------------------------- vaults
def test_the_vault_is_named_honestly_per_platform(monkeypatch, tmp_path):
    cases = {
        "dpapi": "DPAPI do Windows (só a sua conta neste PC abre)",
        "keychain": "Chaveiro do macOS (só a sua conta neste Mac abre)",
        "file": "arquivo local cifrado (protege contra cópia casual)",
    }
    for mode, text in cases.items():
        box = secretbox.SecretBox(tmp_path)
        monkeypatch.setattr(box, "_mode", mode)
        assert box.describe() == text


def test_a_mac_without_a_working_keychain_falls_back_to_a_file(monkeypatch, tmp_path):
    """Degrading is fine; degrading silently while claiming Keychain is not."""
    monkeypatch.setattr(secretbox, "_dpapi_available", lambda: False)
    monkeypatch.setattr(secretbox, "_keychain_available", lambda: True)
    monkeypatch.setattr(secretbox, "_keychain_key", lambda: None)

    box = secretbox.SecretBox(tmp_path)
    assert box._mode == "file"
    assert "arquivo local" in box.describe()


def test_the_keychain_path_round_trips_a_secret(monkeypatch, tmp_path):
    """With the Keychain answering, a key must survive encrypt/decrypt."""
    fake_key = secretbox._new_key()
    monkeypatch.setattr(secretbox, "_dpapi_available", lambda: False)
    monkeypatch.setattr(secretbox, "_keychain_available", lambda: True)
    monkeypatch.setattr(secretbox, "_keychain_key", lambda: fake_key)

    box = secretbox.SecretBox(tmp_path)
    assert box._mode == "keychain"
    token = box.encrypt("AIzaSyEXEMPLO")
    assert "AIzaSyEXEMPLO" not in token
    assert box.decrypt(token) == "AIzaSyEXEMPLO"


def test_the_keychain_key_is_not_written_next_to_the_data(monkeypatch, tmp_path):
    """The whole point: the data folder alone must not be enough to decrypt."""
    fake_key = secretbox._new_key()
    monkeypatch.setattr(secretbox, "_dpapi_available", lambda: False)
    monkeypatch.setattr(secretbox, "_keychain_available", lambda: True)
    monkeypatch.setattr(secretbox, "_keychain_key", lambda: fake_key)

    secretbox.SecretBox(tmp_path).encrypt("AIzaSyEXEMPLO")
    assert not (tmp_path / "secret.key").exists()
