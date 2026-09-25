"""Router configuration: provider pool, ordering, and env/key resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_PATHS = (
    Path("providers.yaml"),
    Path("apps/router/providers.yaml"),
    Path.home() / ".config" / "omni-forge" / "providers.yaml",
    Path(__file__).resolve().parents[1] / "providers.example.yaml",
)


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    priority: int = 100
    api_key_env: str | None = None
    models: list[str] = field(default_factory=list)
    local: bool = False
    rpd: int | None = None
    rpm: int | None = None
    timeout: int | None = None
    cooldown_seconds: int = 300

    @property
    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env) or None

    @property
    def resolved(self) -> bool:
        return self.local or bool(self.api_key)

    def is_resolved(self) -> bool:
        return self.resolved

    @property
    def default_model(self) -> str | None:
        return self.models[0] if self.models else None


@dataclass
class RouterConfig:
    providers: list[ProviderConfig]
    model: str = "forge-chat"
    timeout: int = 120
    host: str = "127.0.0.1"
    port: int = 4010

    def ordered(self) -> list[ProviderConfig]:
        """Local providers always sort last; cloud tiers sort by priority."""
        return sorted(self.providers, key=lambda p: (p.local, p.priority))


def load_config(path: str | Path | None = None) -> RouterConfig:
    candidate = Path(path) if path else next((p for p in DEFAULT_PATHS if p.is_file()), None)
    if candidate is None or not candidate.is_file():
        raise FileNotFoundError("no provider config found; copy providers.example.yaml to providers.yaml")
    raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    router = raw.get("router", {})
    providers = [
        ProviderConfig(
            name=p["name"],
            base_url=p["base_url"].rstrip("/"),
            priority=int(p.get("priority", 100)),
            api_key_env=p.get("api_key_env"),
            models=list(p.get("models", [])),
            local=bool(p.get("local", False)),
            rpd=p.get("rpd"),
            rpm=p.get("rpm"),
            timeout=p.get("timeout"),
            cooldown_seconds=int(p.get("cooldown_seconds", 300)),
        )
        for p in raw.get("providers", [])
    ]
    if not providers:
        raise ValueError("provider config contains no providers")
    return RouterConfig(
        providers=providers,
        model=router.get("model", "forge-chat"),
        timeout=int(router.get("timeout", 120)),
        host=os.environ.get("FORGE_ROUTER_HOST", "127.0.0.1"),
        port=int(os.environ.get("FORGE_ROUTER_PORT", "4010")),
    )