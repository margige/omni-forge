"""Speech-to-text via Whisper (openai-whisper or faster-whisper CLI)."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from ..config import CoreConfig
from .base import Backend


class WhisperBackend(Backend):
    name = "whisper"
    capability = "asr"

    def __init__(self, config: CoreConfig):
        self.config = config

    def available(self) -> bool:
        return shutil.which(self.config.whisper_bin) is not None

    async def run(self, *, audio: bytes, suffix: str = ".wav", language: str | None = None, **_: object) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"input{suffix}"
            src.write_bytes(audio)
            cmd = [self.config.whisper_bin, str(src), "--model", self.config.whisper_model, "--output_format", "json", "--output_dir", tmp]
            if language:
                cmd += ["--language", language]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"whisper failed: {stderr.decode('utf-8', 'replace')}")
            out = Path(tmp) / f"input.json"
            data = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
        return {
            "backend": self.name,
            "text": data.get("text", "").strip(),
            "segments": data.get("segments", []),
            "language": data.get("language"),
        }
