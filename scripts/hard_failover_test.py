"""
Hard E2E test: does omni-forge actually do what it promises?

Spin up stateful stub upstreams (each has a real budget that runs out),
a real router process with rpm gates + cooldowns + a sqlite ledger,
and drive it like a production client:

  T1  sequential exhaustion: alpha(3) bravo(3) charlie(0) delta(*)
      -> every request succeeds, providers visibly rotate down the chain;
         a flaky provider 500s, gets recorded, cooled down, and skipped
  T2  the REAL openai SDK against /v1/chat/completions (forge-chat),
      non-stream AND streaming, talking to the live router over TCP
  T3  concurrent load: 40 parallel requests, rpm gates never breached
  T5  persistence: restart the router process, the sqlite ledger survives
      byte-for-byte and long-lived cooldowns survive the restart

Run: .venv/scripts/python scripts/hard_failover_test.py
Exit non-zero on any failed assertion.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

ROOT = Path(__file__).resolve().parents[1]
ROUTER_PORT = 4010
STUB_BASE = 9100

CHECKS: list[str] = []
FAILED: list[str] = []
def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append(name)
    if not ok:
        FAILED.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

# --------------------------------------------------------------------------
# stateful stub upstreams
# --------------------------------------------------------------------------

class Stub:
    def __init__(self, name: str, port: int, budget: int, flaky_failures: int = 0):
        self.state = {
            "name": name, "remaining": budget, "counter": 0,
            "flaky_failures": int(flaky_failures), "failures_served": 0,
        }
        self.port = port
        app = FastAPI()

        @app.post("/v1/chat/completions")
        async def chat(body: dict):
            s = self.state
            cid = f"chatcmpl-{secrets.token_hex(8)}"
            model = body.get("model", "stub")
            if s["flaky_failures"] > 0 and s["failures_served"] < s["flaky_failures"]:
                s["failures_served"] += 1
                return JSONResponse(status_code=500, content={"error": {"message": "backend exploded"}})
            if s["remaining"] <= 0:
                return JSONResponse(status_code=429, content={"error": {"message": "quota exhausted"}})
            s["remaining"] -= 1
            s["counter"] += 1

            text = f"hello from {s['name']}#{s['counter']}"

            if body.get("stream"):
                async def gen():
                    def chunk(delta: dict, finish=None):
                        return ("data: " + json.dumps({
                            "id": cid, "object": "chat.completion.chunk",
                            "created": int(time.time()), "model": model,
                            "choices": [{"index": 0, "delta": delta, "finish_reason": finish, "logprobs": None}],
                        }) + "\n\n").encode()
                    yield chunk({"role": "assistant", "content": ""})
                    yield chunk({"content": text})
                    yield chunk({}, "stop")
                    yield b"data: [DONE]\n\n"
                return StreamingResponse(gen(), media_type="text/event-stream",
                                         headers={"cache-control": "no-cache"})

            return {
                "id": cid, "object": "chat.completion", "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                             "finish_reason": "stop", "logprobs": None}],
                "usage": {"prompt_tokens": 1, "completion_tokens": len(text),
                          "total_tokens": 1 + len(text)},
            }

        self._app = app
        self._server = None

    def start(self):
        import uvicorn
        self._server = uvicorn.Server(uvicorn.Config(self._app, host="127.0.0.1",
                                                     port=self.port, log_level="error"))
        threading.Thread(target=self._server.run, daemon=True).start()
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{self.port}/openapi.json", timeout=1)
                break
            except Exception:  # noqa: BLE001  retry loop: service still starting
                time.sleep(0.05)

    def stop(self):
        if self._server:
            self._server.should_exit = True

    def top_up(self, budget: int):
        self.state["remaining"] += budget

# --------------------------------------------------------------------------
# real router process
# --------------------------------------------------------------------------

def write_providers(workdir: Path, stub_ports: dict[str, int]) -> Path:
    p = workdir / "providers.yaml"
    spec = {
        "router": {"model": "forge-chat", "timeout": 30},
        "providers": [
            {"name": "flaky",  "base_url": f"http://127.0.0.1:{stub_ports['flaky']}/v1",
             "priority": 1, "local": False, "api_key_env": "FORGE_TEST_KEY",
             "cooldown_seconds": 300},
            {"name": "alpha",  "base_url": f"http://127.0.0.1:{stub_ports['alpha']}/v1",
             "priority": 2, "rpm": 10, "local": False, "api_key_env": "FORGE_TEST_KEY",
             "cooldown_seconds": 1},
            {"name": "bravo",  "base_url": f"http://127.0.0.1:{stub_ports['bravo']}/v1",
             "priority": 3, "rpm": 5, "local": False, "api_key_env": "FORGE_TEST_KEY",
             "cooldown_seconds": 1},
            {"name": "charlie", "base_url": f"http://127.0.0.1:{stub_ports['charlie']}/v1",
             "priority": 4, "local": False, "api_key_env": "FORGE_TEST_KEY",
             "cooldown_seconds": 1},
            {"name": "local-delta", "base_url": f"http://127.0.0.1:{stub_ports['delta']}/v1",
             "priority": 1000, "local": True},
        ],
    }
    p.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return p

def start_router(workdir: Path, env: dict) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "forge_router.main:app",
         "--host", "127.0.0.1", "--port", str(ROUTER_PORT)],
        cwd=workdir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            httpx.get(f"http://127.0.0.1:{ROUTER_PORT}/healthz", timeout=1).raise_for_status()
            return proc
        except Exception:  # noqa: BLE001  retry loop: router still booting
            if proc.poll() is not None:
                raise RuntimeError(f"router died: rc={proc.returncode}")
            time.sleep(0.25)
    raise RuntimeError("router did not become healthy")

def stop(proc: subprocess.Popen | None):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

def quota() -> dict:
    r = httpx.get(f"http://127.0.0.1:{ROUTER_PORT}/forge/quota", timeout=5)
    r.raise_for_status()
    return r.json()

async def chat_raw(prompt: str, timeout: float = 30):
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{ROUTER_PORT}",
                                 timeout=timeout) as c:
        r = await c.post("/v1/chat/completions", json={
            "model": "forge-chat",
            "messages": [{"role": "user", "content": prompt}],
        })
        return r

# --------------------------------------------------------------------------
def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="forge-hard-"))
    env = os.environ.copy()
    env["FORGE_ROUTER_PORT"] = str(ROUTER_PORT)
    env["FORGE_ROUTER_DB"] = str(workdir / "router.db")
    env["FORGE_TEST_KEY"] = "dummy-key-for-stub-providers"
    port = {"flaky": STUB_BASE + 1, "alpha": STUB_BASE + 2, "bravo": STUB_BASE + 3,
            "charlie": STUB_BASE + 4, "delta": STUB_BASE + 5}
    write_providers(workdir, port)

    stubs = {
        "flaky":  Stub("flaky",  port["flaky"],  budget=999, flaky_failures=2),
        "alpha":  Stub("alpha",  port["alpha"],  budget=3),
        "bravo":  Stub("bravo",  port["bravo"],  budget=3),
        "charlie": Stub("charlie", port["charlie"], budget=0),
        "delta":  Stub("local-delta", port["delta"], budget=99999),
    }
    for s in stubs.values():
        s.start()
    router = start_router(workdir, env)

    try:
        # ---------------- T1: sequential quota exhaustion ----------------
        print("\nT1  sequential exhaustion (alpha=3, bravo=3, charlie=0, local=*)")
        leads: list[str] = []
        for n in range(12):
            r = httpx.post(f"http://127.0.0.1:{ROUTER_PORT}/v1/chat/completions",
                           json={"model": "forge-chat", "messages": [{"role": "user", "content": f"q{n}"}]},
                           timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"T1 request {n} failed: {r.status_code} {r.text}")
            leads.append(r.json()["_forge"]["provider"])
        check("alpha, bravo and local-delta each served their own slice",
              leads[:3] == ["alpha"] * 3 and leads[3:6] == ["bravo"] * 3
              and leads[6:] == ["local-delta"] * 6,
              " -> ".join(leads))
        q = quota()
        by = {p["name"]: p for p in q["providers"]}
        check("flaky failed once, then cooled down & skipped",
              by["flaky"]["errors_today"] == 1 and by["flaky"]["cooling_remaining"] > 0)
        check("alpha served exactly its 3 then went dry",
              by["alpha"]["requests_today"] == 3)
        check("bravo served exactly its 3 then went dry",
              by["bravo"]["requests_today"] == 3)
        check("charlie (0 budget) never served a single request",
              by["charlie"]["requests_today"] == 0 and by["charlie"]["errors_today"] == 0)
        check("local-delta caught everything after the cloud pool dried",
              by["local-delta"]["requests_today"] == 6)
        print(f"      lead order: {' -> '.join(leads)}")

        # ---------------- T2: the real openai SDK ------------------------
        print("\nT2  real openai SDK vs /v1  (model=forge-chat)")
        from openai import OpenAI
        c = OpenAI(base_url=f"http://127.0.0.1:{ROUTER_PORT}/v1", api_key="forge-local")

        resp = c.chat.completions.create(
            model="forge-chat",
            messages=[{"role": "user", "content": "who are you?"}])
        txt = resp.choices[0].message.content or ""
        check("SDK non-streaming completion", bool(txt) and txt.startswith("hello"),
              txt[:50])

        raw = c.chat.completions.with_raw_response.create(
            model="forge-chat",
            messages=[{"role": "user", "content": "stream this"}],
            stream=True)
        streamed = raw.parsed if hasattr(raw, "parsed") else raw.parse()
        parts = [ch.choices[0].delta.content or "" for ch in streamed if ch.choices]
        sjoin = "".join(parts)
        check("SDK streaming completion (SSE through the relay)",
              sjoin.startswith("hello"), sjoin[:50])
        check("stream relay reports serving provider",
              raw.headers.get("x-forge-provider") == "local-delta",
              str(raw.headers.get("x-forge-provider")))

        # ---------------- T3: concurrent load + rpm gates -----------------
        print("\nT3  40 concurrent requests, rpm gates must hold")
        stubs["alpha"].top_up(999)
        stubs["bravo"].top_up(999)
        async def load():
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{ROUTER_PORT}",
                                         timeout=60) as ac:
                return await asyncio.gather(*[
                    ac.post("/v1/chat/completions",
                            json={"model": "forge-chat",
                                  "messages": [{"role": "user", "content": f"load {i}"}]})
                    for i in range(40)])
        results = asyncio.run(load())
        ok = [r for r in results if r.status_code == 200]
        check("all 40 concurrent requests succeeded", len(ok) == 40, f"{len(results)-40} failed")
        q = quota()
        by = {p["name"]: p for p in q["providers"]}
        check("alpha rpm(10) never breached", by["alpha"]["requests_last_minute"] <= 10,
              f"{by['alpha']['requests_last_minute']}/min")
        check("bravo rpm(5) never breached", by["bravo"]["requests_last_minute"] <= 5,
              f"{by['bravo']['requests_last_minute']}/min")
        check("ledger still consistent, charlie untouched", by["charlie"]["requests_today"] == 0)

        # ---------------- T5: persistence across restart ------------------
        print("\nT5  router restart, ledger must survive")
        def ledger(q: dict) -> dict:
            return {p["name"]: tuple(p[k] for k in ("requests_today", "errors_today", "tokens_today"))
                    for p in q["providers"]}
        before = ledger(quota())
        cooling_before = {p["name"] for p in quota()["providers"] if p["cooling_remaining"] > 0}
        stop(router)
        router = start_router(workdir, env)
        after = ledger(quota())
        cooling_after = {p["name"] for p in quota()["providers"] if p["cooling_remaining"] > 0}
        check("usage + error + token ledger identical after a hard restart",
              before == after, "OK" if before == after else json.dumps({"before": before, "after": after}))
        check("long-lived cooldowns survive the restart (flaky 300s down)",
              "flaky" in cooling_before and "flaky" in cooling_after,
              f"before={sorted(cooling_before)} after={sorted(cooling_after)}")
        r = httpx.get(f"http://127.0.0.1:{ROUTER_PORT}/v1/models", timeout=5).json()
        check("router fully operational post-restart", "forge-chat" in
              {m["id"] for m in r["data"]})

    finally:
        stop(router)
        for s in stubs.values():
            s.stop()

    print(f"\n{len(CHECKS)} checks, {len(FAILED)} failed, "
          f"{len(CHECKS) - len(FAILED)} passed" + (" (ALL PASS)" if not FAILED else ""))
    return 1 if FAILED else 0

if __name__ == "__main__":
    sys.exit(main())