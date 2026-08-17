"""SQLite persistence for Agents, messages, turns, and recovery."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterable
from uuid import uuid4

from .config import Settings
from .domain import (
    AgentRecord,
    AgentState,
    InvalidStateError,
    MessageRecord,
    MessageStatus,
    TurnRecord,
    require_transition,
    utc_now,
)
from .session import LEGACY_SESSION_ID, STANDALONE_SESSION_ID, validate_session_id


SCHEMA_VERSION = 2
RECOVERY_ERROR = "Broker 异常退出，任务可恢复"
RECOVERABLE_STATES = (AgentState.STARTING.value, AgentState.RUNNING.value, AgentState.RESUMING.value)


class Storage:
    """线程安全的 SQLite 存储。"""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._lock = threading.RLock()

    @classmethod
    def open(cls, path: Path) -> "Storage":
        """打开或创建数据库。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
        connection.row_factory = sqlite3.Row
        storage = cls(connection)
        storage._initialize()
        return storage

    def close(self) -> None:
        """关闭数据库连接。"""
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _initialize(self) -> None:
        with self._lock:
            connection = self._connection
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    owner_session_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    model TEXT NOT NULL,
                    reasoning_effort TEXT NOT NULL,
                    sandbox TEXT NOT NULL,
                    approve_for_me INTEGER NOT NULL,
                    codex_thread_id TEXT,
                    last_result TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                    message_id TEXT NOT NULL REFERENCES messages(id),
                    state TEXT NOT NULL,
                    codex_thread_id TEXT,
                    exit_code INTEGER,
                    result TEXT,
                    error TEXT,
                    usage_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    turn_id TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    delivered_at TEXT,
                    UNIQUE(agent_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                    turn_id TEXT,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS broker_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_agent_sequence ON messages(agent_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_messages_status_created ON messages(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_agents_state_updated ON agents(state, updated_at);
                CREATE INDEX IF NOT EXISTS idx_events_agent_id ON events(agent_id, id);
                """
            )
            row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_agents_workspace_session_name "
                    "ON agents(workspace, owner_session_id, name, state)"
                )
            elif row["version"] == 1:
                self._migrate_v1_to_v2()
            elif row["version"] != SCHEMA_VERSION:
                raise RuntimeError("不支持的数据库版本")
            connection.commit()

    def _migrate_v1_to_v2(self) -> None:
        """将版本 1 数据库原子升级到版本 2。"""
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                f"ALTER TABLE agents ADD COLUMN owner_session_id TEXT NOT NULL DEFAULT '{LEGACY_SESSION_ID}'"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agents_workspace_session_name "
                "ON agents(workspace, owner_session_id, name, state)"
            )
            connection.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def create_agent(
        self,
        name: str,
        workspace: Path | str,
        settings: Settings,
        owner_session_id: str = STANDALONE_SESSION_ID,
    ) -> AgentRecord:
        """创建 Agent。"""
        settings.validate()
        owner_session_id = validate_session_id(owner_session_id)
        workspace_value = str(Path(workspace).expanduser().resolve())
        now = utc_now()
        agent_id = str(uuid4())
        with self._lock:
            active = self._connection.execute(
                "SELECT id FROM agents WHERE name = ? AND workspace = ? AND owner_session_id = ? "
                "AND state != ? LIMIT 1",
                (name, workspace_value, owner_session_id, AgentState.ARCHIVED.value),
            ).fetchone()
            if active is not None:
                raise ValueError("同一工作区和会话内已存在同名 Agent")
            self._connection.execute(
                """
                INSERT INTO agents(
                    id, name, workspace, owner_session_id, state, model, reasoning_effort, sandbox,
                    approve_for_me, codex_thread_id, last_result, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (
                    agent_id,
                    name,
                    workspace_value,
                    owner_session_id,
                    AgentState.QUEUED.value,
                    settings.model,
                    settings.reasoning_effort,
                    settings.sandbox,
                    int(settings.approve_for_me),
                    now,
                    now,
                ),
            )
            self._connection.commit()
            return self.get_agent(agent_id)

    def get_agent(self, agent_id: str) -> AgentRecord:
        """按 ID 获取 Agent。"""
        with self._lock:
            row = self._connection.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(f"Agent 不存在：{agent_id}")
        return self._agent_from_row(row)

    def resolve_agent(
        self,
        identifier: str,
        workspace: Path | str | None = None,
        owner_session_id: str | None = None,
        include_archived: bool = False,
    ) -> AgentRecord:
        """按全局 ID 或工作区会话内名称解析 Agent。"""
        with self._lock:
            by_id = self._connection.execute("SELECT * FROM agents WHERE id = ?", (identifier,)).fetchone()
            if by_id is not None:
                return self._agent_from_row(by_id)
            if workspace is None:
                raise KeyError(f"Agent 不存在：{identifier}")
            workspace_value = str(Path(workspace).expanduser().resolve())
            query = "SELECT * FROM agents WHERE name = ? AND workspace = ?"
            params: list[Any] = [identifier, workspace_value]
            if owner_session_id is not None:
                query += " AND owner_session_id = ?"
                params.append(validate_session_id(owner_session_id))
            if not include_archived:
                query += " AND state != ?"
                params.append(AgentState.ARCHIVED.value)
            rows = self._connection.execute(query, params).fetchall()
        if not rows:
            raise KeyError(f"Agent 不存在：{identifier}")
        if len(rows) > 1:
            raise ValueError(f"Agent 名称不唯一：{identifier}")
        return self._agent_from_row(rows[0])

    def list_agents(
        self,
        workspace: Path | str | None = None,
        include_archived: bool = False,
        owner_session_id: str | None = None,
    ) -> list[AgentRecord]:
        """按工作区和会话范围列出 Agent。"""
        query = "SELECT * FROM agents"
        params: list[Any] = []
        clauses: list[str] = []
        if workspace is not None:
            clauses.append("workspace = ?")
            params.append(str(Path(workspace).expanduser().resolve()))
        if owner_session_id is not None:
            clauses.append("owner_session_id = ?")
            params.append(validate_session_id(owner_session_id))
        if not include_archived:
            clauses.append("state != ?")
            params.append(AgentState.ARCHIVED.value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._agent_from_row(row) for row in rows]

    def adopt_agent(
        self,
        identifier: str,
        owner_session_id: str,
        workspace: Path | str | None = None,
    ) -> AgentRecord:
        """将非归档 Agent 转移到指定会话。"""
        owner_session_id = validate_session_id(owner_session_id)
        agent = self.resolve_agent(identifier, workspace)
        if agent.state == AgentState.ARCHIVED:
            raise ValueError("已归档的 Agent 不能接管")
        with self._lock:
            self._connection.execute(
                "UPDATE agents SET owner_session_id = ?, updated_at = ? WHERE id = ?",
                (owner_session_id, utc_now(), agent.id),
            )
            self._connection.commit()
            return self.get_agent(agent.id)

    def enqueue_message(self, agent_id: str, content: str, role: str = "user") -> MessageRecord:
        """按 Agent 顺序追加消息。"""
        message_id = str(uuid4())
        now = utc_now()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM messages WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            sequence = int(row["next_sequence"])
            self._connection.execute(
                """
                INSERT INTO messages(id, agent_id, sequence, role, content, status, turn_id, error, created_at, delivered_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL)
                """,
                (message_id, agent_id, sequence, role, content, MessageStatus.QUEUED.value, now),
            )
            self._connection.commit()
            return self.get_message(message_id)

    def claim_next_message(self, agent_id: str) -> MessageRecord | None:
        """以 FIFO 顺序领取下一条待发送消息。"""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT * FROM messages WHERE agent_id = ? AND status = ? ORDER BY sequence LIMIT 1",
                (agent_id, MessageStatus.QUEUED.value),
            ).fetchone()
            if row is None:
                self._connection.commit()
                return None
            self._connection.execute(
                "UPDATE messages SET status = ? WHERE id = ?",
                (MessageStatus.DELIVERING.value, row["id"]),
            )
            self._connection.commit()
            return self.get_message(row["id"])

    def mark_message_delivered(self, message_id: str, turn_id: str) -> None:
        """标记消息已投递。"""
        with self._lock:
            self._connection.execute(
                "UPDATE messages SET status = ?, turn_id = ?, delivered_at = ? WHERE id = ?",
                (MessageStatus.DELIVERED.value, turn_id, utc_now(), message_id),
            )
            self._connection.commit()

    def mark_message_failed(self, message_id: str, error: str) -> None:
        """标记消息投递失败。"""
        with self._lock:
            self._connection.execute(
                "UPDATE messages SET status = ?, error = ?, delivered_at = ? WHERE id = ?",
                (MessageStatus.FAILED.value, error, utc_now(), message_id),
            )
            self._connection.commit()

    def requeue_message(self, message_id: str, error: str | None = None) -> None:
        """将中断或可恢复轮次的消息重新放回队列。"""
        with self._lock:
            self._connection.execute(
                "UPDATE messages SET status = ?, turn_id = NULL, error = ?, delivered_at = NULL WHERE id = ?",
                (MessageStatus.QUEUED.value, error, message_id),
            )
            self._connection.commit()

    def get_message(self, message_id: str) -> MessageRecord:
        """按 ID 获取消息。"""
        with self._lock:
            row = self._connection.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise KeyError(f"消息不存在：{message_id}")
        return self._message_from_row(row)

    def list_messages(self, agent_id: str) -> list[MessageRecord]:
        """按顺序列出 Agent 消息。"""
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM messages WHERE agent_id = ? ORDER BY sequence", (agent_id,)
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def has_queued_messages(self, agent_id: str) -> bool:
        """判断 Agent 是否还有待投递消息。"""
        with self._lock:
            row = self._connection.execute(
                "SELECT 1 FROM messages WHERE agent_id = ? AND status = ? LIMIT 1",
                (agent_id, MessageStatus.QUEUED.value),
            ).fetchone()
        return row is not None

    def create_turn(self, agent_id: str, message_id: str) -> TurnRecord:
        """创建执行轮次。"""
        turn_id = str(uuid4())
        now = utc_now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO turns(id, agent_id, message_id, state, codex_thread_id, exit_code, result, error, usage_json, started_at, finished_at)
                VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, '{}', ?, NULL)
                """,
                (turn_id, agent_id, message_id, "running", now),
            )
            self._connection.commit()
            return self.get_turn(turn_id)

    def finish_turn(
        self,
        turn_id: str,
        state: str,
        codex_thread_id: str | None = None,
        exit_code: int | None = None,
        result: str | None = None,
        error: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> TurnRecord:
        """完成执行轮次。"""
        with self._lock:
            self._connection.execute(
                """
                UPDATE turns SET state = ?, codex_thread_id = ?, exit_code = ?, result = ?, error = ?, usage_json = ?, finished_at = ?
                WHERE id = ?
                """,
                (state, codex_thread_id, exit_code, result, error, json.dumps(usage or {}, ensure_ascii=False), utc_now(), turn_id),
            )
            self._connection.commit()
            return self.get_turn(turn_id)

    def get_turn(self, turn_id: str) -> TurnRecord:
        """按 ID 获取轮次。"""
        with self._lock:
            row = self._connection.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None:
            raise KeyError(f"轮次不存在：{turn_id}")
        return self._turn_from_row(row)

    def list_turns(self, agent_id: str) -> list[TurnRecord]:
        """按开始时间列出轮次。"""
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM turns WHERE agent_id = ? ORDER BY started_at", (agent_id,)
            ).fetchall()
        return [self._turn_from_row(row) for row in rows]

    def transition_agent(self, agent_id: str, target: AgentState, error: str | None = None) -> AgentRecord:
        """校验并持久化 Agent 状态转换。"""
        with self._lock:
            current = self.get_agent(agent_id)
            require_transition(current.state, target)
            self._connection.execute(
                "UPDATE agents SET state = ?, last_error = ?, updated_at = ? WHERE id = ?",
                (target.value, error, utc_now(), agent_id),
            )
            self._connection.commit()
            return self.get_agent(agent_id)

    def update_agent_after_turn(
        self,
        agent_id: str,
        target: AgentState,
        thread_id: str | None,
        result: str | None,
        error: str | None,
    ) -> AgentRecord:
        """保存轮次结果并转换 Agent 状态。"""
        with self._lock:
            current = self.get_agent(agent_id)
            require_transition(current.state, target)
            self._connection.execute(
                """
                UPDATE agents SET state = ?, codex_thread_id = COALESCE(?, codex_thread_id), last_result = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (target.value, thread_id, result, error, utc_now(), agent_id),
            )
            self._connection.commit()
            return self.get_agent(agent_id)

    def archive_agent(self, agent_id: str) -> AgentRecord:
        """归档非运行 Agent。"""
        return self.transition_agent(agent_id, AgentState.ARCHIVED)

    def add_event(self, agent_id: str, turn_id: str | None, event: dict[str, Any]) -> None:
        """保存结构化事件并保留最近 1,000 条。"""
        with self._lock:
            self._connection.execute(
                "INSERT INTO events(agent_id, turn_id, event_json, created_at) VALUES (?, ?, ?, ?)",
                (agent_id, turn_id, json.dumps(event, ensure_ascii=False), utc_now()),
            )
            self._connection.execute(
                """
                DELETE FROM events WHERE agent_id = ? AND id NOT IN (
                    SELECT id FROM events WHERE agent_id = ? ORDER BY id DESC LIMIT 1000
                )
                """,
                (agent_id, agent_id),
            )
            self._connection.commit()

    def recover_incomplete_agents(self) -> int:
        """将 Broker 异常退出时遗留的运行状态标记为可恢复。"""
        with self._lock:
            placeholders = ",".join("?" for _ in RECOVERABLE_STATES)
            now = utc_now()
            rows = self._connection.execute(
                f"SELECT id FROM agents WHERE state IN ({placeholders})", RECOVERABLE_STATES
            ).fetchall()
            if not rows:
                return 0
            ids = [row["id"] for row in rows]
            self._connection.execute(
                f"UPDATE agents SET state = ?, last_error = ?, updated_at = ? WHERE state IN ({placeholders})",
                (AgentState.RECOVERABLE.value, RECOVERY_ERROR, now, *RECOVERABLE_STATES),
            )
            self._connection.execute(
                f"UPDATE turns SET state = ?, error = ?, finished_at = ? WHERE state = 'running' AND agent_id IN ({','.join('?' for _ in ids)})",
                ("recoverable", RECOVERY_ERROR, now, *ids),
            )
            self._connection.commit()
            return len(ids)

    def force_state_for_test(self, agent_id: str, state: AgentState) -> None:
        """测试专用状态写入。"""
        with self._lock:
            self._connection.execute("UPDATE agents SET state = ?, updated_at = ? WHERE id = ?", (state.value, utc_now(), agent_id))
            self._connection.commit()

    def _agent_from_row(self, row: sqlite3.Row) -> AgentRecord:
        return AgentRecord(
            id=row["id"],
            name=row["name"],
            workspace=row["workspace"],
            owner_session_id=row["owner_session_id"],
            state=AgentState(row["state"]),
            model=row["model"],
            reasoning_effort=row["reasoning_effort"],
            sandbox=row["sandbox"],
            approve_for_me=bool(row["approve_for_me"]),
            codex_thread_id=row["codex_thread_id"],
            last_result=row["last_result"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _message_from_row(self, row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            sequence=int(row["sequence"]),
            role=row["role"],
            content=row["content"],
            status=MessageStatus(row["status"]),
            turn_id=row["turn_id"],
            error=row["error"],
            created_at=row["created_at"],
            delivered_at=row["delivered_at"],
        )

    def _turn_from_row(self, row: sqlite3.Row) -> TurnRecord:
        return TurnRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            message_id=row["message_id"],
            state=row["state"],
            codex_thread_id=row["codex_thread_id"],
            exit_code=row["exit_code"],
            result=row["result"],
            error=row["error"],
            usage=json.loads(row["usage_json"] or "{}"),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
