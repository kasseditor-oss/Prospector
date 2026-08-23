# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the macOS build.

Must run ON a Mac. PyInstaller does not cross-compile: it packages the
interpreter and the compiled extension modules of the machine doing the build,
so a Windows box cannot produce a working .app no matter how the spec is
written. This file exists so that step is one command on a Mac, not a project.

Produces dist/Prospector.app — a real bundle, which is what makes it draggable
into /Applications and launchable from Spotlight.
"""

from pathlib import Path

HERE = Path(SPECPATH).resolve()      # backend/packaging
BACKEND = HERE.parent                # backend
WEB = BACKEND.parent / "frontend" / "out"

if not (WEB / "index.html").is_file():
    raise SystemExit(
        "frontend/out is missing. Build it first:\n"
        "  cd frontend && PROSPECTOR_DESKTOP=1 npx next build\n"
        "Ou rode compilar-mac.command, que faz os dois passos na ordem."
    )

a = Analysis(
    [str(BACKEND / "desktop.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=[(str(WEB), "web")],
    hiddenimports=[
        # Resolved by string name at runtime, so static analysis cannot see them.
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
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    # Universal2 would need a universal Python; leaving this None builds for
    # the architecture of the Mac doing the build, which is what a personal
    # tool needs. Apple Silicon builds run on Apple Silicon.
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

app = BUNDLE(
    coll,
    name="Prospector.app",
    icon=str(HERE / "Prospector.icns"),
    bundle_identifier="com.prospector.app",
    info_plist={
        "CFBundleName": "Prospector",
        "CFBundleDisplayName": "Prospector",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        # No Dock icon suppression: this is a real windowed app, and hiding it
        # from the Dock would leave no way to bring the window back.
        "LSUIElement": False,
        "NSHighResolutionCapable": True,
        # The app talks only to 127.0.0.1 and to the YouTube API over HTTPS;
        # it never needs cleartext to an arbitrary host.
        "NSHumanReadableCopyright": "Prospector",
    },
)
