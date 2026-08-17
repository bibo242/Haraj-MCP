"""Resolve relative thumbURLs into full CDN URLs."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from haraj.models import Post

KNOWN_CDN_HOSTS = ("mimg6cdn.haraj.com.sa", "img4cdn.haraj.com.sa")
PRIMARY_CDN = KNOWN_CDN_HOSTS[0]

_DATE_RE = re.compile(r"/(\d{4}-\d{1,2}-\d{1,2})/")


def _guess_date_folder(post: Post) -> str:
    for url in post.imagesList:
        match = _DATE_RE.search(url)
        if match:
            return match.group(1)
    dt = datetime.fromtimestamp(post.postDate, tz=timezone.utc)
    return f"{dt.year}-{dt.month}-{dt.day}"


def full_thumb_url(post: Post) -> str | None:
    if not post.thumbURL:
        return None
    if post.thumbURL.startswith("http"):
        return post.thumbURL
    date_folder = _guess_date_folder(post)
    return f"https://{PRIMARY_CDN}/userfiles30/{date_folder}/{post.thumbURL}"


def image_urls(post: Post, max_n: int = 5) -> list[str]:
    urls = list(post.imagesList)
    if not urls and post.thumbURL:
        full = full_thumb_url(post)
        if full:
            urls = [full]
    return urls[:max_n]


def pick_host(url: str) -> str | None:
    host = urlparse(url).netloc
    return host or None
