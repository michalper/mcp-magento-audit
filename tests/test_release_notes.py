import json
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest

from mcp_magento_audit import release_notes as rn


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(rn, "CACHE_PATH", tmp_path / "release_notes.json")


def _write_cache(entries: dict) -> None:
    rn.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    rn.CACHE_PATH.write_text(json.dumps(entries), encoding="utf-8")


def _broken_fetch(url: str) -> str:
    raise urllib.error.URLError("boom")


def test_live_fetch_is_cached_and_returned(monkeypatch):
    payload = {
        "html_url": "https://github.com/magento/magento2/releases/tag/2.4.7",
        "published_at": "2023-03-14T00:00:00Z",
        "body": "## Highlights\n...",
    }
    monkeypatch.setattr(rn, "_fetch", lambda url: json.dumps(payload))

    result = rn.release_notes_for_version("2.4.7")

    assert result.found is True
    assert result.source == "live"
    assert result.url == payload["html_url"]
    assert result.notes == payload["body"]

    cached = json.loads(rn.CACHE_PATH.read_text(encoding="utf-8"))
    assert cached["2.4.7"]["notes"] == payload["body"]


def test_fresh_cache_is_used_without_fetching(monkeypatch):
    _write_cache(
        {
            "2.4.7": {
                "url": "https://example.test",
                "published_at": "2023-03-14T00:00:00Z",
                "notes": "cached notes",
                "fetched_at": datetime.now(UTC).isoformat(),
            }
        }
    )

    def fail_fetch(url: str) -> str:
        raise AssertionError("should not fetch when cache is fresh")

    monkeypatch.setattr(rn, "_fetch", fail_fetch)

    result = rn.release_notes_for_version("2.4.7")
    assert result.source == "cache"
    assert result.notes == "cached notes"


def test_fetch_failure_falls_back_to_stale_cache(monkeypatch):
    stale_time = datetime.now(UTC) - timedelta(days=30)
    _write_cache(
        {
            "2.4.7": {
                "url": "https://example.test",
                "published_at": "2023-03-14T00:00:00Z",
                "notes": "stale notes",
                "fetched_at": stale_time.isoformat(),
            }
        }
    )
    monkeypatch.setattr(rn, "_fetch", _broken_fetch)

    result = rn.release_notes_for_version("2.4.7")
    assert result.source == "cache"
    assert result.notes == "stale notes"


def test_fetch_failure_and_no_cache_is_unavailable(monkeypatch):
    monkeypatch.setattr(rn, "_fetch", _broken_fetch)

    result = rn.release_notes_for_version("0.0.0")

    assert result.found is False
    assert result.source == "unavailable"
    assert result.notes is None
    assert "0.0.0" in result.reason
