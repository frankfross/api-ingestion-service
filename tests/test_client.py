"""Tests for the paginated REST client (no network — canned sessions)."""
import pytest

from api_ingest.client import FatalError, PaginatedClient, TransientError


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    """Replays a scripted list of responses, recording calls."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _page(records):
    return FakeResponse(200, {"records": records})


def test_pagination_stops_at_empty_page():
    session = FakeSession(
        [
            _page([{"id": 1}, {"id": 2}]),
            _page([{"id": 3}]),
            _page([]),
        ]
    )
    client = PaginatedClient("https://api.example.com/v1/x", session=session)
    assert list(client.fetch_all()) == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert [c[1]["page"] for c in session.calls] == [1, 2, 3]


def test_retries_on_429_then_succeeds():
    session = FakeSession(
        [FakeResponse(429), FakeResponse(500), _page([{"id": 9}])]
    )
    client = PaginatedClient(
        "https://api.example.com/v1/x", max_retries=3, session=session
    )
    assert client.fetch_page(1) == [{"id": 9}]
    assert len(session.calls) == 3  # two transient failures, then success


def test_gives_up_after_max_retries():
    session = FakeSession([FakeResponse(500)] * 5)
    client = PaginatedClient(
        "https://api.example.com/v1/x", max_retries=2, session=session
    )
    with pytest.raises(TransientError):
        client.fetch_page(1)
    assert len(session.calls) == 3  # initial + 2 retries


def test_404_fails_fast_without_retry():
    session = FakeSession([FakeResponse(404, {"error": "nope"})])
    client = PaginatedClient("https://api.example.com/v1/x", session=session)
    with pytest.raises(FatalError):
        client.fetch_page(1)
    assert len(session.calls) == 1
