"""Tests for the idempotent record store (SQLite)."""
import pytest

from api_ingest.store import RecordStore


@pytest.fixture
def store(tmp_path):
    s = RecordStore(dsn=str(tmp_path / "test.db"))
    s.init_schema()
    yield s
    s.close()


def test_upsert_counts_inserts_and_updates(store):
    assert store.upsert([{"id": "a", "v": 1}, {"id": "b", "v": 2}]) == (2, 0)
    # same ids again: all updates, no new rows
    assert store.upsert([{"id": "a", "v": 10}, {"id": "b", "v": 2}]) == (0, 2)
    assert store.count() == 2


def test_upsert_updates_payload(store):
    store.upsert([{"id": "a", "v": 1}])
    store.upsert([{"id": "a", "v": 99}])
    assert store.get("a")["v"] == 99


def test_get_missing_returns_none(store):
    assert store.get("nope") is None
