"""Links the app opens in the browser. Some come from outside (the community sheet, GitHub), and Windows
runs whatever it is handed: a "link" such as http\\..\\..\\file.exe opens that file. So only plain https
links are ever opened, and links from the sheet only to the video sites its records use."""
from __future__ import annotations

import webbrowser
from urllib.parse import urlsplit

# Where the sheet's record videos are (subdomains included).
VIDEO_HOSTS = ("youtube.com", "youtu.be", "bilibili.com", "b23.tv", "twitch.tv", "x.com", "twitter.com",
               "streamable.com", "medal.tv")
GITHUB_HOSTS = ("github.com",)
MAX_LENGTH = 500


def safe_url(url, hosts: tuple[str, ...] | None = None) -> str:
    """The link if it is https://host/... (the host being one of hosts or a subdomain, when given) and
    nothing else: no other scheme, no file path, no login, no spaces or backslashes. Otherwise ''."""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url or len(url) > MAX_LENGTH or any(c.isspace() or ord(c) < 32 or c in '\\"<>^`{|}' for c in url):
        return ""
    try:
        parts = urlsplit(url)
        parts.port  # a port that isn't a number raises here
    except ValueError:
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or not host or "." not in host or parts.username or parts.password:
        return ""
    if hosts is not None and not any(host == allowed or host.endswith("." + allowed) for allowed in hosts):
        return ""
    return url


def open_url(url, hosts: tuple[str, ...] | None = None) -> bool:
    """Opens the link in the browser if safe_url accepts it; says whether it did."""
    url = safe_url(url, hosts)
    if url:
        webbrowser.open(url)
    return bool(url)
