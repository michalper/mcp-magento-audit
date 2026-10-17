"""Generic JSON file TTL cache — one JSON object per cache file, keyed by
whatever string the caller wants (a version, a URL, ...). No knowledge of
Magento, Composer or any specific domain, so any tool here that needs to
remember something between calls can reuse it.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()


def lock_for(path: Path) -> threading.Lock:
    """One lock per cache file path, shared by every caller in this process.

    `read()`+`write()` is a read-modify-write over the *whole* file, not a
    single key — two threads racing it (e.g. `fleet_overview` auditing
    several projects that share a target Magento version concurrently) can
    silently lose one side's update. Callers must wrap their whole
    read-check-fetch-write cycle in `with cache.lock_for(path):`, not just
    the write call, since the write isn't what needs protecting."""
    resolved = path.resolve()
    with _locks_guard:
        if resolved not in _locks:
            _locks[resolved] = threading.Lock()
        return _locks[resolved]


def read(path: Path) -> dict[str, Any]:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store), encoding="utf-8")


def is_fresh(entry: dict[str, Any], ttl: timedelta, timestamp_key: str = "fetched_at") -> bool:
    try:
        fetched_at = datetime.fromisoformat(entry[timestamp_key])
    except (KeyError, ValueError):
        return False
    return datetime.now(UTC) - fetched_at < ttl


def stamp(timestamp_key: str = "fetched_at") -> dict[str, str]:
    """A ready-to-merge `{timestamp_key: now}` entry for a freshly fetched value."""
    return {timestamp_key: datetime.now(UTC).isoformat()}
