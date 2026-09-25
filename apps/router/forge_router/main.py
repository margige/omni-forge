"""Forge Router HTTP surface: OpenAI-compatible chat + a small admin API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import Body, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, errors
from .config import load_config
from .router import ForgeRouter
from .store import UsageLedger

UI_DIR = Path(
    os.environ.get("FORGE_UI_DIR", Path(__file__).resolve().parents[3] / "apps" / "ui" / "dashboard")
)
DB_PATH = os.environ.get("FORGE_ROUTER_DB", "data/router.db")


def _ledger_path() -> str:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    ledger = UsageLedger(_ledger_path())
    client = httpx.AsyncClient(follow_redirects=True)
    app.state.config = config
    app.state.ledger = ledger
    app.state.router = ForgeRouter(config, ledger, client)
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(title="omni-forge router", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _router(request: Request) -> ForgeRouter:
    return request.app.state.router


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "service": "forge-router", "version": __version__}


@app.get("/v1/models")
async def models(request: Request) -> dict:
    config = request.app.state.config
    return {
        "object": "list",
        "data": [
            {
                "id": config.model,
                "object": "model",
                "owned_by": "omni-forge",
                "description": "logical model with automatic free-tier failover",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, body: dict = Body(...)):
    router = _router(request)
    wants_stream = bool(body.get("stream"))
    try:
        if wants_stream:
            upstream, provider, model = await router.open_stream(body)
        else:
            data, provider = await router.complete(body)
            return JSONResponse(data)
    except errors.NoProviderAvailable as exc:
        return JSONResponse(status_code=503, content={"error": exc.detail})

    async def relay():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    headers = {
        "x-forge-provider": provider.name,
        "x-forge-model": model,
        "cache-control": "no-cache",
    }
    return StreamingResponse(relay(), media_type="text/event-stream", headers=headers)


# ── admin / dashboard ────────────────────────────────────────────────────────
@app.get("/forge/health")
async def forge_health(request: Request) -> dict:
    router = _router(request)
    providers = router.status()
    return {
        "ok": any(p["healthy"] for p in providers),
        "healthy": [p["name"] for p in providers if p["healthy"]],
        "cooling": [p["name"] for p in providers if p["cooling_remaining"] > 0],
        "local_available": any(p["local"] and p["resolved"] for p in providers),
    }


@app.get("/forge/quota")
async def forge_quota(request: Request) -> dict:
    return {"providers": _router(request).status(), "model": request.app.state.config.model}


@app.get("/forge/providers")
async def forge_providers(request: Request) -> dict:
    return {"providers": _router(request).status()}


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/forge/")


if UI_DIR.is_dir():
    app.mount("/forge", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


def run() -> None:
    config = load_config()
    uvicorn.run(
        "forge_router.main:app",
        host=config.host,
        port=config.port,
        log_level=os.environ.get("FORGE_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    run()
