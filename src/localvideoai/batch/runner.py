"""Queue controller: start / pause / resume / cancel / retry / delete, with real ETA."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from localvideoai.batch.pipeline import BatchPipeline
from localvideoai.batch.resources import ResourceSnapshot, can_start_another, snapshot
from localvideoai.batch.types import (
    ACTIVE_STATUSES,
    RUNNABLE_STATUSES,
    STAGES,
    STATUS_DONE,
    STATUS_FAIL,
    STATUS_PAUSE,
    STATUS_WAIT,
)
from localvideoai.core.exceptions import TaskError
from localvideoai.core.types import TaskSpec
from localvideoai.managers.task_manager import TaskManager

ChangeFn = Callable[[], None]


class BatchRunner:
    def __init__(
        self,
        tasks: TaskManager,
        *,
        analyzer,
        speech_engine,
        ocr_engine,
        translation_engine,
        quality_engine,
        device: str = "auto",
        prefer_gpu: bool = True,
        max_concurrent: int = 1,
        ram_limit_gb: float = 0.0,
        min_free_ram_gb: float = 1.5,
        cpu_threads: int = 0,
        source_lang: str = "auto",
        target_lang: str = "zh-CN",
        on_change: ChangeFn | None = None,
    ) -> None:
        self.tasks = tasks
        self._paused = False
        self._stop_all = False
        self._cancelled: set[str] = set()
        self._running_ids: set[str] = set()
        self._lock = threading.RLock()
        self._stage_locks = {name: threading.Lock() for name in STAGES}
        self._on_change = on_change
        self._session_done = 0
        self._work_started: float | None = None
        self._paused_started: float | None = None
        self._paused_seconds = 0.0
        self.set_limits(
            device=device,
            prefer_gpu=prefer_gpu,
            max_concurrent=max_concurrent,
            ram_limit_gb=ram_limit_gb,
            min_free_ram_gb=min_free_ram_gb,
            cpu_threads=cpu_threads,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        self._pipeline = BatchPipeline(
            analyzer=analyzer,
            speech_engine=speech_engine,
            ocr_engine=ocr_engine,
            translation_engine=translation_engine,
            quality_engine=quality_engine,
            device=self.device,
            prefer_gpu=self.prefer_gpu,
            source_lang=self.source_lang,
            target_lang=self.target_lang,
            locks=self._stage_locks,
        )

    def set_limits(
        self,
        *,
        device: str | None = None,
        prefer_gpu: bool | None = None,
        max_concurrent: int | None = None,
        ram_limit_gb: float | None = None,
        min_free_ram_gb: float | None = None,
        cpu_threads: int | None = None,
        source_lang: str | None = None,
        target_lang: str | None = None,
    ) -> ResourceSnapshot:
        if device is not None:
            self.device = (device or "auto").strip().lower()
        if prefer_gpu is not None:
            self.prefer_gpu = bool(prefer_gpu)
        if max_concurrent is not None:
            self.max_concurrent = max(1, int(max_concurrent))
        if ram_limit_gb is not None:
            self.ram_limit_gb = max(0.0, float(ram_limit_gb))
        if min_free_ram_gb is not None:
            self.min_free_ram_gb = max(0.0, float(min_free_ram_gb))
        if cpu_threads is not None:
            self.cpu_threads = max(0, int(cpu_threads))
        if source_lang is not None:
            self.source_lang = source_lang
        if target_lang is not None:
            self.target_lang = target_lang
        if hasattr(self, "_pipeline"):
            self._pipeline.device = self.device
            self._pipeline.prefer_gpu = self.prefer_gpu
            self._pipeline.source_lang = self.source_lang
            self._pipeline.target_lang = self.target_lang
        return self.resources()

    def resources(self) -> ResourceSnapshot:
        return snapshot(
            device=self.device,
            prefer_gpu=self.prefer_gpu,
            max_concurrent=self.max_concurrent,
            ram_limit_gb=self.ram_limit_gb,
            min_free_ram_gb=self.min_free_ram_gb,
            cpu_threads=self.cpu_threads,
        )

    def add_video(self, path: Path, task_id: str = "") -> str:
        source = path.expanduser().resolve()
        for task in self.tasks.list_tasks():
            existing = Path(str((task.get("payload") or {}).get("path") or ""))
            try:
                if existing.expanduser().resolve() == source:
                    return str(task["id"])
            except OSError:
                if str(existing) == str(source):
                    return str(task["id"])
        spec = TaskSpec(
            task_id=task_id,
            task_type="batch_video",
            payload={"path": str(source), "name": source.name, "done_stages": []},
        )
        return self.tasks.enqueue(spec)

    def start(self) -> None:
        with self._lock:
            self._paused = False
            self._stop_all = False
            if self._paused_started is not None:
                self._paused_seconds += time.monotonic() - self._paused_started
                self._paused_started = None
            if self._work_started is None:
                self._work_started = time.monotonic()

    def pause(self) -> None:
        with self._lock:
            already = self._paused
            self._paused = True
            if self._paused_started is None:
                self._paused_started = time.monotonic()
        if already:
            return
        for task in self.tasks.list_tasks():
            if task.get("status") in ACTIVE_STATUSES and task["id"] not in self._running_ids:
                self.tasks.update(str(task["id"]), status=STATUS_PAUSE)
        self._notify()

    def resume(self) -> None:
        self.start()

    def cancel(self, task_id: str | None = None) -> None:
        if task_id:
            with self._lock:
                self._cancelled.add(task_id)
            current = self.tasks.get(task_id)
            if current and current.get("status") != STATUS_DONE and task_id not in self._running_ids:
                self.tasks.update(task_id, status=STATUS_FAIL, error="已取消")
        else:
            with self._lock:
                self._stop_all = True
            for task in self.tasks.list_tasks():
                if task.get("status") == STATUS_DONE:
                    continue
                if task["id"] in self._running_ids:
                    with self._lock:
                        self._cancelled.add(str(task["id"]))
                    continue
                self.tasks.update(str(task["id"]), status=STATUS_FAIL, error="已取消")
        self._notify()

    def retry(self, task_id: str) -> dict[str, Any]:
        current = self.tasks.get(task_id)
        if current is None:
            raise TaskError(f"任务不存在：{task_id}")
        with self._lock:
            self._cancelled.discard(task_id)
        updated = self.tasks.update(task_id, status=STATUS_WAIT, error="")
        self._notify()
        return updated

    def delete(self, task_id: str) -> None:
        with self._lock:
            self._cancelled.add(task_id)
        self.tasks.delete(task_id)
        self._notify()

    def is_paused(self) -> bool:
        return self._paused

    def is_busy(self) -> bool:
        with self._lock:
            return bool(self._running_ids)

    def run_until_idle(self) -> None:
        self.start()
        self._apply_cpu_threads()
        workers = max(1, self.max_concurrent)
        if workers == 1:
            while True:
                if self._paused or self._stop_all:
                    self._mark_active_paused()
                    return
                task = self._next_runnable()
                if task is None:
                    return
                allowed, _reason = can_start_another(len(self._running_ids), self.resources())
                if not allowed:
                    return
                self._run_one(task)
            return
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures: dict[Any, str] = {}
            while True:
                if self._paused or self._stop_all:
                    if futures:
                        wait(futures)
                    self._mark_active_paused()
                    return
                while len(futures) < workers:
                    allowed, _reason = can_start_another(len(self._running_ids), self.resources())
                    if not allowed:
                        break
                    task = self._next_runnable()
                    if task is None:
                        break
                    futures[pool.submit(self._run_one, task)] = str(task["id"])
                if not futures:
                    return
                done, _pending = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    future.result()
                    futures.pop(future, None)

    def stats(self) -> dict[str, Any]:
        tasks = self.tasks.list_tasks()
        remaining = [
            item
            for item in tasks
            if item.get("status") not in {STATUS_DONE, STATUS_FAIL}
        ]
        elapsed = self._work_elapsed()
        speed = (self._session_done / (elapsed / 60.0)) if elapsed > 0 and self._session_done else 0.0
        eta = None
        if speed > 0:
            eta = remaining and (len(remaining) / speed) * 60.0 or 0.0
        limits = self.resources()
        return {
            "total": len(tasks),
            "done": sum(1 for item in tasks if item.get("status") == STATUS_DONE),
            "failed": sum(1 for item in tasks if item.get("status") == STATUS_FAIL),
            "running": len(self._running_ids),
            "remaining": len(remaining),
            "paused": self._paused,
            "speed_per_min": round(speed, 2),
            "eta_seconds": None if eta is None else max(0, int(round(eta))),
            "elapsed_seconds": int(elapsed),
            "cpu_count": limits.cpu_count,
            "cpu_threads": limits.cpu_threads,
            "device": limits.device,
            "prefer_gpu": limits.prefer_gpu,
            "total_ram_gb": round(limits.total_ram_gb, 1),
            "available_ram_gb": round(limits.available_ram_gb, 1),
            "max_concurrent": limits.max_concurrent,
            "ram_limit_gb": limits.ram_limit_gb,
        }

    def _next_runnable(self) -> dict[str, Any] | None:
        with self._lock:
            running = set(self._running_ids)
            cancelled = set(self._cancelled)
        for task in self.tasks.list_tasks():
            task_id = str(task.get("id") or "")
            status = str(task.get("status") or "")
            if task_id in running or task_id in cancelled:
                continue
            if status == STATUS_DONE:
                continue
            if status == STATUS_FAIL:
                continue
            if status in RUNNABLE_STATUSES or status == STATUS_PAUSE:
                return task
        return None

    def _run_one(self, task: dict[str, Any]) -> None:
        task_id = str(task["id"])
        with self._lock:
            self._running_ids.add(task_id)
        try:
            result = self._pipeline.process(
                task,
                persist=lambda **fields: self._persist(task_id, **fields),
                should_stop=lambda: self._should_stop(task_id),
                is_paused=lambda: self._paused,
            )
            if result.get("status") == STATUS_DONE:
                with self._lock:
                    self._session_done += 1
        finally:
            with self._lock:
                self._running_ids.discard(task_id)
            self._notify()

    def _persist(self, task_id: str, **fields: Any) -> dict[str, Any]:
        updated = self.tasks.update(task_id, **fields)
        self._notify()
        return updated

    def _should_stop(self, task_id: str) -> bool:
        with self._lock:
            return self._stop_all or task_id in self._cancelled

    def _mark_active_paused(self) -> None:
        for task in self.tasks.list_tasks():
            if task.get("status") in ACTIVE_STATUSES:
                self.tasks.update(str(task["id"]), status=STATUS_PAUSE)
        self._notify()

    def _work_elapsed(self) -> float:
        if self._work_started is None:
            return 0.0
        paused = self._paused_seconds
        if self._paused_started is not None:
            paused += time.monotonic() - self._paused_started
        return max(0.0, time.monotonic() - self._work_started - paused)

    def _apply_cpu_threads(self) -> None:
        if self.cpu_threads > 0:
            os.environ["OMP_NUM_THREADS"] = str(self.cpu_threads)
            os.environ["CT2_NUM_THREADS"] = str(self.cpu_threads)

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()
