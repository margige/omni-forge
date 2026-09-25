"""Image generation backends.

`pollinations` needs no account and no GPU — it is the zero-config free default.
`comfyui` is the quality path: a local node graph you already trust.
`openrouter` provides text-to-image models via the dedicated Image API
(`POST /api/v1/images`), using the same OPENROUTER_API_KEY as the router.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import random
from urllib.parse import quote

import httpx

from ..config import CoreConfig
from ..util import dimensions, media_url, save_bytes
from .base import Backend


class PollinationsBackend(Backend):
    name = "pollinations"
    capability = "image"

    def __init__(self, config: CoreConfig):
        self.config = config
        self._client = httpx.AsyncClient(timeout=180, follow_redirects=True)

    async def run(self, *, prompt: str, aspect: str = "1:1", **_: object) -> dict:
        width, height = dimensions(aspect)
        url = (
            f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            f"?width={width}&height={height}&nologo=true"
        )
        response = await self._client.get(url)
        response.raise_for_status()
        path = save_bytes(self.config.output_dir, response.content, ".jpg", "image")
        return {
            "backend": self.name,
            "path": str(path),
            "url": media_url(path),
            "width": width,
            "height": height,
        }


class ComfyUIBackend(Backend):
    name = "comfyui"
    capability = "image"

    def __init__(self, config: CoreConfig):
        self.config = config
        self._client = httpx.AsyncClient(timeout=300)

    def available(self) -> bool:
        workflow = self.config.comfy_workflow
        return bool(workflow and workflow.is_file())

    def _render_workflow(self, prompt: str, aspect: str) -> dict:
        width, height = dimensions(aspect)
        raw = self.config.comfy_workflow.read_text(encoding="utf-8")  # type: ignore[union-attr]
        raw = (
            raw.replace("{prompt}", json.dumps(prompt)[1:-1])
            .replace("{width}", str(width))
            .replace("{height}", str(height))
            .replace("{seed}", str(random.randint(0, 2**31 - 1)))
        )
        return json.loads(raw)

    async def run(self, *, prompt: str, aspect: str = "1:1", **_: object) -> dict:
        workflow = self._render_workflow(prompt, aspect)
        client_id = f"omni-forge-{random.randint(0, 1 << 20)}"
        queued = await self._client.post(
            f"{self.config.comfyui_base_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        queued.raise_for_status()
        prompt_id = queued.json()["prompt_id"]

        history: dict = {}
        for _ in range(600):  # up to ~5 minutes
            await asyncio.sleep(0.5)
            response = await self._client.get(f"{self.config.comfyui_base_url}/history/{prompt_id}")
            history = response.json() or {}
            if prompt_id in history:
                break

        outputs = history.get(prompt_id, {}).get("outputs", {})
        for node in outputs.values():
            for image in node.get("images", []):
                view = await self._client.get(
                    f"{self.config.comfyui_base_url}/view",
                    params={
                        "filename": image["filename"],
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    },
                )
                view.raise_for_status()
                path = save_bytes(self.config.output_dir, view.content, ".png", "image")
                return {
                    "backend": self.name,
                    "path": str(path),
                    "url": media_url(path),
                    "prompt_id": prompt_id,
                }
        raise RuntimeError("comfyui produced no image output")


class OpenRouterImageBackend(Backend):
    name = "openrouter"
    capability = "image"
    _DEFAULT_MODEL = "bytedance-seed/seedream-4.5"

    def __init__(self, config: CoreConfig):
        self.config = config
        self._client = httpx.AsyncClient(timeout=120, follow_redirects=True)
        self._model = os.environ.get("OPENROUTER_IMAGE_MODEL") or self._DEFAULT_MODEL

    def available(self) -> bool:
        return bool(os.environ.get("OPENROUTER_API_KEY"))

    async def run(self, *, prompt: str, aspect: str = "1:1", model: str | None = None, **_: object) -> dict:
        slug = model or self._model
        payload: dict = {"model": slug, "prompt": prompt, "aspect_ratio": aspect}
        response = await self._client.post(
            "https://openrouter.ai/api/v1/images",
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        image = data["data"][0]
        raw = base64.b64decode(image["b64_json"])
        suffix = ".png"
        if image.get("media_type", "").endswith("jpeg"):
            suffix = ".jpg"
        elif image.get("media_type", "").endswith("webp"):
            suffix = ".webp"
        path = save_bytes(self.config.output_dir, raw, suffix, "image")
        return {
            "backend": self.name,
            "path": str(path),
            "url": media_url(path),
            "width": image.get("width"),
            "height": image.get("height"),
        }
