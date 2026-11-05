"""Self-update from the GitHub releases: find a newer version, download its installer, check it against
the release's SHA256SUMS.txt and run it silently (the installer relaunches the app when done).

A file downloaded by the app carries no "downloaded from the internet" mark, so SmartScreen only
ever shows up for the first, browser-downloaded install.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from version import __version__

LATEST_RELEASE_API = "https://api.github.com/repos/Thiscesarr/jungle-splits/releases/latest"
SETUP_NAME = "JungleSplits-Setup.exe"
SUMS_NAME = "SHA256SUMS.txt"
USER_AGENT = f"JungleSplits/{__version__}"


@dataclass(frozen=True)
class Update:
    version: str
    setup_url: str
    sums_url: str
    page_url: str


def version_tuple(text: str) -> tuple[int, ...]:
    """'v1.0.10' -> (1, 0, 10); anything unparsable sorts as oldest."""
    try:
        return tuple(int(part) for part in text.strip().lstrip("vV").split("."))
    except ValueError:
        return (0,)


def fetch(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def check_latest(current: str = __version__, fetch=fetch) -> Update | None:
    """The newest release if it is newer than current and ships an installer with checksums."""
    try:
        release = json.loads(fetch(LATEST_RELEASE_API))
    except (OSError, ValueError):
        return None
    tag = str(release.get("tag_name", ""))
    if release.get("draft") or release.get("prerelease") or version_tuple(tag) <= version_tuple(current):
        return None
    assets = {a.get("name"): a.get("browser_download_url") for a in release.get("assets", [])}
    if not assets.get(SETUP_NAME) or not assets.get(SUMS_NAME):
        return None
    return Update(tag.lstrip("vV"), assets[SETUP_NAME], assets[SUMS_NAME], str(release.get("html_url", "")))


def expected_hash(sums: str, name: str = SETUP_NAME) -> str | None:
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def download(update: Update, folder: Path, fetch=fetch) -> Path:
    """Downloads the installer and checks it against the release's SHA-256; raises ValueError if it
    doesn't match, so a corrupted or tampered file is never run."""
    wanted = expected_hash(fetch(update.sums_url).decode("utf-8", "replace"))
    if wanted is None:
        raise ValueError("no checksum for the installer")
    data = fetch(update.setup_url, timeout=120.0)
    if hashlib.sha256(data).hexdigest() != wanted:
        raise ValueError("installer checksum mismatch")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"JungleSplits-Setup-{update.version}.exe"
    target.write_bytes(data)
    return target


def run_installer(path: Path) -> None:
    """Starts the update in the background: the installer shows its progress, closes this app if it is
    still open, installs over the current version (same folder, same language) and relaunches it."""
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     close_fds=True)
