"""Where bundled files and the player's data live, for a source checkout and for the installed .exe."""
from __future__ import annotations

import configparser
import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# Files shipped with the app (config.json, the fallback sheet, icons...).
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
# Folder of the .exe; the installer writes install.ini (chosen language) here.
INSTALL_DIR = Path(sys.executable).resolve().parent if FROZEN else BUNDLE_DIR
# The installed app may live in a read-only folder, so player data goes to the user's AppData; a source
# checkout keeps it at the repository root (data/, git-ignored), next to src/.
USER_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Jungle Splits" if FROZEN else BUNDLE_DIR.parent

DATA_DIR = USER_DIR / "data"
DEMO_DATA_DIR = USER_DIR / "data_demo"
CUSTOM_SOUNDS_DIR = USER_DIR / "sons"
ICON_ICO = BUNDLE_DIR / "assets" / "icon.ico"
ICON_PNG = BUNDLE_DIR / "assets" / "icon.png"
CONFIG = BUNDLE_DIR / "config.json"
FALLBACK_SHEET = BUNDLE_DIR / "clears_fallback.csv"


def installer_language() -> str | None:
    """Language picked in the installer, if the app was installed with it."""
    ini = configparser.ConfigParser()
    try:
        ini.read(INSTALL_DIR / "install.ini", encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        return None
    value = ini.get("app", "language", fallback="").lower()
    return {"brazilianportuguese": "pt", "portuguese": "pt", "english": "en"}.get(value)


def ensure_custom_sounds_dir() -> Path:
    """Creates the folder where players can drop their own WAVs, with its instructions."""
    CUSTOM_SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    readme = CUSTOM_SOUNDS_DIR / "LEIA-ME.txt"
    if not readme.exists() and (BUNDLE_DIR / "sons" / "LEIA-ME.txt").exists():
        shutil.copyfile(BUNDLE_DIR / "sons" / "LEIA-ME.txt", readme)
    return CUSTOM_SOUNDS_DIR
