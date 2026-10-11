"""
One disk cache for downloaded text (catalogues, HAPI answers, index files).

A cached copy is used without asking the server when it is younger than `ttl_s`, or for good
when it was written after `permanent_after` (the data were complete then: a copy fetched while
its period was still being filled is fetched again). Otherwise the server is asked; an answer
that `valid` accepts replaces the copy (written atomically), and when the server cannot be
reached, or answers something not valid, the last copy is used, however old.
"""
from __future__ import annotations

import gzip
import os
import time
from datetime import datetime
from typing import Awaitable, Callable, Optional, Tuple


def _read(path: str, gz: bool) -> Optional[str]:
    try:
        with (gzip.open(path, "rt", encoding="utf-8") if gz else open(path, encoding="utf-8")) as f:
            return f.read()
    except (OSError, EOFError, UnicodeDecodeError):  # missing or truncated copy
        return None


async def cached_text(path: str, url: str, fetch_text: Callable[[str], Awaitable[Optional[str]]], ttl_s: float,
                      permanent_after: Optional[datetime] = None, valid: Callable[[str], bool] = lambda t: True,
                      gz: bool = False) -> Tuple[Optional[str], bool]:
    """(text or None, whether the server was asked and could not give a valid answer)."""
    if os.path.exists(path):
        mtime = os.path.getmtime(path)
        if (permanent_after is not None and mtime > permanent_after.timestamp()) or time.time() - mtime < ttl_s:
            text = _read(path, gz)
            if text is not None:
                return text, False
    text = await fetch_text(url)
    try:
        ok = text is not None and valid(text)
    except ValueError:
        ok = False
    if not ok:
        return (_read(path, gz) if os.path.exists(path) else None), True
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with (gzip.open(tmp, "wt", encoding="utf-8") if gz else open(tmp, "w", encoding="utf-8")) as f:
        f.write(text)
    os.replace(tmp, path)
    return text, False
