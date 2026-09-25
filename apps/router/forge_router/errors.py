"""Typed router errors."""

from __future__ import annotations

from typing import Any

QUOTA_MARKERS = (
    "rate limit",
    "quota exceeded",
    "too many requests",
    "insufficient_quota",
    "billing",
    "credit balance",
    "429",
    "402",
)


class NoProviderAvailable(Exception):
    def __init__(self, detail: dict[str, Any] | None = None) -> None:
        self.detail = detail or {}
        super().__init__("no provider available")


def is_quota_error(status: int, body: str) -> bool:
    if status in (402, 429):
        return True
    lowered = body.lower()
    return any(marker in lowered for marker in QUOTA_MARKERS)


def is_retryable(status: int) -> bool:
    return status >= 500 or status in (408, 425)