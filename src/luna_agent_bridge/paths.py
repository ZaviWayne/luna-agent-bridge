"""Application paths and Codex executable discovery."""

from __future__ import annotations

from dataclasses import dataclass
import os
import getpass
import hashlib
import subprocess
from pathlib import Path
import shutil
import sys


class ConfigurationError(RuntimeError):
    """配置不可用。"""


UNIX_SOCKET_DIR = Path("/private/tmp")


@dataclass(frozen=True, slots=True)
class AppPaths:
    """用户级应用路径。"""

    root: Path
    bin_dir: Path
    broker_dir: Path
    data_dir: Path
    logs_dir: Path
    database: Path
    config: Path
    broker_key: Path
    pipe_lock: Path
    pipe_name: str
    pipe_family: str
    executable_name: str

    @classmethod
    def for_user(cls, root: Path | None = None, platform_name: str | None = None) -> "AppPaths":
        """返回当前用户的持久化路径。"""
        platform_name = platform_name or _current_platform()
        if root is None:
            if platform_name == "windows":
                local_app_data = os.environ.get("LOCALAPPDATA")
                if not local_app_data:
                    raise ConfigurationError("未找到当前用户的 LOCALAPPDATA 目录")
                root = Path(local_app_data) / "CodexLunaAgent"
            elif platform_name == "macos":
                root = Path.home() / "Library" / "Application Support" / "CodexLunaAgent"
            else:
                raise ConfigurationError("Luna Agent Bridge 仅支持 Windows 和 macOS")
        root = Path(root).expanduser().resolve()
        if platform_name == "windows":
            pipe_name = rf"\\.\pipe\codex-luna-agent-v1-{_effective_identity_suffix()}"
            pipe_family = "AF_PIPE"
            executable_name = "luna-agent.exe"
        elif platform_name == "macos":
            root_digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
            pipe_name = str(UNIX_SOCKET_DIR / f"codex-luna-agent-{root_digest}.sock")
            pipe_family = "AF_UNIX"
            executable_name = "luna-agent"
        else:
            raise ConfigurationError("Luna Agent Bridge 仅支持 Windows 和 macOS")
        return cls(
            root=root,
            bin_dir=root / "bin",
            broker_dir=root / "broker",
            data_dir=root / "data",
            logs_dir=root / "logs",
            database=root / "data" / "agents.db",
            config=root / "config.toml",
            broker_key=root / "data" / "broker.key",
            pipe_lock=root / "data" / "broker.lock",
            pipe_name=pipe_name,
            pipe_family=pipe_family,
            executable_name=executable_name,
        )

    def ensure_directories(self) -> None:
        """创建应用运行所需目录。"""
        for directory in (self.root, self.bin_dir, self.broker_dir, self.data_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
            if self.pipe_family == "AF_UNIX":
                directory.chmod(0o700)


def discover_codex_executable(explicit: Path | None = None) -> Path:
    """按用户配置和本机安装位置查找 Codex CLI。"""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        codex_bin = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
        if codex_bin.exists():
            candidates.extend(sorted(codex_bin.glob("*/codex.exe"), reverse=True))
    for command in ("codex.exe", "codex"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise ConfigurationError("未找到 Codex CLI 可执行文件")


def _effective_identity_suffix() -> str:
    """根据有效 Windows SID 生成用户专用命名管道后缀。"""
    identity = getpass.getuser().lower()
    if os.name == "nt":
        try:
            completed = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=False)
            fields = completed.stdout.strip().split('","')
            if completed.returncode == 0 and len(fields) >= 2:
                identity = fields[-1].strip('"').lower()
        except OSError:
            pass
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return digest


def _current_platform() -> str:
    """返回受支持的平台名称。"""
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "unsupported"
