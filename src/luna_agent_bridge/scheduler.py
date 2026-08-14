"""公平 FIFO 调度器和 Agent 串行化。"""

from __future__ import annotations

from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
import threading
from typing import Callable, Any


class SchedulerBusyError(RuntimeError):
    """同一 Agent 已有任务排队或运行。"""


@dataclass(slots=True)
class _Job:
    agent_id: str
    callable: Callable[[], Any]
    future: Future


class Scheduler:
    """最多固定数量 worker 的 FIFO 调度器。"""

    def __init__(self, max_workers: int = 4):
        if not 1 <= max_workers <= 4:
            raise ValueError("调度器并发数必须在 1 到 4 之间")
        self.max_workers = max_workers
        self._condition = threading.Condition()
        self._queue: deque[_Job] = deque()
        self._reserved_agents: set[str] = set()
        self._running_agents: set[str] = set()
        self._stopping = False
        self._workers = [
            threading.Thread(target=self._worker_loop, name=f"luna-worker-{index}", daemon=True)
            for index in range(max_workers)
        ]
        for worker in self._workers:
            worker.start()

    def submit(self, agent_id: str, task: Callable[[], Any]) -> Future:
        """提交 Agent 任务并返回 Future。"""
        with self._condition:
            if self._stopping:
                raise RuntimeError("调度器已停止")
            if agent_id in self._reserved_agents:
                raise SchedulerBusyError(f"Agent 已有任务排队或运行：{agent_id}")
            future: Future = Future()
            self._queue.append(_Job(agent_id, task, future))
            self._reserved_agents.add(agent_id)
            self._condition.notify()
            return future

    def running_count(self) -> int:
        """返回当前运行任务数量。"""
        with self._condition:
            return len(self._running_agents)

    def queued_count(self) -> int:
        """返回等待任务数量。"""
        with self._condition:
            return len(self._queue)

    def shutdown(self, wait: bool = True) -> None:
        """停止调度器并取消尚未开始的任务。"""
        with self._condition:
            self._stopping = True
            while self._queue:
                job = self._queue.popleft()
                self._reserved_agents.discard(job.agent_id)
                job.future.cancel()
            self._condition.notify_all()
        if wait:
            for worker in self._workers:
                worker.join(timeout=10)

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._stopping:
                    self._condition.wait()
                if self._stopping and not self._queue:
                    return
                job = self._queue.popleft()
                self._running_agents.add(job.agent_id)
            if not job.future.set_running_or_notify_cancel():
                with self._condition:
                    self._running_agents.discard(job.agent_id)
                    self._reserved_agents.discard(job.agent_id)
                    self._condition.notify_all()
                continue
            try:
                result = job.callable()
            except BaseException as error:  # Future must receive worker exceptions.
                job.future.set_exception(error)
            else:
                job.future.set_result(result)
            finally:
                with self._condition:
                    self._running_agents.discard(job.agent_id)
                    self._reserved_agents.discard(job.agent_id)
                    self._condition.notify_all()
