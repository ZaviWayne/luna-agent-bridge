"""Broker 命名管道客户端。"""

from __future__ import annotations

from dataclasses import dataclass
from multiprocessing.connection import Client
import os
from pathlib import Path
import secrets
import time
from typing import Callable, Any

from .paths import AppPaths
from .protocol import BrokerRequest, BrokerResponse, decode_response, encode_request


AUTHKEY_BYTES = 32
AUTHKEY_READ_ATTEMPTS = 100
AUTHKEY_READ_DELAY_SECONDS = 0.01


def load_or_create_authkey(paths: AppPaths) -> bytes:
    """读取或创建本机 Broker 认证密钥。"""
    paths.ensure_directories()
    if paths.broker_key.exists():
        return _read_authkey(paths)
    key = secrets.token_bytes(AUTHKEY_BYTES)
    try:
        descriptor = os.open(paths.broker_key, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return _read_authkey(paths)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key)
        handle.flush()
        os.fsync(handle.fileno())
    return key


def _read_authkey(paths: AppPaths) -> bytes:
    """等待并读取并发创建中的完整认证密钥。"""
    for _ in range(AUTHKEY_READ_ATTEMPTS):
        key = paths.broker_key.read_bytes()
        if len(key) == AUTHKEY_BYTES:
            return key
        time.sleep(AUTHKEY_READ_DELAY_SECONDS)
    raise RuntimeError("Luna Broker 认证密钥不完整")


class PipeClient:
    """通过认证命名管道发送 Broker 请求。"""

    def __init__(self, paths: AppPaths, starter: Callable[[], None] | None = None, connect_timeout_seconds: float = 10.0):
        self.paths = paths
        self.starter = starter
        self.connect_timeout_seconds = connect_timeout_seconds

    def request(self, command: str, params: dict[str, Any], cwd: str | None = None) -> BrokerResponse:
        """发送命令并等待响应。"""
        request = BrokerRequest(
            version=1,
            request_id=secrets.token_hex(16),
            command=command,
            params=params,
            cwd=cwd or str(Path.cwd().resolve()),
        )
        key = load_or_create_authkey(self.paths)
        connection = self._connect(key)
        try:
            connection.send_bytes(encode_request(request))
            return decode_response(connection.recv_bytes())
        finally:
            connection.close()

    def _connect(self, key: bytes):
        deadline = time.monotonic() + self.connect_timeout_seconds
        started = False
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return Client(self.paths.pipe_name, family=self.paths.pipe_family, authkey=key)
            except (OSError, EOFError, ConnectionRefusedError) as error:
                last_error = error
                if self.starter is not None and not started:
                    self.starter()
                    started = True
                time.sleep(0.05)
        raise ConnectionError("无法连接 Luna Broker") from last_error
