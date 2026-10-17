"""Generic JSON file TTL cache — one JSON object per cache file, keyed by
whatever string the caller wants (a version, a URL, ...). No knowledge of
Magento, Composer or any specific domain, so any tool here that needs to
remember something between calls can reuse it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


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
