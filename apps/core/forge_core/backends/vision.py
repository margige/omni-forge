"""Vision: describe or answer questions about an image through a VLM.

Routes to the local free router, so whichever vision-capable model is healthy
serves the request.
"""

from __future__ import annotations

import base64

import httpx

from ..config import CoreConfig
from .base import Backend


class VisionBackend(Backend):
    name = "vision"
    capability = "vision"

    def __init__(self, config: CoreConfig):
        self.config = config
        self._client = httpx.AsyncClient(timeout=180)

    async def run(self, *, image: bytes, prompt: str, mime: str = "image/png", **_: object) -> dict:
        data_uri = f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"
        payload = {
            "model": "forge-chat",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        }
        response = await self._client.post(
            f"{self.config.router_base_url}/chat/completions", json=payload
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        return {"backend": self.name, "text": text, "provider": data.get("_forge", {}).get("provider")}
