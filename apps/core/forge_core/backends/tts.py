"""Text-to-speech backends.

`edge-tts` is free and needs no key — the default. `piper` is fully offline.
Both write a file and return its URL.
"""

from __future__ import annotations

import asyncio
import shutil

from ..config import CoreConfig
from ..util import media_url, save_bytes
from .base import Backend


class EdgeTTSBackend(Backend):
    name = "edge-tts"
    capability = "tts"

    def __init__(self, config: CoreConfig):
        self.config = config

    def available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False
        return True

    async def run(self, *, text: str, voice: str | None = None, **_: object) -> dict:
        import edge_tts

        voice = voice or self.config.edge_voice
        audio = b""
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        path = save_bytes(self.config.output_dir, audio, ".mp3", "speech")
        return {"backend": self.name, "path": str(path), "url": media_url(path), "voice": voice}


class PiperBackend(Backend):
    name = "piper"
    capability = "tts"

    def __init__(self, config: CoreConfig):
        self.config = config

    def available(self) -> bool:
        return bool(self.config.piper_model) and shutil.which(self.config.piper_bin) is not None

    async def run(self, *, text: str, **_: object) -> dict:
        model = self.config.piper_model
        assert model and self.config.piper_bin
        proc = await asyncio.create_subprocess_exec(
            self.config.piper_bin,
            "--model",
            model,
            "--output_file",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(text.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(f"piper failed: {stderr.decode('utf-8', 'replace')}")
        path = save_bytes(self.config.output_dir, stdout, ".wav", "speech")
        return {"backend": self.name, "path": str(path), "url": media_url(path), "voice": model}
