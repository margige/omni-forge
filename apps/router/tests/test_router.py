"""Failover is the whole product. Prove it."""

from __future__ import annotations

import httpx
import pytest

from forge_router.config import ProviderConfig, RouterConfig
from forge_router.errors import NoProviderAvailable
from forge_router.router import ForgeRouter
from forge_router.store import UsageLedger


def make_router(handler, providers):
    config = RouterConfig(model="forge-chat", providers=providers)
    ledger = UsageLedger(":memory:")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ForgeRouter(config, ledger, client), ledger


def ok_body(model="upstream-model"):
    return {"id": "x", "model": model, "choices": [], "usage": {"total_tokens": 7}}


@pytest.mark.asyncio
async def test_failover_on_quota_exhaustion():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        calls.append(host)
        if host == "quota.example":
            return httpx.Response(429, json={"error": {"message": "rate limit exceeded"}})
        return httpx.Response(200, json=ok_body())

    providers = [
        ProviderConfig(name="quota", base_url="https://quota.example/v1", api_key_env=None, priority=1),
        ProviderConfig(name="good", base_url="https://good.example/v1", api_key_env=None, priority=2),
    ]
    providers[0].api_key_env = "X"  # requires a key, but is_resolved checks local/key
    # make both resolved without touching the environment
    for p in providers:
        p.local = True

    router, ledger = make_router(handler, providers)
    data, provider = await router.complete({"model": "forge-chat", "messages": []})

    assert provider.name == "good"
    assert data["_forge"]["provider"] == "good"
    assert calls == ["quota.example", "good.example"]
    assert ledger.is_cooling("quota")
    assert ledger.cooldown_reason("quota") == "quota"


@pytest.mark.asyncio
async def test_all_providers_exhausted_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    providers = [
        ProviderConfig(name="a", base_url="https://a.example/v1", priority=1, local=True),
        ProviderConfig(name="b", base_url="https://b.example/v1", priority=2, local=True),
    ]
    router, _ = make_router(handler, providers)

    with pytest.raises(NoProviderAvailable) as exc:
        await router.complete({"model": "forge-chat", "messages": []})

    assert exc.value.detail["error"] == "no provider available"
    assert len(exc.value.detail["providers"]) == 2


@pytest.mark.asyncio
async def test_unresolved_provider_is_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok_body())

    providers = [
        ProviderConfig(name="needs-key", base_url="https://x.example/v1", api_key_env="ABSENT_KEY", priority=1),
        ProviderConfig(name="local", base_url="https://local.example/v1", priority=2, local=True),
    ]
    router, _ = make_router(handler, providers)
    _, provider = await router.complete({"model": "forge-chat", "messages": []})
    assert provider.name == "local"


@pytest.mark.asyncio
async def test_rpd_quota_gate_skips_provider():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok_body())

    providers = [
        ProviderConfig(name="tiny", base_url="https://tiny.example/v1", priority=1, local=True, rpd=1),
        ProviderConfig(name="big", base_url="https://big.example/v1", priority=2, local=True),
    ]
    router, ledger = make_router(handler, providers)
    await router.complete({"model": "forge-chat", "messages": []})
    _, provider = await router.complete({"model": "forge-chat", "messages": []})
    assert provider.name == "big"  # tiny hit its daily cap
    assert ledger.requests_today("tiny") == 1
