"""Codex CLI invocation construction and JSONL parsing."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .config import Settings


class CodexProtocolError(RuntimeError):
    """Codex JSONL 输出不符合预期。"""


@dataclass(frozen=True, slots=True)
class CodexInvocation:
    """待启动的 Codex 子进程。"""

    argv: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True, slots=True)
class CodexTurnResult:
    """Codex 一轮执行结果。"""

    thread_id: str | None
    final_text: str
    usage: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    error: str | None = None


class CodexCommandFactory:
    """根据固定安全策略构造 Codex 参数。"""

    def __init__(self, executable: Path, settings: Settings):
        self.executable = Path(executable).resolve()
        self.settings = settings.validate()

    def spawn(self, cwd: Path, prompt: str) -> CodexInvocation:
        """构造首轮执行命令。"""
        workspace = Path(cwd).expanduser().resolve()
        argv = (
            str(self.executable),
            "exec",
            "--skip-git-repo-check",
            "--cd",
            str(workspace),
            "--model",
            self.settings.model,
            "--config",
            f'model_reasoning_effort="{self.settings.reasoning_effort}"',
            "--approve-for-me",
            "--json",
            prompt,
        )
        return CodexInvocation(argv=argv, cwd=workspace)

    def resume(self, thread_id: str, prompt: str, cwd: Path | None = None) -> CodexInvocation:
        """构造续聊命令。"""
        argv = (
            str(self.executable),
            "exec",
            "resume",
            "--model",
            self.settings.model,
            "--config",
            f'model_reasoning_effort="{self.settings.reasoning_effort}"',
            "--skip-git-repo-check",
            "--json",
            thread_id,
            prompt,
        )
        return CodexInvocation(argv=argv, cwd=(Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()))


class CodexEventParser:
    """逐行解析 Codex JSONL 事件。"""

    def __init__(self):
        self.thread_id: str | None = None
        self.final_text_parts: list[str] = []
        self.usage: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []

    def feed(self, line: str) -> None:
        """解析一行；非 JSON 的警告行会被忽略。"""
        try:
            payload = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        event_type = payload.get("type")
        if event_type == "thread.started":
            self.thread_id = payload.get("thread_id")
            self.events.append(payload)
            return
        if event_type == "item.completed":
            item = payload.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str):
                    self.final_text_parts.append(text)
                return
        if event_type == "turn.completed":
            usage = payload.get("usage")
            if isinstance(usage, dict):
                self.usage = usage
            return
        self.events.append(payload)

    def result(self, exit_code: int) -> CodexTurnResult:
        """生成结果并校验成功轮次的必要字段。"""
        final_text = "\n".join(self.final_text_parts)
        if exit_code == 0 and not self.thread_id:
            raise CodexProtocolError("Codex 成功退出但没有返回 thread_id")
        if exit_code == 0 and not final_text:
            raise CodexProtocolError("Codex 成功退出但没有返回 Agent 消息")
        return CodexTurnResult(
            thread_id=self.thread_id,
            final_text=final_text,
            usage=dict(self.usage),
            events=tuple(self.events),
            error=None if exit_code == 0 else f"Codex 退出码：{exit_code}",
        )
