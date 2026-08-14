"""Agent 生命周期和消息投递服务。"""

from __future__ import annotations

from collections.abc import Callable
import threading
import time
from pathlib import Path
from typing import Any

from .codex_adapter import (
    CodexCommandFactory,
    CodexEventParser,
    CodexTurnResult,
)
from .config import Settings
from .domain import (
    AgentRecord,
    AgentState,
    DomainError,
    MessageRecord,
    MessageStatus,
    TurnRecord,
    WaitTimeoutError,
)
from .process_control import ProcessController, RunningProcess
from .scheduler import Scheduler, SchedulerBusyError
from .session import STANDALONE_SESSION_ID, validate_session_id
from .storage import Storage


TERMINAL_WAIT_STATES = frozenset({
    AgentState.IDLE,
    AgentState.INTERRUPTED,
    AgentState.RECOVERABLE,
    AgentState.FAILED,
    AgentState.ARCHIVED,
})
RUNNING_STATES = frozenset({AgentState.STARTING, AgentState.RUNNING, AgentState.RESUMING})


class AgentService:
    """编排 Agent、消息、Codex 轮次和调度器。"""

    def __init__(
        self,
        storage: Storage,
        scheduler: Scheduler,
        settings: Settings,
        execute_turn: Callable[[AgentRecord, MessageRecord, TurnRecord], CodexTurnResult] | None = None,
        process_controller: ProcessController | None = None,
        command_factory: CodexCommandFactory | None = None,
    ):
        self.storage = storage
        self.scheduler = scheduler
        self.settings = settings.validate()
        self._execute_override = execute_turn
        self.process_controller = process_controller or ProcessController()
        if command_factory is None and execute_turn is None:
            command_factory = CodexCommandFactory(self.settings.resolve_codex_executable(), self.settings)
        self.command_factory = command_factory
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._active_agents: set[str] = set()
        self._running_handles: dict[str, RunningProcess] = {}
        self._interrupt_requested: set[str] = set()

    def spawn(
        self,
        name: str,
        workspace: Path | str,
        task: str,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> AgentRecord:
        """创建 Agent 并投递首条消息。"""
        workspace_path = Path(workspace).expanduser().resolve()
        if not workspace_path.is_dir():
            raise DomainError(f"工作区不存在：{workspace_path}")
        with self._lock:
            agent = self.storage.create_agent(name, workspace_path, self.settings, owner_session_id)
            self.storage.enqueue_message(agent.id, task)
            self._schedule_agent(agent.id)
            return self.storage.get_agent(agent.id)

    def send(
        self,
        identifier: str,
        content: str,
        workspace: Path | str | None = None,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> MessageRecord:
        """向 Agent 发送消息；运行中消息在轮次边界投递。"""
        with self._lock:
            agent = self.storage.resolve_agent(identifier, workspace, owner_session_id)
            if agent.state == AgentState.ARCHIVED:
                raise DomainError("已归档的 Agent 不能接收消息")
            message = self.storage.enqueue_message(agent.id, content)
            if agent.state == AgentState.IDLE:
                self.storage.transition_agent(agent.id, AgentState.RESUMING)
                self._schedule_agent(agent.id)
            self._condition.notify_all()
            return message

    def status(
        self,
        identifier: str,
        workspace: Path | str | None = None,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> AgentRecord:
        """获取 Agent 状态。"""
        return self.storage.resolve_agent(identifier, workspace, owner_session_id)

    def list_agents(
        self,
        workspace: Path | str | None = None,
        include_archived: bool = False,
        owner_session_id: str | None = STANDALONE_SESSION_ID,
    ) -> list[AgentRecord]:
        """列出 Agent。"""
        return self.storage.list_agents(workspace, include_archived, owner_session_id)

    def messages(
        self,
        identifier: str,
        workspace: Path | str | None = None,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> list[MessageRecord]:
        """读取 Agent 消息。"""
        agent = self.storage.resolve_agent(identifier, workspace, owner_session_id)
        return self.storage.list_messages(agent.id)

    def result(
        self,
        identifier: str,
        workspace: Path | str | None = None,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> AgentRecord:
        """读取 Agent 最近结果。"""
        return self.storage.resolve_agent(identifier, workspace, owner_session_id)

    def wait(
        self,
        identifiers: list[str],
        workspace: Path | str | None = None,
        timeout_seconds: float | None = None,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> list[AgentRecord]:
        """等待多个 Agent 进入可等待终态。"""
        agents = [
            self.storage.resolve_agent(identifier, workspace, owner_session_id)
            for identifier in identifiers
        ]
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        with self._condition:
            while True:
                current = [self.storage.get_agent(agent.id) for agent in agents]
                if all(agent.state in TERMINAL_WAIT_STATES for agent in current):
                    return current
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise WaitTimeoutError("等待超时")
                    self._condition.wait(min(remaining, 0.1))
                else:
                    self._condition.wait(0.1)

    def interrupt(
        self,
        identifier: str,
        workspace: Path | str | None = None,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> AgentRecord:
        """中断正在运行的 Agent。"""
        with self._lock:
            agent = self.storage.resolve_agent(identifier, workspace, owner_session_id)
            if agent.state not in (AgentState.RUNNING, AgentState.STARTING, AgentState.RESUMING):
                raise DomainError("当前 Agent 不在运行状态")
            self._interrupt_requested.add(agent.id)
            handle = self._running_handles.get(agent.id)
        if handle is not None:
            handle.interrupt(self.settings.interrupt_grace_seconds)
        with self._condition:
            self._condition.notify_all()
            return self.storage.get_agent(agent.id)

    def resume(
        self,
        identifier: str,
        workspace: Path | str | None = None,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> AgentRecord:
        """恢复可恢复 Agent 的原 Codex 会话。"""
        with self._lock:
            agent = self.storage.resolve_agent(identifier, workspace, owner_session_id)
            if agent.state not in (AgentState.INTERRUPTED, AgentState.RECOVERABLE, AgentState.FAILED):
                raise DomainError("当前 Agent 不需要恢复")
            if not agent.codex_thread_id:
                raise DomainError("Agent 没有可恢复的 Codex 会话")
            self.storage.transition_agent(agent.id, AgentState.RESUMING)
            self._schedule_agent(agent.id)
            return self.storage.get_agent(agent.id)

    def archive(
        self,
        identifier: str,
        workspace: Path | str | None = None,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> AgentRecord:
        """归档非运行 Agent。"""
        with self._lock:
            agent = self.storage.resolve_agent(identifier, workspace, owner_session_id)
            if agent.state in RUNNING_STATES:
                raise DomainError("运行中的 Agent 必须先中断")
            archived = self.storage.archive_agent(agent.id)
            self._condition.notify_all()
            return archived

    def adopt(
        self,
        identifier: str,
        owner_session_id: str,
        workspace: Path | str | None = None,
    ) -> AgentRecord:
        """将非归档 Agent 接管到当前主会话。"""
        return self.storage.adopt_agent(identifier, validate_session_id(owner_session_id), workspace)

    def shutdown(self) -> None:
        """中断已知子进程并停止调度。"""
        with self._lock:
            handles = list(self._running_handles.values())
        for handle in handles:
            handle.interrupt(self.settings.interrupt_grace_seconds)
        self.scheduler.shutdown(wait=True)

    def _schedule_agent(self, agent_id: str) -> None:
        if agent_id in self._active_agents:
            return
        self._active_agents.add(agent_id)
        try:
            self.scheduler.submit(agent_id, lambda: self._run_agent(agent_id))
        except SchedulerBusyError:
            self._active_agents.discard(agent_id)

    def _run_agent(self, agent_id: str) -> None:
        try:
            self._prepare_running_state(agent_id)
            while True:
                with self._lock:
                    agent = self.storage.get_agent(agent_id)
                    if agent.state not in (AgentState.RUNNING, AgentState.STARTING, AgentState.RESUMING):
                        return
                    if agent.state in (AgentState.STARTING, AgentState.RESUMING):
                        agent = self.storage.transition_agent(agent_id, AgentState.RUNNING)
                    message = self.storage.claim_next_message(agent_id)
                    if message is None:
                        if agent.state == AgentState.RUNNING:
                            self.storage.transition_agent(agent_id, AgentState.IDLE)
                        self._condition.notify_all()
                        with self._lock:
                            if self.storage.has_queued_messages(agent_id):
                                self.storage.transition_agent(agent_id, AgentState.RESUMING)
                                continue
                            self._active_agents.discard(agent_id)
                            return
                    turn = self.storage.create_turn(agent_id, message.id)
                    self._condition.notify_all()
                try:
                    result = self._execute_turn(agent, message, turn)
                except Exception as error:  # noqa: BLE001 - boundary converts worker errors to Agent state.
                    self._finish_failed(agent, message, turn, str(error))
                    return
                with self._lock:
                    interrupted = agent_id in self._interrupt_requested
                    self._interrupt_requested.discard(agent_id)
                    if interrupted:
                        self.storage.requeue_message(message.id, "Agent 被中断，等待恢复")
                        self.storage.finish_turn(
                            turn.id,
                            "interrupted",
                            result.thread_id,
                            None,
                            None,
                            "Agent 被中断",
                            result.usage,
                        )
                        self.storage.update_agent_after_turn(
                            agent_id, AgentState.INTERRUPTED, result.thread_id, None, "Agent 被中断"
                        )
                        self._condition.notify_all()
                        return
                    if result.error:
                        self._finish_failed(agent, message, turn, result.error, result)
                        return
                    self.storage.mark_message_delivered(message.id, turn.id)
                    self.storage.finish_turn(
                        turn.id,
                        "completed",
                        result.thread_id,
                        0,
                        result.final_text,
                        None,
                        result.usage,
                    )
                    self.storage.update_agent_after_turn(
                        agent_id, AgentState.IDLE, result.thread_id, result.final_text, None
                    )
                    self._condition.notify_all()
                    if self.storage.has_queued_messages(agent_id):
                        self.storage.transition_agent(agent_id, AgentState.RESUMING)
                        continue
                    self._active_agents.discard(agent_id)
                    return
        finally:
            with self._lock:
                self._running_handles.pop(agent_id, None)
                self._active_agents.discard(agent_id)
                self._condition.notify_all()

    def _prepare_running_state(self, agent_id: str) -> None:
        with self._lock:
            agent = self.storage.get_agent(agent_id)
            if agent.state == AgentState.QUEUED:
                self.storage.transition_agent(agent_id, AgentState.STARTING)
            if self.storage.get_agent(agent_id).state in (AgentState.STARTING, AgentState.RESUMING):
                self.storage.transition_agent(agent_id, AgentState.RUNNING)
            self._condition.notify_all()

    def _execute_turn(self, agent: AgentRecord, message: MessageRecord, turn: TurnRecord) -> CodexTurnResult:
        if self._execute_override is not None:
            return self._execute_override(agent, message, turn)
        if self.command_factory is None:
            raise RuntimeError("Codex 命令工厂未初始化")
        if agent.codex_thread_id:
            invocation = self.command_factory.resume(agent.codex_thread_id, message.content, Path(agent.workspace))
        else:
            invocation = self.command_factory.spawn(Path(agent.workspace), message.content)
        process = self.process_controller.start(invocation)
        with self._lock:
            self._running_handles[agent.id] = process
        try:
            stdout, stderr, exit_code = process.communicate()
        finally:
            with self._lock:
                self._running_handles.pop(agent.id, None)
        parser = CodexEventParser()
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            parser.feed(line)
        for event in parser.events:
            self.storage.add_event(agent.id, turn.id, event)
        result = parser.result(exit_code)
        if stderr and exit_code != 0:
            error_text = stderr.decode("utf-8", errors="replace").strip()
            if error_text and result.error is None:
                result = CodexTurnResult(result.thread_id, result.final_text, result.usage, result.events, error_text)
        return result

    def _finish_failed(
        self,
        agent: AgentRecord,
        message: MessageRecord,
        turn: TurnRecord,
        error: str,
        result: CodexTurnResult | None = None,
    ) -> None:
        with self._lock:
            self.storage.mark_message_failed(message.id, error)
            self.storage.finish_turn(
                turn.id,
                "failed",
                result.thread_id if result else agent.codex_thread_id,
                None,
                result.final_text if result else None,
                error,
                result.usage if result else {},
            )
            self.storage.update_agent_after_turn(
                agent.id,
                AgentState.FAILED,
                result.thread_id if result else agent.codex_thread_id,
                result.final_text if result else None,
                error,
            )
            self._condition.notify_all()
