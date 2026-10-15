"""Minimal Oura API v2 client: bearer auth, `next_token` pagination, polite retries.

- 429: waits `Retry-After` seconds (Oura's guidance), then retries.
- 5xx / network errors: exponential backoff.
- 401: refreshes the token once.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator

API = "https://api.ouraring.com"
MAX_ATTEMPTS = 6


class OuraApiError(RuntimeError):
    def __init__(self, status: int, path: str, body: str):
        super().__init__(f"{status} on {path}: {body[:300]}")
        self.status = status


Opener = Callable[[urllib.request.Request], tuple[int, dict, bytes]]


def _urlopen(req: urllib.request.Request) -> tuple[int, dict, bytes]:
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


class OuraClient:
    def __init__(
        self, token: Callable[[], str], opener: Opener = _urlopen, sleep: Callable[[float], None] = time.sleep
    ):
        self._token = token
        self._open = opener
        self._sleep = sleep
        self.requests = 0

    def get(self, path: str, params: dict | None = None) -> dict:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{API}{path}{'?' + query if query else ''}"
        refreshed = False
        for attempt in range(MAX_ATTEMPTS):
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}
            )
            self.requests += 1
            status, headers, body = self._open(req)
            if status == 200:
                return json.loads(body)
            if status == 401 and not refreshed:
                refreshed = True  # token() refreshes when expired; one retry covers a just-expired token
                continue
            if status == 429:
                retry_after = float({k.lower(): v for k, v in headers.items()}.get("retry-after", 2**attempt))
                self._sleep(min(retry_after, 120))
                continue
            if status >= 500:
                self._sleep(min(2**attempt, 30))
                continue
            raise OuraApiError(status, path, body.decode(errors="replace"))
        raise OuraApiError(status, path, "gave up after retries")

    def paginate(self, path: str, params: dict) -> Iterator[dict]:
        """Yield every document across `next_token` pages."""
        token = None
        while True:
            page = self.get(path, params | {"next_token": token})
            yield from page.get("data", [])
            token = page.get("next_token")
            if not token:
                return
