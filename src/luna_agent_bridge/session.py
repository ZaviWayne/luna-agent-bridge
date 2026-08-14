"""主 Agent 会话上下文解析。"""

from __future__ import annotations

import os
from collections.abc import Mapping


STANDALONE_SESSION_ID = "standalone"
LEGACY_SESSION_ID = "legacy"
MAX_SESSION_ID_LENGTH = 128
CODEX_THREAD_ID_ENV = "CODEX_THREAD_ID"


def validate_session_id(value: str) -> str:
    """校验并返回会话标识。"""
    if not isinstance(value, str):
        raise ValueError("会话标识必须为字符串")
    if not value or value != value.strip():
        raise ValueError("会话标识不能为空或包含首尾空白")
    if len(value) > MAX_SESSION_ID_LENGTH:
        raise ValueError(f"会话标识不能超过 {MAX_SESSION_ID_LENGTH} 个字符")
    if any(ord(character) < 32 for character in value):
        raise ValueError("会话标识不能包含控制字符")
    return value


def resolve_session_id(explicit: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """按显式参数、Codex 环境变量和独立会话回退值解析会话标识。"""
    if explicit is not None:
        return validate_session_id(explicit)
    environment = os.environ if environ is None else environ
    value = environment.get(CODEX_THREAD_ID_ENV)
    if value is None or value == "":
        value = STANDALONE_SESSION_ID
    return validate_session_id(value)
