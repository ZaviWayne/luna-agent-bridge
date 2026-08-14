"""全局配置加载和校验。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import tomllib

from .paths import AppPaths, ConfigurationError, discover_codex_executable


DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_REASONING_EFFORT = "max"
DEFAULT_SANDBOX = "workspace-write"
MAX_WORKERS = 4
SUPPORTED_SANDBOXES = frozenset({"read-only", "workspace-write"})


@dataclass(frozen=True, slots=True)
class Settings:
    """Broker 运行配置。"""

    model: str = DEFAULT_MODEL
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    sandbox: str = DEFAULT_SANDBOX
    approve_for_me: bool = True
    max_workers: int = MAX_WORKERS
    codex_executable: Path | None = None
    pipe_start_timeout_seconds: float = 10.0
    interrupt_grace_seconds: float = 5.0
    retry_delays_seconds: tuple[float, ...] = (1.0, 2.0, 4.0)

    @classmethod
    def defaults(cls) -> "Settings":
        """返回默认配置。"""
        return cls()

    @classmethod
    def load(cls, paths: AppPaths) -> "Settings":
        """读取用户级 TOML 配置，不存在时返回默认值。"""
        settings = cls.defaults()
        if paths.config.exists():
            with paths.config.open("rb") as handle:
                raw = tomllib.load(handle)
            settings = replace(
                settings,
                model=raw.get("model", settings.model),
                reasoning_effort=raw.get("model_reasoning_effort", settings.reasoning_effort),
                sandbox=raw.get("sandbox", settings.sandbox),
                approve_for_me=raw.get("approve_for_me", settings.approve_for_me),
                max_workers=raw.get("max_workers", settings.max_workers),
                codex_executable=Path(raw["codex_executable"]) if raw.get("codex_executable") else None,
                pipe_start_timeout_seconds=float(raw.get("pipe_start_timeout_seconds", settings.pipe_start_timeout_seconds)),
                interrupt_grace_seconds=float(raw.get("interrupt_grace_seconds", settings.interrupt_grace_seconds)),
            )
        return settings.validate()

    def validate(self) -> "Settings":
        """校验并返回配置。"""
        if self.model != DEFAULT_MODEL:
            raise ConfigurationError("Luna Agent Bridge 只允许使用 gpt-5.6-luna")
        if self.reasoning_effort != DEFAULT_REASONING_EFFORT:
            raise ConfigurationError("Luna Agent Bridge 只允许使用 max 推理强度")
        if self.sandbox not in SUPPORTED_SANDBOXES:
            raise ConfigurationError("沙箱模式必须为 read-only 或 workspace-write")
        if not self.approve_for_me:
            raise ConfigurationError("Luna Agent Bridge 要求启用自动审批")
        if not 1 <= self.max_workers <= MAX_WORKERS:
            raise ConfigurationError("并发数必须在 1 到 4 之间")
        if self.pipe_start_timeout_seconds <= 0 or self.interrupt_grace_seconds <= 0:
            raise ConfigurationError("超时时间必须大于 0")
        return self

    def resolve_codex_executable(self) -> Path:
        """解析 Codex CLI 路径。"""
        return discover_codex_executable(self.codex_executable)
