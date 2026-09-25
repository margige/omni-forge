"""Selection and transport: pick the first healthy provider, fail over cleanly.

The caller only ever names one logical model (`forge-chat`). Everything about
*which* upstream serves it — priority, quota, cooldown, locality — is decided
here, request by request.
"""

from __future__ import annotations

import time

import httpx

from . import errors
from .config import RouterConfig
from .providers import Provider
from .store import UsageLedger


class ForgeRouter:
    def __init__(self, config: RouterConfig, ledger: UsageLedger, client: httpx.AsyncClient):
        self.config = config
        self.ledger = ledger
        self.client = client
        self.providers: list[Provider] = [Provider(c) for c in config.ordered()]

    # ── candidate selection ──────────────────────────────────────────────
    def _quota_ok(self, provider: Provider) -> bool:
        rpd = provider.cfg.rpd
        if rpd is None:
            return True
        return self.ledger.requests_today(provider.name) < rpd

    def candidates(self) -> list[Provider]:
        now = time.time()
        out: list[Provider] = []
        for provider in self.providers:
            if not provider.cfg.is_resolved():
                continue
            if self.ledger.is_cooling(provider.name, now):
                continue
            if not provider.rpm_ok(now):
                continue
            if not self._quota_ok(provider):
                continue
            out.append(provider)
        return out

    # ── non-streaming ────────────────────────────────────────────────────
    async def complete(self, payload: dict) -> tuple[dict, Provider]:
        requested = payload.get("model")
        candidates = self.candidates()
        if not candidates:
            raise errors.NoProviderAvailable(self.report())

        last_error: str | None = None
        for provider in candidates:
            model = provider.default_model(requested)
            body = provider.build_payload(payload, model)
            if not await provider.reserve():
                last_error = f"{provider.name}: rpm limited"
                continue
            try:
                response = await self.client.post(
                    provider.chat_url(),
                    headers=provider.headers(),
                    json=body,
                    timeout=provider.cfg.timeout or self.config.timeout,
                )
            except httpx.HTTPError as exc:
                self.ledger.record_error(provider.name)
                last_error = f"{provider.name}: {exc}"
                continue

            if response.status_code >= 400:
                last_error = self._handle_failure(provider, response.status_code, response.text)
                continue

            data = response.json()
            tokens = int(((data.get("usage") or {}).get("total_tokens")) or 0)
            self.ledger.record_success(provider.name, tokens)
            data["_forge"] = {"provider": provider.name, "model": model}
            return data, provider

        raise errors.NoProviderAvailable(self.report(last_error))

    # ── streaming ────────────────────────────────────────────────────────
    async def open_stream(self, payload: dict) -> tuple[httpx.Response, Provider, str]:
        """Send a streaming request and return the live response once it is 200.

        Failover happens *before* any bytes reach the client, so a dead provider
        never corrupts an in-flight stream.
        """
        requested = payload.get("model")
        candidates = self.candidates()
        if not candidates:
            raise errors.NoProviderAvailable(self.report())

        last_error: str | None = None
        for provider in candidates:
            model = provider.default_model(requested)
            body = provider.build_payload(payload, model)
            body["stream"] = True
            request = self.client.build_request(
                "POST",
                provider.chat_url(),
                headers=provider.headers(),
                json=body,
                timeout=provider.cfg.timeout or self.config.timeout,
            )
            if not await provider.reserve():
                last_error = f"{provider.name}: rpm limited"
                continue
            try:
                response = await self.client.send(request, stream=True)
            except httpx.HTTPError as exc:
                self.ledger.record_error(provider.name)
                last_error = f"{provider.name}: {exc}"
                continue

            if response.status_code >= 400:
                raw = await response.aread()
                await response.aclose()
                last_error = self._handle_failure(
                    provider, response.status_code, raw.decode("utf-8", "replace")
                )
                continue

            self.ledger.record_success(provider.name, 0)
            return response, provider, model

        raise errors.NoProviderAvailable(self.report(last_error))

    # ── failure handling ─────────────────────────────────────────────────
    def _handle_failure(self, provider: Provider, status: int, body: str) -> str:
        if errors.is_quota_error(status, body):
            self.ledger.set_cooldown(provider.name, provider.cfg.cooldown_seconds, "quota")
        else:
            self.ledger.record_error(provider.name)
            if errors.is_retryable(status):
                self.ledger.set_cooldown(provider.name, 30, f"http {status}")
        return f"{provider.name}: {status}"

    # ── introspection ────────────────────────────────────────────────────
    def status(self) -> list[dict]:
        now = time.time()
        rows = {r["provider"]: r for r in self.ledger.snapshot()}
        out = []
        for provider in self.providers:
            row = rows.get(provider.name, {})
            out.append(
                {
                    "name": provider.name,
                    "local": provider.cfg.local,
                    "resolved": provider.cfg.is_resolved(),
                    "priority": provider.cfg.priority,
                    "models": provider.cfg.models,
                    "requests_today": row.get("requests", 0),
                    "tokens_today": row.get("tokens", 0),
                    "errors_today": row.get("errors", 0),
                    "rpd": provider.cfg.rpd,
                    "rpm": provider.cfg.rpm,
                    "requests_last_minute": provider.requests_last_minute(),
                    "cooling_remaining": round(self.ledger.cooldown_remaining(provider.name, now), 1),
                    "cooling_reason": self.ledger.cooldown_reason(provider.name),
                    "healthy": (
                        provider.cfg.is_resolved()
                        and not self.ledger.is_cooling(provider.name, now)
                        and provider.rpm_ok(now)
                        and self._quota_ok(provider)
                    ),
                }
            )
        return out

    def report(self, last_error: str | None = None) -> dict:
        providers = self.status()
        return {
            "error": "no provider available",
            "last_error": last_error,
            "local_available": any(p["local"] and p["resolved"] for p in providers),
            "providers": providers,
        }
