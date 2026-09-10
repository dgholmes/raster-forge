"""Job queue.

The database is the source of truth for job state; the queue only decides
*when* work runs. That separation is what makes "close the browser and come
back later" work by construction, and what lets the backend be swapped for
Redis/RQ later without touching the pipeline.

`ThreadJobQueue` is the default because Redis has no first-class Windows
build and this MVP has to run on the operator's machine today. It bounds
concurrency with a `ThreadPoolExecutor` sized by MAX_CONCURRENT_RASTER_JOBS,
and keeps a live `GdalRunner` per job so a cancel request can actually
terminate the subprocess rather than just setting a flag.
"""
from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Protocol

from .gdal_runner import GdalRunner

__all__ = ["JobQueue", "ThreadJobQueue", "JobHandle"]


class JobQueue(Protocol):
    def submit(self, job_id: str) -> None: ...
    def cancel(self, job_id: str) -> str: ...
    def active_count(self) -> int: ...
    def is_cancelled(self, job_id: str) -> bool: ...
    def register_runner(self, job_id: str, runner: GdalRunner) -> None: ...
    def shutdown(self, wait: bool = False) -> None: ...


class JobHandle:
    """Per-job control state shared between the API thread and the worker."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.cancel_event = threading.Event()
        self.runner: GdalRunner | None = None
        self.future: Future | None = None


class ThreadJobQueue:
    """In-process bounded worker pool.

    `runner_fn` takes a job id and does the work. It must open its own Flask
    app context: `current_app` is a thread-local proxy bound to the request
    thread, so reading it inside a pool worker raises
    "Working outside of application context".
    """

    def __init__(self, runner_fn: Callable[[str], None], max_workers: int = 2) -> None:
        self._runner_fn = runner_fn
        self._max_workers = max(1, int(max_workers))
        self._pool = ThreadPoolExecutor(
            max_workers=self._max_workers, thread_name_prefix="raster-worker"
        )
        self._handles: dict[str, JobHandle] = {}
        self._running: set[str] = set()
        self._lock = threading.Lock()

    # -- submission ------------------------------------------------------

    def submit(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._handles:
                return  # already queued or running
            handle = JobHandle(job_id)
            self._handles[job_id] = handle

        def work() -> None:
            with self._lock:
                self._running.add(job_id)
            try:
                self._runner_fn(job_id)
            finally:
                with self._lock:
                    self._running.discard(job_id)
                    self._handles.pop(job_id, None)

        handle.future = self._pool.submit(work)

    # -- cancellation ----------------------------------------------------

    def cancel(self, job_id: str) -> str:
        """Request cancellation, and say **who finalises the job row**.

        Returns:
          "dropped"   -- the work will never run; the caller must write the
                         terminal state itself.
          "signalled" -- a worker is running it and will write the terminal
                         state when it unwinds. The caller must NOT write it.
          "unknown"   -- not in this queue (e.g. orphaned by a restart); the
                         caller should finalise it.

        This distinction exists because deciding from the job's *database*
        status races: the route can read `queued` a moment before the worker
        commits `processing`, then write `cancelled` over a job that is in
        fact starting up — leaving the dataset stuck at `processing` with a
        `cancelled` job. The queue is the only thing that knows for certain
        whether the work began.
        """
        with self._lock:
            handle = self._handles.get(job_id)
        if handle is None:
            return "unknown"

        handle.cancel_event.set()

        # Not started yet: drop it before it ever runs.
        if handle.future is not None and handle.future.cancel():
            with self._lock:
                self._handles.pop(job_id, None)
            return "dropped"

        if handle.runner is not None:
            handle.runner.cancel()
        return "signalled"

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            handle = self._handles.get(job_id)
        return bool(handle and handle.cancel_event.is_set())

    def register_runner(self, job_id: str, runner: GdalRunner) -> None:
        """Publish the live runner so cancel() can reach the subprocess."""
        with self._lock:
            handle = self._handles.get(job_id)
        if handle is not None:
            handle.runner = runner
            # Cancelled while we were starting up.
            if handle.cancel_event.is_set():
                runner.cancel()

    # -- introspection ---------------------------------------------------

    def active_count(self) -> int:
        with self._lock:
            return len(self._running)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._handles) - len(self._running)

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def shutdown(self, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=not wait)
