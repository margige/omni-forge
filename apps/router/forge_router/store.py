"""SQLite-backed usage ledger: requests, tokens, errors, cooldowns."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    provider TEXT NOT NULL,
    day TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, day)
);
CREATE TABLE IF NOT EXISTS cooldowns (
    provider TEXT PRIMARY KEY,
    until REAL NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS keys (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    added REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
"""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _window() -> list[float]:
    now = time.time()
    return [now - 60, now]


class UsageLedger:
    def __init__(self, path: str = ":memory:") -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()
        self._recent: dict[str, list[float]] = {}

    # ── writes ───────────────────────────────────────────────────────────
    def record_success(self, provider: str, tokens: int = 0) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO usage (provider, day, requests, tokens, errors) VALUES (?, ?, 1, ?, 0) "
                "ON CONFLICT(provider, day) DO UPDATE SET requests = requests + 1, tokens = tokens + ?",
                (provider, _today(), tokens, tokens),
            )
            self._db.commit()
        self._recent.setdefault(provider, []).append(time.time())

    def record_error(self, provider: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO usage (provider, day, requests, tokens, errors) VALUES (?, ?, 0, 0, 1) "
                "ON CONFLICT(provider, day) DO UPDATE SET errors = errors + 1",
                (provider, _today()),
            )
            self._db.commit()

    def set_cooldown(self, provider: str, seconds: int, reason: str = "") -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO cooldowns (provider, until, reason) VALUES (?, ?, ?) "
                "ON CONFLICT(provider) DO UPDATE SET until = excluded.until, reason = excluded.reason",
                (provider, time.time() + seconds, reason),
            )
            self._db.commit()

    # ── reads ────────────────────────────────────────────────────────────
    def requests_today(self, provider: str) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT requests FROM usage WHERE provider = ? AND day = ?",
                (provider, _today()),
            ).fetchone()
        return int(row["requests"]) if row else 0

    def tokens_today(self, provider: str) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT tokens FROM usage WHERE provider = ? AND day = ?",
                (provider, _today()),
            ).fetchone()
        return int(row["tokens"]) if row else 0

    def errors_today(self, provider: str) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT errors FROM usage WHERE provider = ? AND day = ?",
                (provider, _today()),
            ).fetchone()
        return int(row["errors"]) if row else 0

    def cooldown_remaining(self, provider: str, now: float | None = None) -> float:
        with self._lock:
            row = self._db.execute(
                "SELECT until FROM cooldowns WHERE provider = ?", (provider,)
            ).fetchone()
        return max(0.0, float(row["until"]) - (now or time.time())) if row else 0.0

    def is_cooling(self, provider: str, now: float | None = None) -> bool:
        return self.cooldown_remaining(provider, now) > 0.0

    def cooldown_reason(self, provider: str) -> str:
        with self._lock:
            row = self._db.execute(
                "SELECT reason FROM cooldowns WHERE provider = ?", (provider,)
            ).fetchone()
        return str(row["reason"]) if row and row["reason"] else ""

    def requests_in_window(self, provider: str) -> int:
        start, end = _window()
        stamps = [s for s in self._recent.get(provider, []) if start <= s <= end]
        self._recent[provider] = stamps
        return len(stamps)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT provider, requests, tokens, errors FROM usage WHERE day = ?", (_today(),)
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(dict(row))
        return out

    # ── key pool (optional, off by default) ──────────────────────────────
    @staticmethod
    def _key_id(provider: str, key: str) -> str:
        return hashlib.sha256(f"{provider}:{key}".encode()).hexdigest()[:16]

    def add_key(self, provider: str, key: str) -> str:
        key_id = self._key_id(provider, key)
        with self._lock:
            self._db.execute(
                "INSERT INTO keys (id, provider, added) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO NOTHING",
                (key_id, provider, time.time()),
            )
            self._db.commit()
        return key_id

    def close(self) -> None:
        with self._lock:
            self._db.close()