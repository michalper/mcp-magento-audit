from datetime import timedelta

from mcp_magento_audit import cache


def test_read_missing_file_returns_empty_dict(tmp_path):
    assert cache.read(tmp_path / "missing.json") == {}


def test_read_corrupt_json_returns_empty_dict(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("not json")
    assert cache.read(path) == {}


def test_read_non_object_json_returns_empty_dict(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("[1, 2, 3]")
    assert cache.read(path) == {}


def test_write_then_read_round_trip(tmp_path):
    path = tmp_path / "nested" / "cache.json"
    cache.write(path, {"foo": {"value": 1}})
    assert cache.read(path) == {"foo": {"value": 1}}


def test_is_fresh_entry_within_ttl():
    entry = cache.stamp()
    assert cache.is_fresh(entry, timedelta(days=1)) is True


def test_is_fresh_entry_outside_ttl():
    entry = cache.stamp()
    assert cache.is_fresh(entry, timedelta(seconds=-1)) is False


def test_is_fresh_missing_timestamp_is_false():
    assert cache.is_fresh({}, timedelta(days=1)) is False


def test_is_fresh_invalid_timestamp_is_false():
    assert cache.is_fresh({"fetched_at": "not-a-date"}, timedelta(days=1)) is False
