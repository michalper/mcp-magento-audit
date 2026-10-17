"""Magento's own release notes for a given version.

Fetched from the magento/magento2 GitHub repo's Releases API — never
reconstructed from training data. Unlike `magento_versions.py`, there is no
hardcoded fallback table here: that's the whole point of this tool (the
README's own mandate is "don't answer from the model's memory"), so a
failed fetch is reported as `found=False` with a reason, never invented.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from . import cache

CACHE_PATH = Path.home() / ".cache" / "mcp-magento-audit" / "release_notes.json"
CACHE_TTL = timedelta(days=7)


@dataclass(frozen=True)
class ReleaseNotes:
    found: bool
    source: str  # "cache" | "live" | "unavailable"
    url: str | None
    published_at: str | None
    notes: str | None
    reason: str | None


def _fetch(url: str) -> str:
    headers = {"User-Agent": "mcp-magento-audit", "Accept": "application/vnd.github+json"}
    # Unauthenticated GitHub REST API calls are capped at 60/hour per IP —
    # easy to hit for a shared office/CI IP running fleet_overview/upgrade_plan
    # across many projects. An optional token raises that to 5000/hour; this
    # only ever reads public release data, so a read-only, no-scope token is
    # enough.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310
        body: bytes = response.read()
        return body.decode("utf-8")


def _fetch_from_github(version: str) -> dict[str, Any] | None:
    safe_version = urllib.parse.quote(version, safe="")
    url = f"https://api.github.com/repos/magento/magento2/releases/tags/{safe_version}"
    try:
        data: Any = json.loads(_fetch(url))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _from_entry(entry: dict[str, Any], source: str) -> ReleaseNotes:
    return ReleaseNotes(
        found=True,
        source=source,
        url=entry.get("url"),
        published_at=entry.get("published_at"),
        notes=entry.get("notes"),
        reason=None,
    )


def release_notes_for_version(version: str) -> ReleaseNotes:
    with cache.lock_for(CACHE_PATH):
        store = cache.read(CACHE_PATH)
        entry = store.get(version)

        if entry and cache.is_fresh(entry, CACHE_TTL):
            return _from_entry(entry, "cache")

        data = _fetch_from_github(version)
        if data is not None:
            payload = {
                "url": data.get("html_url"),
                "published_at": data.get("published_at"),
                "notes": data.get("body"),
            }
            store[version] = {**payload, **cache.stamp()}
            cache.write(CACHE_PATH, store)
            return _from_entry(store[version], "live")

        if entry:
            return _from_entry(entry, "cache")

    return ReleaseNotes(
        found=False,
        source="unavailable",
        url=None,
        published_at=None,
        notes=None,
        reason=f"could not fetch release notes for Magento {version} from GitHub",
    )
