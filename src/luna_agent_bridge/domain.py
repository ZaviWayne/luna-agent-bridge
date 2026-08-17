"""领域状态、记录和异常。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    """返回 UTC ISO-8601 时间。"""
    return datetime.now(timezone.utc).isoformat()


class AgentState(StrEnum):
    """Agent 生命周期状态。"""

    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    INTERRUPTED = "interrupted"
    RESUMING = "resuming"
    RECOVERABLE = "recoverable"
    FAILED = "failed"
    ARCHIVED = "archived"


class MessageStatus(StrEnum):
    """消息投递状态。"""

    QUEUED = "queued"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"


ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.QUEUED: frozenset({AgentState.STARTING, AgentState.ARCHIVED}),
    AgentState.STARTING: frozenset({AgentState.RUNNING, AgentState.RECOVERABLE, AgentState.FAILED}),
    AgentState.RUNNING: frozenset({AgentState.IDLE, AgentState.INTERRUPTED, AgentState.RECOVERABLE, AgentState.FAILED}),
    AgentState.IDLE: frozenset({AgentState.RESUMING, AgentState.ARCHIVED}),
    AgentState.INTERRUPTED: frozenset({AgentState.RESUMING, AgentState.ARCHIVED}),
    AgentState.RESUMING: frozenset({AgentState.RUNNING, AgentState.RECOVERABLE, AgentState.FAILED}),
    AgentState.RECOVERABLE: frozenset({AgentState.RESUMING, AgentState.ARCHIVED}),
    AgentState.FAILED: frozenset({AgentState.RESUMING, AgentState.ARCHIVED}),
    AgentState.ARCHIVED: frozenset(),
}


class DomainError(RuntimeError):
    """领域错误基类。"""


class InvalidStateError(DomainError):
    """状态转换不合法。"""


class AgentNotFoundError(DomainError):
    """Agent 不存在。"""


class AgentAmbiguousError(DomainError):
    """Agent 名称无法唯一解析。"""


class WaitTimeoutError(DomainError):
    """等待超过指定时长。"""


def can_transition(current: AgentState, target: AgentState) -> bool:
    """判断状态转换是否被允许。"""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def require_transition(current: AgentState, target: AgentState) -> None:
    """校验状态转换，否则抛出领域错误。"""
    if not can_transition(current, target):
        raise InvalidStateError(f"不允许从 {current.value} 转换为 {target.value}")


@dataclass(frozen=True, slots=True)
class AgentRecord:
    """Agent 持久化记录。"""

    id: str
    name: str
    workspace: str
    owner_session_id: str
    state: AgentState
    model: str
    reasoning_effort: str
    sandbox: str
    approve_for_me: bool
    codex_thread_id: str | None
    last_result: str | None
    last_error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MessageRecord:
    """消息持久化记录。"""

    id: str
    agent_id: str
    sequence: int
    role: str
    content: str
    status: MessageStatus
    turn_id: str | None
    error: str | None
    created_at: str
    delivered_at: str | None


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """Codex 轮次持久化记录。"""

    id: str
    agent_id: str
    message_id: str
    state: str
    codex_thread_id: str | None
    exit_code: int | None
    result: str | None
    error: str | None
    usage: dict[str, Any]
    started_at: str
    finished_at: str | None
