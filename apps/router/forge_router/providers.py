"""Runtime provider wrapper: URL, headers, model and payload shaping."""

from __future__ import annotations

import asyncio
import time
from collections import deque

from .config import ProviderConfig


class Provider:
    def __init__(self, cfg: ProviderConfig) -> None:
        self.cfg = cfg
        self.name = cfg.name
        self._window: deque[float] = deque()
        self._rpm_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return self.cfg.base_url

    @property
    def resolved(self) -> bool:
        return self.cfg.resolved

    def chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.cfg.api_key:
            headers["authorization"] = f"Bearer {self.cfg.api_key}"
        return headers

    def rpm_ok(self, now: float | None = None) -> bool:
        if not self.cfg.rpm:
            return True
        cutoff = (now or time.time()) - 60
        while self._window and self._window[0] < cutoff:
            self._window.popleft()
        return len(self._window) < self.cfg.rpm

    def note_request(self, now: float | None = None) -> None:
        self._window.append(now or time.time())

    async def reserve(self, now: float | None = None) -> bool:
        """Atomically claim one slot of the rpm window.

        `rpm_ok` alone races: N concurrent calls can all pass the check and then
        all append, overshooting the limit. The check and the append must be
        mutually exclusive, so a burst can only ever reserve up to rpm slots.
        """
        if not self.cfg.rpm:
            self.note_request(now)
            return True
        async with self._rpm_lock:
            if not self.rpm_ok(now):
                return False
            self.note_request(now)
            return True

    def requests_last_minute(self, now: float | None = None) -> int:
        cutoff = (now or time.time()) - 60
        return len([s for s in self._window if s >= cutoff])

    def default_model(self, requested: str | None = None) -> str:
        if requested and requested != "forge-chat":
            if not self.cfg.models or requested in self.cfg.models:
                return requested
        if self.cfg.models:
            return self.cfg.models[0]
        return requested or "forge-chat"

    def build_payload(self, payload: dict, model: str) -> dict:
        body = {k: v for k, v in payload.items() if k != "stream"}
        body["model"] = model
        return body