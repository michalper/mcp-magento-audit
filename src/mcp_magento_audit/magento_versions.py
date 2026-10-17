"""PHP requirement for a given Magento version.

Three layers, in order of preference: a fresh local cache, a live fetch from
the magento/magento2 GitHub repo (its composer.json per tag declares the PHP
requirement), and a small hardcoded table as the offline fallback.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PHP_TABLE: dict[str, str] = {
    "2.4.7": "~8.1.0||~8.2.0||~8.3.0",
    "2.4.6": "~8.1.0||~8.2.0",
    "2.4.5": "~7.4.0||~8.1.0",
}

CACHE_PATH = Path.home() / ".cache" / "mcp-magento-audit" / "magento_php.json"
CACHE_TTL = timedelta(days=7)


@dataclass(frozen=True)
class PhpRequirement:
    php_requirement: str | None
    source: str  # "hardcoded" | "cache" | "live" | "unknown"


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
        body: bytes = response.read()
        return body.decode("utf-8")


def _fetch_php_requirement(version: str) -> str | None:
    url = f"https://raw.githubusercontent.com/magento/magento2/{version}/composer.json"
    try:
        data: Any = json.loads(_fetch(url))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return (data.get("require") or {}).get("php")


def _read_cache() -> dict[str, Any]:
    try:
        data: Any = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


def _is_fresh(entry: dict[str, Any]) -> bool:
    try:
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
    except (KeyError, ValueError):
        return False
    return datetime.now(UTC) - fetched_at < CACHE_TTL


def php_requirement_for_magento(version: str) -> PhpRequirement:
    cache = _read_cache()
    entry = cache.get(version)

    if entry and _is_fresh(entry):
        return PhpRequirement(php_requirement=entry.get("php_requirement"), source="cache")

    fetched = _fetch_php_requirement(version)
    if fetched is not None:
        cache[version] = {
            "php_requirement": fetched,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        _write_cache(cache)
        return PhpRequirement(php_requirement=fetched, source="live")

    if entry:
        return PhpRequirement(php_requirement=entry.get("php_requirement"), source="cache")

    if version in PHP_TABLE:
        return PhpRequirement(php_requirement=PHP_TABLE[version], source="hardcoded")

    return PhpRequirement(php_requirement=None, source="unknown")
