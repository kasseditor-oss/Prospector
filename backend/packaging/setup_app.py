"""Single-file installer for Prospector.

The folder build is 98 files. Handing someone a zip of that and asking them to
extract it, find installer\\Instalar.bat and run it from the right place is where
most people give up — a good number click the .bat from inside the zip, where
the relative paths do not resolve, and conclude the program is broken.

This is one file. Double-click, a window opens, one button installs. The whole
program folder rides inside as a bundled payload, so there is nothing to
extract by hand and no path for the user to get wrong.

Installing per user, into %LOCALAPPDATA%\\Programs, is deliberate: no UAC
prompt, no administrator password, nothing written outside the user's own
profile. The lead base lives somewhere else entirely and is never touched here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import font as tkfont

APP_NAME = "Prospector"
PUBLISHER = "Prospector"
VERSION = "1.0.0"

TARGET = Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME
DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / APP_NAME
START_MENU = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"

# The palette the app itself uses, so the installer does not look like a
# stranger to the thing it installs.
BG = "#10131A"
PANEL = "#171B23"
INK = "#EDF1F6"
INK_2 = "#9BA6B4"
SIGNAL = "#4C8DFF"
SIGNAL_INK = "#03070F"
OK = "#5BD08A"
BAD = "#F0736A"

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: never flash a console at the user


def bundled(name: str) -> Path:
    """A file packed into this executable by PyInstaller."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return root / name


def run_hidden(*args: str) -> None:
    subprocess.run(args, creationflags=NO_WINDOW, check=False)


def stop_running_copy() -> None:
    """An open Prospector holds its own .exe open and would block the copy."""
    run_hidden("taskkill", "/F", "/IM", f"{APP_NAME}.exe")
    time.sleep(1.5)


def make_shortcut(path: Path, target: Path) -> None:
    """Shortcuts need COM, and PowerShell is the shortest way to reach it."""
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath = '{exe}';"
        "$s.WorkingDirectory = '{dir}';"
        "$s.Description = 'Prospeccao de canais do YouTube';"
        "$s.Save()"
    ).format(lnk=path, exe=target, dir=target.parent)
    run_hidden("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script)


def register_uninstall(size_kb: int) -> None:
    """HKCU, so Windows lists it in Settings with a working Uninstall button
    and no elevation was ever needed to put it there."""
    exe = TARGET / f"{APP_NAME}.exe"
    command = (
        f'powershell -ExecutionPolicy Bypass -File "{TARGET / "uninstall.ps1"}"'
    )
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in [
            ("DisplayName", APP_NAME),
            ("DisplayVersion", VERSION),
            ("Publisher", PUBLISHER),
            ("InstallLocation", str(TARGET)),
            ("DisplayIcon", str(exe)),
            ("UninstallString", command),
        ]:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, value in [("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", size_kb)]:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def install(progress) -> Path:
    """Copy the payload into place and wire up the shortcuts."""
    payload = bundled("payload")
    if not (payload / f"{APP_NAME}.exe").is_file():
        raise RuntimeError("Este instalador foi montado sem o programa dentro.")

    progress("Fechando o Prospector, se estiver aberto…")
    stop_running_copy()

    progress("Copiando os arquivos…")
    if TARGET.exists():
        shutil.rmtree(TARGET, ignore_errors=True)
    shutil.copytree(payload, TARGET)

    uninstaller = bundled("uninstall.ps1")
    if uninstaller.is_file():
        shutil.copy2(uninstaller, TARGET / "uninstall.ps1")

    exe = TARGET / f"{APP_NAME}.exe"

    progress("Criando os atalhos…")
    START_MENU.mkdir(parents=True, exist_ok=True)
    make_shortcut(START_MENU / f"{APP_NAME}.lnk", exe)
    desktop = Path(os.path.expanduser("~/Desktop"))
    if desktop.is_dir():
        make_shortcut(desktop / f"{APP_NAME}.lnk", exe)

    progress("Registrando em Aplicativos Instalados…")
    total = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file())
    register_uninstall(max(1, total // 1024))

    return exe


# ------------------------------------------------------------------- interface
class Installer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Instalar {APP_NAME}")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._centre(460, 330)
        try:
            self.iconbitmap(str(bundled("Prospector.ico")))
        except Exception:
            pass  # an installer must not die over its own title-bar icon

        self.exe: Path | None = None
        self._build()

    def _centre(self, width: int, height: int) -> None:
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 3
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self) -> None:
        title_font = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        body_font = tkfont.Font(family="Segoe UI", size=10)
        small_font = tkfont.Font(family="Segoe UI", size=9)

        tk.Label(self, text=APP_NAME, bg=BG, fg=INK, font=title_font).pack(pady=(34, 2))
        tk.Label(
            self,
            text="Prospecção de canais do YouTube para editores",
            bg=BG,
            fg=INK_2,
            font=small_font,
        ).pack()

        card = tk.Frame(self, bg=PANEL)
        card.pack(fill="x", padx=30, pady=(26, 0))
        tk.Label(
            card,
            text=(
                "Instala só para você, sem pedir administrador.\n"
                "Nada é escrito fora da sua pasta de usuário."
            ),
            bg=PANEL,
            fg=INK_2,
            font=small_font,
            justify="left",
        ).pack(padx=16, pady=14)

        self.status = tk.Label(self, text="", bg=BG, fg=INK_2, font=body_font, wraplength=400)
        self.status.pack(pady=(18, 0))

        self.button = tk.Button(
            self,
            text="Instalar",
            command=self.start,
            bg=SIGNAL,
            fg=SIGNAL_INK,
            activebackground="#75A9FF",
            activeforeground=SIGNAL_INK,
            font=tkfont.Font(family="Segoe UI", size=11, weight="bold"),
            relief="flat",
            cursor="hand2",
            padx=30,
            pady=9,
            borderwidth=0,
        )
        self.button.pack(pady=(16, 0))

        tk.Label(
            self,
            text=str(TARGET),
            bg=BG,
            fg="#5A6472",
            font=tkfont.Font(family="Segoe UI", size=8),
        ).pack(side="bottom", pady=12)

    # -- actions ---------------------------------------------------------
    def start(self) -> None:
        self.button.configure(state="disabled", text="Instalando…")
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        try:
            exe = install(lambda text: self.after(0, self._say, text, INK_2))
        except Exception as error:  # noqa: BLE001 - the user needs the reason
            self.after(0, self._failed, str(error))
            return
        self.after(0, self._done, exe)

    def _say(self, text: str, colour: str) -> None:
        self.status.configure(text=text, fg=colour)

    def _failed(self, message: str) -> None:
        self._say(f"Não deu certo: {message}", BAD)
        self.button.configure(state="normal", text="Tentar de novo")

    def _done(self, exe: Path) -> None:
        self.exe = exe
        self._say("Instalado. Está no Menu Iniciar e na Área de Trabalho.", OK)
        self.button.configure(
            state="normal", text="Abrir o Prospector", command=self.launch, bg=SIGNAL
        )

    def launch(self) -> None:
        if self.exe:
            subprocess.Popen([str(self.exe)], cwd=str(self.exe.parent))
        self.destroy()


def main() -> int:
    # /S is the convention every Windows installer answers to, and it is also
    # what makes this executable testable without a human clicking a button.
    if any(arg.lower() in ("/s", "-s", "--silent") for arg in sys.argv[1:]):
        try:
            install(lambda _text: None)
        except Exception as error:  # noqa: BLE001
            print(f"ERRO: {error}", file=sys.stderr)
            return 1
        return 0

    Installer().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
