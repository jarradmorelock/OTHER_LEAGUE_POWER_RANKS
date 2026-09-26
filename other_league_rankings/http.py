"""Bounded-retry HTTP access for public data feeds."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

class DataSourceError(RuntimeError):
    """Raised when a remote source cannot provide usable data."""


class HttpClient:
    def __init__(self, timeout: int = 30, session: Any = None) -> None:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        self.timeout = timeout
        self.session = session or requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({"User-Agent": "Other-League-Power-Ranks/1.0"})

    def get_json(self, url: str) -> Any:
        import requests

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            # Report only the host; future feeds may include sensitive query strings.
            host = urlsplit(url).netloc or "remote source"
            raise DataSourceError(f"GET failed for {host}: {exc}") from exc
