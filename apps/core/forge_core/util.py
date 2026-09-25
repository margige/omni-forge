"""Shared helpers for the core service."""

from __future__ import annotations

import secrets
import time
from pathlib import Path

ASPECTS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
}


def dimensions(aspect: str) -> tuple[int, int]:
    return ASPECTS.get(aspect, ASPECTS["1:1"])


def save_bytes(output_dir: Path, data: bytes, suffix: str, stem: str = "gen") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"{stem}-{int(time.time())}-{secrets.token_hex(3)}{suffix}"
    path = output_dir / name
    path.write_bytes(data)
    return path


def media_url(path: Path) -> str:
    return f"/media/{path.name}"
