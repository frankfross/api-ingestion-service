"""End-to-end test: fake API -> real SQLite store, run twice for idempotency."""
from api_ingest.client import PaginatedClient
from api_ingest.run import run_pipeline


class FakeClient(PaginatedClient):
    def __init__(self, pages):
        self._pages = pages

    def fetch_page(self, page):
        return self._pages[page - 1] if page <= len(self._pages) else []


def _cfg(tmp_path):
    return {
        "api": {"base_url": "https://x", "page_size": 2, "max_retries": 1},
        "db": {"dsn": str(tmp_path / "e2e.db")},
    }


def test_end_to_end_idempotent(tmp_path):
    pages = [
        [{"id": "1", "v": "a"}, {"id": "2", "v": "b"}, {"no": "id"}],
        [{"id": "3", "v": "c"}],
    ]
    report = run_pipeline(_cfg(tmp_path), client=FakeClient(pages))
    assert report["pages_fetched"] == 2
    assert report["records_seen"] == 3
    assert report["inserted"] == 3
    assert report["updated"] == 0
    assert report["skipped_no_id"] == 1
    assert report["total_rows"] == 3

    # second run: everything is an update, row count unchanged
    report2 = run_pipeline(_cfg(tmp_path), client=FakeClient(pages))
    assert report2["inserted"] == 0
    assert report2["updated"] == 3
    assert report2["total_rows"] == 3
