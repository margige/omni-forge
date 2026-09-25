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


@pytest.mark.asyncio
async def test_pinned_provider_model_serves_only_that_upstream():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        calls.append(request.url.host)
        return httpx.Response(200, json=ok_body(model=_json.loads(request.content)["model"]))

    providers = [
        ProviderConfig(name="a", base_url="https://a.example/v1", priority=5, local=True),
        ProviderConfig(name="b", base_url="https://b.example/v1", priority=1, local=True),
    ]
    router, _ = make_router(handler, providers)
    data, provider = await router.complete({"model": "b/upstream-model", "messages": []})

    assert provider.name == "b"
    assert data["_forge"]["model"] == "upstream-model"
    assert calls == ["b.example"]  # 'a' was never tried: the pin decides, not priority


@pytest.mark.asyncio
async def test_pinned_provider_without_health_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok_body())

    providers = [
        ProviderConfig(name="healthy", base_url="https://h.example/v1", local=True, priority=1),
        ProviderConfig(name="down", base_url="https://d.example/v1", local=True, priority=99, rpd=1),
    ]
    router, _ = make_router(handler, providers)
    await router.complete({"model": "forge-chat", "messages": []})  # exhaust 'down'? no: 'healthy' wins

    # pin to 'down' after it is already cooling/rpd-exhausted
    router.ledger.record_success("down", 1)
    router.ledger.record_success("down", 1)
    with pytest.raises(NoProviderAvailable):
        await router.complete({"model": "down/whatever", "messages": []})


def test_models_catalog_lists_chain_plus_executable_entries():
    providers = [
        ProviderConfig(name="cloud", base_url="https://c.example/v1", api_key_env="MISSING_KEY", priority=1),
        ProviderConfig(name="local", base_url="https://l.example/v1", local=True, priority=90,
                       models=["qwen2.5:7b", "deepseek-r1:8b"]),
    ]
    router, _ = make_router(lambda r: httpx.Response(200, json=ok_body()), providers)

    catalog = router.models_catalog()
    assert catalog["model"] == "forge-chat"
    entries = {e["model"]: e for e in catalog["entries"]}
    assert entries["forge-chat"]["auto"] is True
    assert entries["local/qwen2.5:7b"]["provider"] == "local"
    assert entries["local/deepseek-r1:8b"]["label"] == "deepseek-r1:8b"
    assert not any(e["model"].startswith("cloud/") for e in catalog["entries"])


def test_resolve_requested():
    provider = ProviderConfig(name="up", base_url="https://u.example/v1", local=True, models=["m1", "m2"])
    other = ProviderConfig(name="other", base_url="https://o.example/v1", local=True, models=["m1"])
    router, _ = make_router(lambda r: httpx.Response(200, json=ok_body()), [provider, other])

    assert router.resolve_requested(None) is None
    assert router.resolve_requested("forge-chat") is None
    pinned = router.resolve_requested("up/m2")
    assert pinned == (router.providers[0], "m2")
    pinned = router.resolve_requested("other/m1")
    assert pinned == (router.providers[1], "m1")
    assert router.resolve_requested("up/anything-not-listed") == (router.providers[0], "anything-not-listed")
    assert router.resolve_requested("unknown/the-model") is None
    assert router.resolve_requested("m2") == (router.providers[0], "m2")
