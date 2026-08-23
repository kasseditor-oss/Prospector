# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the desktop build.

Produces a folder under dist/Prospector containing the interpreter, the
dependencies and the exported interface. One-folder rather than one-file: a
one-file build unpacks itself into a temp directory on every launch, which
costs seconds of startup on every single run for a cosmetic gain.
"""

from pathlib import Path

HERE = Path(SPECPATH).resolve()      # backend/packaging
BACKEND = HERE.parent                # backend
WEB = BACKEND.parent / "frontend" / "out"

if not (WEB / "index.html").is_file():
    raise SystemExit(
        "frontend/out is missing. Build it first:\n"
        "  cd frontend && PROSPECTOR_DESKTOP=1 npx next build\n"
        "Ou rode compilar.bat, que faz os dois passos na ordem."
    )

a = Analysis(
    [str(BACKEND / "desktop.py")],
    # Absolute, so `import app.main` resolves whatever directory the build runs from.
    pathex=[str(BACKEND)],
    binaries=[],
    # The exported interface ships inside the app; main.py looks for it at
    # sys._MEIPASS/web.
    datas=[(str(WEB), "web")],
    hiddenimports=[
        # Uvicorn and its protocol implementations are resolved by string name
        # at runtime, so static analysis cannot see them.
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "app.main",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Prospector",
    # Generated from the same path data as the in-app mark, so the Start Menu
    # icon and the header logo are literally the same geometry.
    icon=str(HERE / "Prospector.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # No console window: this is a desktop app, not a script.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Prospector",
)
