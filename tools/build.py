"""Builds the Windows release into dist/:

- JungleSplits/            the app folder (PyInstaller, one folder: starts faster and trips antivirus
                           heuristics far less than a single self-extracting exe)
- JungleSplits-Portable.zip
- JungleSplits-Setup.exe   when Inno Setup is installed (always on the GitHub release workflow)
- SHA256SUMS.txt

Run from the repo root: python tools/build.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from version import GITHUB_URL, __version__  # noqa: E402

DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP = "JungleSplits"

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Jungle Splits'),
      StringStruct('FileDescription', 'Jungle Splits - F1-style jungle clear timer'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{app}'),
      StringStruct('LegalCopyright', 'Open source - {url}'),
      StringStruct('OriginalFilename', '{app}.exe'),
      StringStruct('ProductName', 'Jungle Splits'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def build_app() -> Path:
    import PyInstaller.__main__

    BUILD.mkdir(exist_ok=True)
    nums = tuple(int(n) for n in __version__.split(".")) + (0,)
    version_file = BUILD / "version_info.txt"
    version_file.write_text(VERSION_INFO.format(nums=nums, version=__version__, app=APP, url=GITHUB_URL),
                            encoding="utf-8")
    data = [("config.json", "."), ("clears_fallback.csv", "."), ("assets", "assets"), ("sons/LEIA-ME.txt", "sons")]
    PyInstaller.__main__.run([
        str(SRC / "main.py"),
        "--name", APP,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(SRC / "assets" / "icon.ico"),
        "--paths", str(SRC),
        "--version-file", str(version_file),
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        "--hidden-import", "pystray._win32",
        # Optional Pillow integrations the app never uses (numpy alone is ~27 MB). PIL.ImageTk stays: the
        # settings, first-run and pop-up windows draw their widgets with it (ui.py).
        *[arg for module in ("numpy", "PIL.ImageQt", "PyQt5", "PySide6")
          for arg in ("--exclude-module", module)],
        *[arg for src, dest in data for arg in ("--add-data", f"{SRC / src};{dest}")],
    ])
    return DIST / APP


def portable_zip(app_dir: Path) -> Path:
    target = DIST / f"{APP}-Portable.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in app_dir.rglob("*"):
            archive.write(file, Path("Jungle Splits") / file.relative_to(app_dir))
    return target


def find_iscc() -> str | None:
    """Inno Setup's compiler: on PATH, or in any of the folders its installer (or winget/choco) uses."""
    if shutil.which("iscc"):
        return shutil.which("iscc")
    roots = [Path(r"C:\Program Files (x86)"), Path(r"C:\Program Files"),
             Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"]
    found = sorted(c for root in roots for c in root.glob("Inno Setup*/ISCC.exe"))
    return str(found[-1]) if found else None


def installer() -> Path | None:
    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup not found: skipping the installer (the release workflow builds it).")
        return None
    subprocess.run([iscc, f"/DAppVersion={__version__}", str(ROOT / "packaging" / "installer.iss")], check=True)
    return DIST / f"{APP}-Setup.exe"


def checksums(files: list[Path]) -> None:
    lines = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}" for f in files]
    (DIST / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    app_dir = build_app()
    outputs = [portable_zip(app_dir), installer()]
    checksums([f for f in outputs if f])
    for f in DIST.iterdir():
        print(f.name)


if __name__ == "__main__":
    main()
