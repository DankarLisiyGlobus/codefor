import os
import re
import time
import threading
import tempfile
from collections import defaultdict
from urllib.parse import urlparse

import bleach
import markdown as md_lib


ALLOWED_TAGS = {
    'p', 'br', 'hr', 'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins',
    'blockquote', 'pre', 'code', 'span', 'div',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'sup', 'sub',
}
ALLOWED_ATTRS = {
    'a': ['href', 'title', 'rel', 'target'],
    'img': ['src', 'alt', 'title'],
    'code': ['class'],
    'span': ['class'],
    'div': ['class'],
    'th': ['align'], 'td': ['align'],
}
ALLOWED_PROTOCOLS = {'http', 'https', 'mailto'}


def markdown_to_safe_html(text: str) -> str:
    if not text:
        return ''
    html = md_lib.markdown(
        text,
        extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists'],
        output_format='html5',
    )
    clean = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    clean = bleach.linkify(clean, skip_tags=['pre', 'code'])
    return clean


def sanitize_plain(text: str, max_len: int | None = None) -> str:
    if not text:
        return ''
    s = bleach.clean(text, tags=[], attributes={}, strip=True).strip()
    if max_len:
        s = s[:max_len]
    return s


def is_safe_url(url: str) -> bool:
    if not url:
        return False
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme.lower() not in ('http', 'https', 'mailto'):
        return False
    if 'javascript' in url.lower() or 'data:' in url.lower()[:20]:
        return False
    return True


def safe_github_url(url: str) -> str | None:
    if not url:
        return None
    if not is_safe_url(url):
        return None
    p = urlparse(url)
    if p.netloc.lower() not in ('github.com', 'www.github.com'):
        return None
    return url


_IMAGE_SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': 'png',
    b'\xff\xd8\xff': 'jpg',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
}


def sniff_image_type(head: bytes) -> str | None:
    for sig, ext in _IMAGE_SIGNATURES.items():
        if head.startswith(sig):
            return ext
    if len(head) >= 12 and head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    return None


def verify_image(path: str) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: int) -> bool:
        now = time.time()
        with self._lock:
            arr = self._hits[key]
            cutoff = now - window
            while arr and arr[0] < cutoff:
                arr.pop(0)
            if len(arr) >= limit:
                return False
            arr.append(now)
            return True

    def reset(self, key: str):
        with self._lock:
            self._hits.pop(key, None)


rate_limiter = RateLimiter()


def ascii_filename(name: str) -> str:
    safe = name.encode('ascii', 'ignore').decode('ascii') or 'download'
    return safe.replace('"', '').replace('\\', '')