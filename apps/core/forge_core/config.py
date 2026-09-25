"""Core configuration, entirely from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value else default


@dataclass(slots=True)
class CoreConfig:
    host: str
    port: int
    output_dir: Path
    ollama_base_url: str
    router_base_url: str
    comfyui_base_url: str
    searxng_base_url: str
    comfy_workflow: Path | None
    piper_bin: str
    piper_model: str | None
    whisper_bin: str
    whisper_model: str
    wan_command: str | None
    edge_voice: str


def load() -> CoreConfig:
    output = Path(_env("FORGE_OUTPUT_DIR", "outputs"))
    output.mkdir(parents=True, exist_ok=True)
    workflow = _env("FORGE_COMFY_WORKFLOW")
    return CoreConfig(
        host=_env("FORGE_CORE_HOST", "127.0.0.1") or "127.0.0.1",
        port=int(_env("FORGE_CORE_PORT", "4020") or "4020"),
        output_dir=output,
        ollama_base_url=_env("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1") or "",
        router_base_url=_env("FORGE_ROUTER_URL", "http://127.0.0.1:4010/v1") or "",
        comfyui_base_url=_env("COMFYUI_BASE_URL", "http://127.0.0.1:8188") or "",
        searxng_base_url=_env("SEARXNG_BASE_URL", "http://127.0.0.1:8080") or "",
        comfy_workflow=Path(workflow) if workflow else None,
        piper_bin=_env("FORGE_PIPER_BIN", "piper") or "piper",
        piper_model=_env("FORGE_PIPER_MODEL"),
        whisper_bin=_env("FORGE_WHISPER_BIN", "whisper") or "whisper",
        whisper_model=_env("FORGE_WHISPER_MODEL", "base") or "base",
        wan_command=_env("FORGE_WAN_COMMAND"),
        edge_voice=_env("FORGE_EDGE_VOICE", "en-US-AriaNeural") or "en-US-AriaNeural",
    )
