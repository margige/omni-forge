"""Backend contract: one capability, one `run`."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Backend(ABC):
    name: str = "backend"
    capability: str = "generic"

    def available(self) -> bool:
        """Cheap, synchronous check that this backend can serve right now."""
        return True

    def describe(self) -> dict:
        return {"name": self.name, "capability": self.capability, "available": self.available()}

    @abstractmethod
    async def run(self, **kwargs) -> dict:
        raise NotImplementedError
