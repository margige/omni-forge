"""Video generation via a local Wan 2.1 (or compatible) command.

Video is slow and GPU-bound, so the core exposes it as a job. The backend is an
adapter around any command that renders a file; configure it with
`FORGE_WAN_COMMAND` using `{prompt}` and `{out}` placeholders.
"""

from __future__ import annotations

import asyncio
import shlex
import shutil
import time
from pathlib import Path

from ..config import CoreConfig
from ..util import media_url
from .base import Backend


class WanBackend(Backend):
    name = "wan"
    capability = "video"

    def __init__(self, config: CoreConfig):
        self.config = config

    def available(self) -> bool:
        return bool(self.config.wan_command)

    async def run(self, *, prompt: str, **_: object) -> dict:
        assert self.config.wan_command
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        out = self.config.output_dir / f"video-{int(time.time())}.mp4"
        command = self.config.wan_command.format(prompt=shlex.quote(prompt), out=shlex.quote(str(out)))
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not out.is_file():
            raise RuntimeError(f"video command failed: {stderr.decode('utf-8', 'replace')[-500:]}")
        return {"backend": self.name, "path": str(out), "url": media_url(out)}
