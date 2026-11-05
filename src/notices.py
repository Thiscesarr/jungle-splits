"""Notices published on GitHub and shown once in the app, so news reaches players without a new release.

They live in docs/notices.json on the repository's master branch; editing that file is enough. Each
notice is shown once per player (remembered by its id), only to the app versions in its optional range
and until its optional end date:

{
  "notices": [
    {
      "id": "patch-26-23-wolves",
      "title": {"pt": "...", "en": "..."},
      "text": {"pt": "...", "en": "..."},
      "link": "https://...",                        optional: adds a button that opens it
      "link_label": {"pt": "...", "en": "..."},     optional
      "min_version": "1.0.4", "max_version": "1.9", optional: app versions it is for
      "until": "2026-12-31"                         optional: last day it is shown
    }
  ]
}
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from updater import fetch, version_tuple

NOTICES_URL = "https://raw.githubusercontent.com/Thiscesarr/jungle-splits/master/docs/notices.json"


@dataclass(frozen=True)
class Notice:
    id: str
    title: str
    text: str
    link: str = ""
    link_label: str = ""


def _localized(value, language: str) -> str:
    """A {"pt": ..., "en": ...} text in the player's language (English, then any, as fallback)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in (language, "en", *value):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key]
    return ""


def parse_notices(data, version: str, language: str, seen: set[str], today: date) -> list[Notice]:
    """The notices this player should see now, in file order; anything malformed is skipped."""
    notices = []
    for item in (data.get("notices") if isinstance(data, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        notice_id = str(item.get("id", "")).strip()
        title, text = _localized(item.get("title"), language), _localized(item.get("text"), language)
        if not notice_id or notice_id in seen or not (title and text):
            continue
        if "min_version" in item and version_tuple(version) < version_tuple(str(item["min_version"])):
            continue
        if "max_version" in item and version_tuple(version) > version_tuple(str(item["max_version"])):
            continue
        try:
            if "until" in item and today > date.fromisoformat(str(item["until"])):
                continue
        except ValueError:
            continue
        link = str(item.get("link", ""))
        notices.append(Notice(notice_id, title, text, link if link.startswith("https://") else "",
                              _localized(item.get("link_label"), language)))
    return notices


def fetch_notices(fetch=fetch):
    """The parsed notices file, or None when it can't be read (offline, moved, not JSON)."""
    try:
        return json.loads(fetch(NOTICES_URL))
    except (OSError, ValueError):
        return None
