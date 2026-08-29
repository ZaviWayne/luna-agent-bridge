"""Broker JSON 请求响应协议。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024
KNOWN_COMMANDS = frozenset({
    "health",
    "shutdown",
    "spawn",
    "send",
    "status",
    "list",
    "messages",
    "result",
    "wait",
    "interrupt",
    "resume",
    "archive",
    "adopt",
})


class ProtocolError(ValueError):
    """协议数据无效。"""


@dataclass(frozen=True, slots=True)
class BrokerRequest:
    """Broker 请求。"""

    version: int
    request_id: str
    command: str
    params: dict[str, Any]
    cwd: str


@dataclass(frozen=True, slots=True)
class BrokerResponse:
    """Broker 响应。"""

    request_id: str
    ok: bool
    data: Any = None
    error_code: str | None = None
    message: str | None = None
    log_path: str | None = None

    @classmethod
    def success(cls, request_id: str, data: Any = None) -> "BrokerResponse":
        """构造成功响应。"""
        return cls(request_id=request_id, ok=True, data=data)

    @classmethod
    def error(cls, request_id: str, error_code: str, message: str, log_path: str | None = None) -> "BrokerResponse":
        """构造错误响应。"""
        return cls(request_id=request_id, ok=False, error_code=error_code, message=message, log_path=log_path)


def encode_request(request: BrokerRequest) -> bytes:
    """编码请求 JSON。"""
    payload = {
        "version": request.version,
        "request_id": request.request_id,
        "command": request.command,
        "params": request.params,
        "cwd": request.cwd,
    }
    return _encode(payload)


def decode_request(raw: bytes) -> BrokerRequest:
    """解码并校验请求 JSON。"""
    payload = _decode(raw)
    if payload.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("不支持的 Broker 协议版本")
    request_id = payload.get("request_id")
    command = payload.get("command")
    params = payload.get("params")
    cwd = payload.get("cwd")
    if not isinstance(request_id, str) or not request_id:
        raise ProtocolError("request_id 必须为非空字符串")
    if command not in KNOWN_COMMANDS:
        raise ProtocolError(f"未知 Broker 命令：{command}")
    if not isinstance(params, dict):
        raise ProtocolError("params 必须为对象")
    if not isinstance(cwd, str) or not _is_absolute_path(cwd):
        raise ProtocolError("cwd 必须为绝对路径")
    return BrokerRequest(PROTOCOL_VERSION, request_id, command, params, cwd)


def encode_response(response: BrokerResponse) -> bytes:
    """编码响应 JSON。"""
    payload = {
        "request_id": response.request_id,
        "ok": response.ok,
        "data": _json_value(response.data),
        "error_code": response.error_code,
        "message": response.message,
        "log_path": response.log_path,
    }
    return _encode(payload)


def decode_response(raw: bytes) -> BrokerResponse:
    """解码响应 JSON。"""
    payload = _decode(raw)
    request_id = payload.get("request_id")
    ok = payload.get("ok")
    if not isinstance(request_id, str) or not isinstance(ok, bool):
        raise ProtocolError("响应缺少 request_id 或 ok")
    return BrokerResponse(
        request_id=request_id,
        ok=ok,
        data=payload.get("data"),
        error_code=payload.get("error_code"),
        message=payload.get("message"),
        log_path=payload.get("log_path"),
    )


def _encode(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Broker 消息超过 1 MiB 限制")
    return raw


def _decode(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Broker 消息超过 1 MiB 限制")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("Broker 消息不是有效 UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ProtocolError("Broker 消息必须为 JSON 对象")
    return payload


def _is_absolute_path(value: str) -> bool:
    windows_path = PureWindowsPath(value)
    is_windows_absolute = windows_path.is_absolute() and bool(windows_path.drive)
    return is_windows_absolute or PurePosixPath(value).is_absolute()


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {field: _json_value(getattr(value, field)) for field in value.__dataclass_fields__}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return value
