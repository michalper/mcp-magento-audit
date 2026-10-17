import threading
import time
from datetime import timedelta
from pathlib import Path

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


def test_lock_for_same_path_is_the_same_lock_object():
    assert cache.lock_for(Path("/tmp/a.json")) is cache.lock_for(Path("/tmp/a.json"))


def test_lock_for_serializes_concurrent_read_modify_write(tmp_path):
    # Simulates fleet_overview's concurrent callers racing the same cache
    # file: without the lock, each thread's read-sleep-write would race the
    # others' and lose updates. A short sleep between read and write widens
    # the window a missing lock would race in.
    path = tmp_path / "cache.json"
    cache.write(path, {"counter": 0})

    def bump() -> None:
        with cache.lock_for(path):
            store = cache.read(path)
            store["counter"] = store["counter"] + 1
            time.sleep(0.001)
            cache.write(path, store)

    threads = [threading.Thread(target=bump) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert cache.read(path)["counter"] == 20


def test_is_fresh_invalid_timestamp_is_false():
    assert cache.is_fresh({"fetched_at": "not-a-date"}, timedelta(days=1)) is False
