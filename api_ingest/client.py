"""Paginated REST client with explicit retry behavior.

Transient failures (429, 5xx) are retried with exponential backoff.
Other 4xx responses fail immediately — retrying them is pointless.
"""
from __future__ import annotations

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class TransientError(Exception):
    """Retryable: rate-limited or server-side failure."""


class FatalError(Exception):
    """Not retryable: the request itself is wrong."""


class PaginatedClient:
    def __init__(self, base_url: str, page_size: int = 100,
                 max_retries: int = 3, session=None):
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.session = session or requests.Session()
        self._get = self._make_getter(max_retries)

    def _make_getter(self, max_retries: int):
        @retry(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(TransientError),
            reraise=True,
        )
        def _get(url: str, params: dict):
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise TransientError(f"transient HTTP {resp.status_code}")
            if resp.status_code >= 400:
                raise FatalError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return resp.json()

        return _get

    def fetch_page(self, page: int) -> list[dict]:
        data = self._get(
            self.base_url, {"page": page, "page_size": self.page_size}
        )
        return data.get("records", [])

    def fetch_all(self):
        """Yield records across pages until an empty page."""
        page = 1
        while True:
            records = self.fetch_page(page)
            if not records:
                return
            yield from records
            page += 1
