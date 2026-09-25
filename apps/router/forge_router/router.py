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

    def resolve_requested(self, requested: str | None) -> tuple[Provider, str] | None:
        """Map a client model name to an explicit upstream, or None for the chain.

        ``forge-chat`` / absent → None, meaning the normal failover chain.

        ``name/model``          → exactly that provider and that upstream model,
                                  even if the model is not in its configured list.

        Exact model name        → the single provider that lists it.

        Anything else           → None, so the request falls through to the chain
                                  (providers that know the name serve it).
        """
        if not requested or requested == "forge-chat":
            return None
        if "/" in requested:
            provider_name, _, model = requested.partition("/")
            for provider in self.providers:
                if provider.name == provider_name:
                    return provider, model
        for provider in self.providers:
            if requested in provider.cfg.models:
                return provider, requested
        return None

    async def _send(
        self, provider: Provider, payload: dict, model: str, *, stream: bool = False
    ) -> tuple[httpx.Response | None, str | None]:
        """One attempt at one provider. Returns (response, error).

        The response is only handed back once it is a 2xx; on any failure the
        ledger is updated and the error string is returned instead.
        """
        body = provider.build_payload(payload, model)
        if stream:
            body["stream"] = True
        request = self.client.build_request(
            "POST",
            provider.chat_url(),
            headers=provider.headers(),
            json=body,
            timeout=provider.cfg.timeout_s or self.config.timeout,
        )
        if not await provider.reserve():
            return None, f"{provider.name}: rpm limited"
        try:
            response = await self.client.send(request, stream=stream)
        except httpx.HTTPError as exc:
            self.ledger.record_error(provider.name)
            return None, f"{provider.name}: {exc}"
        if response.status_code >= 400:
            raw = await response.aread()
            await response.aclose()
            return None, self._handle_failure(
                provider, response.status_code, raw.decode("utf-8", "replace")
            )
        return response, None

    # ── non-streaming ────────────────────────────────────────────────────
    async def complete(self, payload: dict) -> tuple[dict, Provider]:
        requested = payload.get("model")
        pinned = self.resolve_requested(requested)
        if pinned is not None:
            target, upstream = pinned
            provider = next((p for p in self.candidates() if p.name == target.name), None)
            if provider is None:
                raise errors.NoProviderAvailable(
                    self.report(
                        f"{target.name}: pinned model unavailable (missing key, cooling or quota)"
                    )
                )
            response, err = await self._send(provider, payload, upstream)
            if err:
                raise errors.NoProviderAvailable(self.report(err))
            data = response.json()
            tokens = int(((data.get("usage") or {}).get("total_tokens")) or 0)
            self.ledger.record_success(provider.name, tokens)
            data["_forge"] = {"provider": provider.name, "model": upstream}
            return data, provider

        candidates = self.candidates()
        if not candidates:
            raise errors.NoProviderAvailable(self.report())

        last_error: str | None = None
        for provider in candidates:
            model = provider.default_model(requested)
            response, err = await self._send(provider, payload, model)
            if err:
                last_error = err
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
        pinned = self.resolve_requested(requested)
        if pinned is not None:
            target, upstream = pinned
            provider = next((p for p in self.candidates() if p.name == target.name), None)
            if provider is None:
                raise errors.NoProviderAvailable(
                    self.report(
                        f"{target.name}: pinned model unavailable (missing key, cooling or quota)"
                    )
                )
            response, err = await self._send(provider, payload, upstream, stream=True)
            if err:
                raise errors.NoProviderAvailable(self.report(err))
            self.ledger.record_success(provider.name, 0)
            return response, provider, upstream

        candidates = self.candidates()
        if not candidates:
            raise errors.NoProviderAvailable(self.report())

        last_error: str | None = None
        for provider in candidates:
            model = provider.default_model(requested)
            response, err = await self._send(provider, payload, model, stream=True)
            if err:
                last_error = err
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
                    "missing_key": provider.cfg.missing_key,
                    "model": provider.default_model(),
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
            "missing_keys": sorted(p["name"] for p in providers if p["missing_key"]),
            "providers": providers,
        }

    def models_catalog(self) -> dict:
        """Selectable models for the UI.

        ``forge-chat`` is the logical chain entry; every other entry is
        ``<provider>/<upstream-model>`` so the UI can pin a specific backend.
        """
        status = {p["name"]: p for p in self.status()}
        entries = [{
            "model": self.config.model,
            "provider": "*",
            "label": self.config.model,
            "local": False,
            "healthy": any(p["healthy"] for p in status.values()),
            "auto": True,
            "kind": "chat",
        }]
        for provider in self.providers:
            provider_status = status[provider.name]
            if not provider_status["resolved"]:
                continue
            for model in provider.cfg.models:
                entries.append(
                    {
                        "model": f"{provider.name}/{model}",
                        "provider": provider.name,
                        "label": model,
                        "local": provider.cfg.local,
                        "healthy": provider_status["healthy"],
                        "auto": False,
                        "kind": "chat",
                    }
                )
            for model in provider.cfg.image_models:
                entries.append(
                    {
                        "model": f"{provider.name}/{model}",
                        "provider": provider.name,
                        "label": model,
                        "local": provider.cfg.local,
                        "healthy": provider_status["healthy"],
                        "auto": False,
                        "kind": "image",
                    }
                )
        return {"model": self.config.model, "entries": entries, "providers": status}
