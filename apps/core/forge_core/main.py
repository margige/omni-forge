"""Forge Core HTTP surface: image, video, tts, asr, vision, search."""

from __future__ import annotations

import base64
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__ as VERSION
from .backends import Registry
from .backends import asr as asr_backends
from .backends import image as image_backends
from .backends import search as search_backends
from .backends import tts as tts_backends
from .backends import video as video_backends
from .backends import vision as vision_backends
from .config import load as load_config
from .jobs import JobStore

config = load_config()
app = FastAPI(title="omni-forge core", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.registry = Registry()
app.state.jobs = JobStore()

app.state.registry.register(image_backends.PollinationsBackend(config))
app.state.registry.register(image_backends.ComfyUIBackend(config))
app.state.registry.register(video_backends.WanBackend(config))
app.state.registry.register(tts_backends.EdgeTTSBackend(config))
app.state.registry.register(tts_backends.PiperBackend(config))
app.state.registry.register(asr_backends.WhisperBackend(config))
app.state.registry.register(search_backends.SearXNGSearchBackend(config))
app.state.registry.register(search_backends.DuckDuckGoSearchBackend(config))
app.state.registry.register(search_backends.BingSearchBackend(config))
app.state.registry.register(image_backends.OpenRouterImageBackend(config))
app.state.registry.register(vision_backends.VisionBackend(config))

app.mount("/media", StaticFiles(directory=str(config.output_dir)), name="media")

#: Router URL for prompt-enrichment LLM calls; empty disables enrichment.
_ROUTER_URL = os.environ.get("FORGE_ROUTER_URL", "http://127.0.0.1:4010")

_PROMPT_ENHANCE_SYSTEM = (
    "You are an expert image-generation prompt engineer. "
    "Given the user's brief description, expand it into a rich, highly detailed "
    "image-generation prompt that covers: main subject and its appearance, "
    "setting and environment, lighting (type, direction, color), composition "
    "(framing, angle, depth of field), color palette and mood, artistic style "
    "(medium, reference artists if applicable), and technical details "
    "(resolution, rendering style). "
    "Return ONLY the expanded prompt as plain text — no explanation, no tags, no prefix."
)

async def _enrich_prompt(text: str) -> str:
    """Expand a brief prompt into a richly described one via the router LLM.

    Falls back to the original text on any error so image generation is never
    blocked by the enrichment step.
    """
    if not _ROUTER_URL:
        return text
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_ROUTER_URL}/v1/chat/completions",
                json={
                    "model": "forge-chat",
                    "messages": [
                        {"role": "system", "content": _PROMPT_ENHANCE_SYSTEM},
                        {"role": "user", "content": text},
                    ],
                    "max_tokens": 256,
                    "temperature": 0.7,
                },
            )
            if resp.status_code != 200:
                return text
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return content if content else text
    except Exception:  # noqa: BLE001 - fall back to original prompt
        return text


def _registry(request: Request) -> Registry:
    return request.app.state.registry


async def _run_chain(registry: Registry, capability: str, name: str | None = None, **kwargs) -> dict:
    """Try each registered backend for a capability, falling through on failure."""
    last: Exception | None = None
    for backend in registry.all(capability):
        if name and backend.name != name:
            continue
        if not backend.available():
            continue
        try:
            return await backend.run(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface the last failure
            last = exc
    raise HTTPException(
        status_code=503,
        detail=f"all '{capability}' backends failed" + (f": {last}" if last else ""),
    )


class ImageRequest(BaseModel):
    prompt: str
    aspect: str = "1:1"
    backend: str | None = None
    model: str | None = None


class TTSRequest(BaseModel):
    text: str
    voice: str | None = None
    backend: str | None = None


class VisionRequest(BaseModel):
    prompt: str = "Describe this image in detail."
    image_base64: str | None = None
    image_url: str | None = None


class VideoRequest(BaseModel):
    prompt: str


@app.get("/")
async def root() -> dict:
    return {"service": "forge-core", "version": VERSION, "capabilities": sorted(_registry(app).describe())}


@app.get("/forge/health")
async def health() -> dict:
    return {
        "ok": True,
        "output_dir": str(config.output_dir),
        "capabilities": app.state.registry.describe(),
    }


@app.post("/v1/image")
async def create_image(body: ImageRequest, request: Request) -> dict:
    """Generate an image.

    The prompt is first expanded by the router LLM into a richly detailed
    description (subject, lighting, composition, mood, style, medium) so
    the image backend produces a deeply-understood result. If enrichment
    fails or the router is unavailable the original prompt is used.

    If the caller explicitly forced a paid backend (e.g. OpenRouter) and that
    backend rejects the request because credits are required, fall back to the
    free default backend automatically and surface the note to the caller.
    """
    prompt = await _enrich_prompt(body.prompt)
    backend = body.backend
    try:
        return await _run_chain(_registry(request), "image", backend, prompt=prompt, aspect=body.aspect, model=body.model)
    except HTTPException as exc:
        if exc.status_code == 503 and backend and "payment" in str(exc.detail).lower():
            result = await _run_chain(_registry(request), "image", None, prompt=prompt, aspect=body.aspect, model=body.model)
            result["_note"] = "OpenRouter image generation requires paid credits — served by the free default backend instead."
            return result
        raise


@app.post("/v1/tts")
async def create_speech(body: TTSRequest, request: Request) -> dict:
    return await _run_chain(_registry(request), "tts", body.backend, text=body.text, voice=body.voice)


@app.post("/v1/asr")
async def transcribe_audio(request: Request) -> dict:
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        raise HTTPException(status_code=400, detail="multipart field 'file' is required")
    data = await upload.read()
    name = (upload.filename or "input.wav").lower()
    suffix = name[name.rfind(".") :] if "." in name else ".wav"
    result = await _run_chain(_registry(request), "asr", audio=data, suffix=suffix)
    return {"text": result["text"], "segments": result["segments"], "language": result["language"]}


@app.post("/v1/vision")
async def ask_vision(body: VisionRequest, request: Request) -> dict:
    if not body.image_base64:
        raise HTTPException(status_code=400, detail="image_base64 is required")
    image = base64.b64decode(body.image_base64)
    return await _run_chain(_registry(request), "vision", prompt=body.prompt, image=image)


@app.post("/v1/video")
async def create_video(body: VideoRequest, request: Request) -> dict:
    backend = _registry(request).pick("video")
    if backend is None:
        raise HTTPException(status_code=503, detail="no video backend available (set FORGE_WAN_COMMAND)")
    job = request.app.state.jobs.submit(backend.run(prompt=body.prompt))
    return {"job_id": job.id, "status": job.status}


@app.get("/v1/video/{job_id}")
async def video_status(job_id: str, request: Request) -> dict:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job")
    return {"job": job.as_dict()}


@app.get("/v1/search")
async def web_search(q: str, limit: int = 8, request: Request = None) -> dict:
    if request is None:
        raise HTTPException(status_code=400, detail="bad request context")
    return await _run_chain(_registry(request), "search", query=q, limit=limit)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "forge_core.main:app",
        host=config.host,
        port=config.port,
        log_level="info",
    )


if __name__ == "__main__":
    run()