# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the single-file installer.

One-file here, unlike the app itself: an installer runs once, so paying a few
seconds of self-extraction buys the thing that matters — a single file someone
can be handed, with nothing to unzip and no way to click the wrong entry point.

The whole built app folder rides inside as the payload, which means this spec
depends on dist/Prospector already existing. compilar.bat builds them in order.
"""

from pathlib import Path

HERE = Path(SPECPATH).resolve()          # backend/packaging
BACKEND = HERE.parent                    # backend
APP = BACKEND / "dist" / "Prospector"
UNINSTALL = HERE / "uninstall.ps1"

if not (APP / "Prospector.exe").is_file():
    raise SystemExit(
        "backend/dist/Prospector is missing. Build the app first:\n"
        "  .venv/Scripts/python -m PyInstaller packaging/Prospector.spec --noconfirm\n"
        "Ou rode compilar.bat, que faz os passos na ordem."
    )

a = Analysis(
    [str(HERE / "setup_app.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=[
        # The program being installed, carried whole.
        (str(APP), "payload"),
        (str(UNINSTALL), "."),
        (str(HERE / "Prospector.ico"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # tkinter stays: it is the installer's window. Everything the app needs at
    # runtime is inside the payload, not imported here.
    excludes=["pytest", "matplotlib", "numpy", "PIL", "uvicorn", "fastapi", "httpx"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ProspectorSetup",
    icon=str(HERE / "Prospector.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # A window, not a console: a black box flashing up is what makes people
    # close an installer before it runs.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
