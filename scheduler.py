"""
Async scheduler for timed announcements (timers, reminders, anything fire-later).

Items are pushed onto a min-heap by fire_at timestamp. A background task sleeps
until the next item is due and then forwards the announcement text to an
asyncio.Queue that the audio player drains.

Single-consumer by design: v1 plays announcements through the Anker S3 only.
local_input.py is expected to be the consumer.
"""
from __future__ import annotations

import asyncio
import heapq
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("jarvis.scheduler")


@dataclass(order=True)
class _Pending:
    fire_at: float
    text: str = field(compare=False)


class Scheduler:
    def __init__(self) -> None:
        self._heap: list[_Pending] = []
        # asyncio primitives created lazily so the module can be imported before
        # a running event loop exists.
        self._wake: Optional[asyncio.Event] = None
        self._queue: Optional[asyncio.Queue] = None
        self._task: Optional[asyncio.Task] = None

    def _ensure_loop_objects(self) -> None:
        if self._wake is None:
            self._wake = asyncio.Event()
        if self._queue is None:
            self._queue = asyncio.Queue()

    async def start(self) -> None:
        """Begin the background loop. Safe to call more than once."""
        self._ensure_loop_objects()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="scheduler")
            log.info("scheduler started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    # ---- Scheduling API ----

    def schedule_in(self, seconds: float, text: str) -> None:
        """Fire an announcement `seconds` from now."""
        self.schedule_at(time.time() + seconds, text)

    def schedule_at(self, timestamp: float, text: str) -> None:
        """Fire an announcement at a wall-clock time (UNIX seconds)."""
        heapq.heappush(self._heap, _Pending(timestamp, text))
        if self._wake is not None:
            self._wake.set()
        dt = timestamp - time.time()
        log.info(f"scheduled in {dt:.1f}s: {text!r}")

    # ---- Consumer API ----

    async def get_announcement(self) -> str:
        """Block until the next announcement fires, return its text."""
        self._ensure_loop_objects()
        assert self._queue is not None
        return await self._queue.get()

    def pending_count(self) -> int:
        """How many items are scheduled (not yet fired)."""
        return len(self._heap)

    def list_pending(self) -> list[tuple[float, str]]:
        """Return scheduled items as (fire_at_unix_seconds, text), soonest first."""
        return sorted((p.fire_at, p.text) for p in self._heap)

    def cancel_all(self) -> int:
        """Drop all pending items. Returns how many were removed."""
        n = len(self._heap)
        self._heap.clear()
        return n

    # ---- Internal ----

    async def _run(self) -> None:
        assert self._wake is not None and self._queue is not None
        try:
            while True:
                if not self._heap:
                    # Nothing scheduled — wait for someone to schedule something.
                    self._wake.clear()
                    await self._wake.wait()
                    continue

                top = self._heap[0]
                now = time.time()
                delay = top.fire_at - now

                if delay <= 0:
                    heapq.heappop(self._heap)
                    await self._queue.put(top.text)
                    log.info(f"fired: {top.text!r}")
                    continue

                # Sleep until either due-time or a new item lands.
                try:
                    self._wake.clear()
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            log.info("scheduler cancelled")
            raise


# ---- Module-level singleton ----

_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
