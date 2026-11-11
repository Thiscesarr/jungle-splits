"""Writes requirements.txt and requirements-build.txt from requirements.in and requirements-build.in:
every package (and the packages they need) at the exact version installed here, with the SHA-256 of
each of its files on PyPI. pip then refuses anything else, so a release is built from the same files
that were tested, whatever is uploaded to PyPI later.

To update the dependencies: install the new versions, run the tests and the build, then run this.
    pip install --upgrade pyinstaller pillow pystray
    python tools/lock_requirements.py
"""
from __future__ import annotations

import json
import re
import urllib.request
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
HEADER = "# Written by tools/lock_requirements.py from {source}: don't edit by hand.\n"


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def top_level(source: Path) -> list[str]:
    lines = (line.split("#")[0].strip() for line in source.read_text(encoding="utf-8").splitlines())
    return [canonical(Requirement(line).name) for line in lines if line and not line.startswith("-")]


def closure(names: list[str]) -> set[str]:
    """These packages and everything they need on this system, as installed."""
    found: set[str] = set()
    todo = list(names)
    while todo:
        name = todo.pop()
        if name in found:
            continue
        found.add(name)
        for text in metadata.requires(name) or []:
            requirement = Requirement(text)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                todo.append(canonical(requirement.name))
    return found


def locked(name: str) -> str:
    version = metadata.version(name)
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
        files = json.load(response)["urls"]
    hashes = sorted({file["digests"]["sha256"] for file in files})
    if not hashes:
        raise SystemExit(f"{name} {version} has no files on PyPI")
    return f"{name}=={version} \\\n" + " \\\n".join(f"    --hash=sha256:{h}" for h in hashes) + "\n"


def main() -> None:
    runtime = closure(top_level(ROOT / "requirements.in"))
    build = closure(top_level(ROOT / "requirements-build.in")) - runtime
    (ROOT / "requirements.txt").write_text(
        HEADER.format(source="requirements.in") + "".join(locked(n) for n in sorted(runtime)), encoding="utf-8",
        newline="\n")
    (ROOT / "requirements-build.txt").write_text(
        HEADER.format(source="requirements-build.in") + "-r requirements.txt\n"
        + "".join(locked(n) for n in sorted(build)), encoding="utf-8", newline="\n")
    print(f"locked {len(runtime)} runtime and {len(build)} build packages")


if __name__ == "__main__":
    main()
