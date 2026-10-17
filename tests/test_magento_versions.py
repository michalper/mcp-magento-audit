import json
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest

from mcp_magento_audit import magento_versions as mv


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(mv, "CACHE_PATH", tmp_path / "magento_php.json")


def _write_cache(entries: dict) -> None:
    mv.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    mv.CACHE_PATH.write_text(json.dumps(entries), encoding="utf-8")


def _broken_fetch(url: str) -> str:
    raise urllib.error.URLError("boom")


def test_fresh_cache_is_used_without_fetching(monkeypatch):
    _write_cache(
        {
            "2.4.7": {
                "php_requirement": "~8.2.0||~8.3.0",
                "fetched_at": datetime.now(UTC).isoformat(),
            }
        }
    )

    def fail_fetch(url: str) -> str:
        raise AssertionError("should not fetch when cache is fresh")

    monkeypatch.setattr(mv, "_fetch", fail_fetch)

    result = mv.php_requirement_for_magento("2.4.7")
    assert result.source == "cache"
    assert result.php_requirement == "~8.2.0||~8.3.0"


def test_missing_cache_fetches_live_and_writes_cache(monkeypatch):
    monkeypatch.setattr(
        mv, "_fetch", lambda url: json.dumps({"require": {"php": "~8.1.0||~8.2.0"}})
    )

    result = mv.php_requirement_for_magento("2.4.6")
    assert result.source == "live"
    assert result.php_requirement == "~8.1.0||~8.2.0"

    cached = json.loads(mv.CACHE_PATH.read_text(encoding="utf-8"))
    assert cached["2.4.6"]["php_requirement"] == "~8.1.0||~8.2.0"


def test_fetch_failure_falls_back_to_stale_cache(monkeypatch):
    stale_time = datetime.now(UTC) - timedelta(days=30)
    _write_cache({"2.4.7": {"php_requirement": "~8.2.0", "fetched_at": stale_time.isoformat()}})

    monkeypatch.setattr(mv, "_fetch", _broken_fetch)

    result = mv.php_requirement_for_magento("2.4.7")
    assert result.source == "cache"
    assert result.php_requirement == "~8.2.0"


def test_fetch_failure_and_no_cache_falls_back_to_hardcoded_table(monkeypatch):
    monkeypatch.setattr(mv, "_fetch", _broken_fetch)

    result = mv.php_requirement_for_magento("2.4.7")
    assert result.source == "hardcoded"
    assert result.php_requirement == mv.PHP_TABLE["2.4.7"]


def test_unknown_version_without_any_source(monkeypatch):
    monkeypatch.setattr(mv, "_fetch", _broken_fetch)

    result = mv.php_requirement_for_magento("1.0.0")
    assert result.source == "unknown"
    assert result.php_requirement is None
