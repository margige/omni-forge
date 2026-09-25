"""Backend registry: ordered preference per capability."""

from __future__ import annotations

from .base import Backend


class Registry:
    def __init__(self) -> None:
        self._by_cap: dict[str, list[Backend]] = {}

    def register(self, backend: Backend) -> None:
        self._by_cap.setdefault(backend.capability, []).append(backend)

    def all(self, capability: str) -> list[Backend]:
        return list(self._by_cap.get(capability, []))

    def available(self, capability: str) -> list[Backend]:
        return [b for b in self.all(capability) if b.available()]

    def pick(self, capability: str, name: str | None = None) -> Backend | None:
        if name:
            for backend in self.all(capability):
                if backend.name == name:
                    return backend
            return None
        available = self.available(capability)
        return available[0] if available else None

    def describe(self) -> dict[str, list[dict]]:
        return {cap: [b.describe() for b in backends] for cap, backends in self._by_cap.items()}
