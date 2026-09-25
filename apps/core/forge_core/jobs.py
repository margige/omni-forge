"""In-memory async job registry for slow generations (video)."""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    status: str = "queued"  # queued | running | done | error
    result: dict | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    finished: float | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created": self.created,
            "finished": self.finished,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def submit(self, coro) -> Job:
        job = Job(id=secrets.token_hex(8))
        self._jobs[job.id] = job

        async def runner():
            job.status = "running"
            try:
                job.result = await coro
                job.status = "done"
            except Exception as exc:  # noqa: BLE001 - surfaced to the client
                job.status = "error"
                job.error = str(exc)
            finally:
                job.finished = time.time()

        task = asyncio.create_task(runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[dict]:
        return [j.as_dict() for j in self._jobs.values()]
