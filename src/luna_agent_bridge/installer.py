"""用户级安装、升级和卸载。"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable

from .paths import AppPaths, ConfigurationError


BEGIN_MARKER = "<!-- BEGIN CODEX LUNA AGENT BRIDGE -->"
END_MARKER = "<!-- END CODEX LUNA AGENT BRIDGE -->"
PATH_SEPARATOR = ";"


class UserPathStore:
    """当前用户 PATH 读写适配器。"""

    def get(self) -> str:
        """读取当前用户 PATH。"""
        if os.name != "nt":
            return os.environ.get("PATH", "")
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                return str(value)
        except FileNotFoundError:
            return ""

    def set(self, value: str) -> None:
        """写入当前用户 PATH。"""
        if os.name != "nt":
            return
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, value)
        _broadcast_environment_change()


class Installer:
    """执行用户级安装和卸载。"""

    def __init__(
        self,
        paths: AppPaths,
        home: Path | None = None,
        path_store: UserPathStore | None = None,
        acl_runner: Callable[[Path], None] | None = None,
    ):
        self.paths = paths
        self.home = Path(home or Path.home()).expanduser().resolve()
        self.path_store = path_store or UserPathStore()
        self.acl_runner = acl_runner or _apply_current_user_acl
        self.agents_file = self.home / "AGENTS.md"
        self.skill_dir = self.home / ".codex" / "skills" / "luna-agent-bridge"

    def install(self, source_exe: Path) -> dict[str, str]:
        """安装或升级可执行文件和全局规则。"""
        source_exe = Path(source_exe).expanduser().resolve()
        if not source_exe.is_file():
            raise ConfigurationError(f"安装源文件不存在：{source_exe}")
        self.paths.ensure_directories()
        backup_dir = self._backup_existing_files()
        target_exe = self.paths.bin_dir / "luna-agent.exe"
        _copy_atomic(source_exe, target_exe)
        skill_source = _asset_path("SKILL.md")
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        _copy_atomic(skill_source, self.skill_dir / "SKILL.md")
        block = _asset_path("AGENTS.block.md").read_text(encoding="utf-8")
        self._write_agents_block(block)
        if not self.paths.config.exists():
            _write_atomic(
                self.paths.config,
                "model = \"gpt-5.6-luna\"\nmodel_reasoning_effort = \"max\"\nsandbox = \"workspace-write\"\napprove_for_me = true\nmax_workers = 4\n",
            )
        self._add_path_entry(self.paths.bin_dir)
        for directory in (self.paths.root, self.paths.bin_dir, self.paths.broker_dir, self.paths.data_dir, self.paths.logs_dir):
            self.acl_runner(directory)
        return {
            "executable": str(target_exe),
            "database": str(self.paths.database),
            "skill": str(self.skill_dir / "SKILL.md"),
            "agents": str(self.agents_file),
            "backup": str(backup_dir) if backup_dir else "",
        }

    def uninstall(self, purge_data: bool = False) -> dict[str, str | bool]:
        """卸载桥接器；默认保留 Agent 数据和日志。"""
        target_exe = self.paths.bin_dir / "luna-agent.exe"
        if target_exe.exists():
            target_exe.unlink()
        if self.skill_dir.exists():
            shutil.rmtree(self.skill_dir)
        if self.agents_file.exists():
            self._remove_agents_block()
        self._remove_path_entry(self.paths.bin_dir)
        purged = False
        if purge_data:
            for target in (self.paths.data_dir, self.paths.logs_dir, self.paths.broker_dir):
                self._remove_owned_directory(target)
            purged = True
        return {"uninstalled": True, "purged_data": purged, "data_dir": str(self.paths.data_dir)}

    def _backup_existing_files(self) -> Path | None:
        existing: list[tuple[Path, Path]] = []
        if self.agents_file.exists():
            existing.append((self.agents_file, Path("AGENTS.md")))
        skill_file = self.skill_dir / "SKILL.md"
        if skill_file.exists():
            existing.append((skill_file, Path("skill") / "SKILL.md"))
        if not existing:
            return None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = self.paths.root / "backups" / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        for source, relative in existing:
            destination = backup_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return backup_dir

    def _write_agents_block(self, block: str) -> None:
        existing = self.agents_file.read_text(encoding="utf-8") if self.agents_file.exists() else ""
        start = existing.find(BEGIN_MARKER)
        end = existing.find(END_MARKER)
        if start >= 0 and end >= start:
            end += len(END_MARKER)
            content = existing[:start].rstrip() + "\n\n" + block.strip() + existing[end:]
        else:
            content = existing.rstrip() + ("\n\n" if existing.strip() else "") + block.strip() + "\n"
        self.agents_file.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(self.agents_file, content)

    def _remove_agents_block(self) -> None:
        content = self.agents_file.read_text(encoding="utf-8")
        start = content.find(BEGIN_MARKER)
        end = content.find(END_MARKER)
        if start >= 0 and end >= start:
            end += len(END_MARKER)
            content = (content[:start] + content[end:]).strip()
            if content:
                _write_atomic(self.agents_file, content + "\n")
            else:
                self.agents_file.unlink()

    def _add_path_entry(self, entry: Path) -> None:
        entries = [item for item in self.path_store.get().split(PATH_SEPARATOR) if item]
        normalized = str(entry).casefold()
        entries = [item for item in entries if item.casefold() != normalized]
        entries.append(str(entry))
        self.path_store.set(PATH_SEPARATOR.join(entries))

    def _remove_path_entry(self, entry: Path) -> None:
        normalized = str(entry).casefold()
        entries = [item for item in self.path_store.get().split(PATH_SEPARATOR) if item and item.casefold() != normalized]
        self.path_store.set(PATH_SEPARATOR.join(entries))

    def _remove_owned_directory(self, target: Path) -> None:
        target = target.resolve()
        if target.parent != self.paths.root.resolve():
            raise ConfigurationError("拒绝删除非桥接器目录")
        if target.exists():
            shutil.rmtree(target)


def _asset_path(name: str) -> Path:
    """定位打包前或 PyInstaller 运行时资源。"""
    bundle_root = getattr(__import__("sys"), "_MEIPASS", None)
    if bundle_root:
        candidate = Path(bundle_root) / "assets" / name
    else:
        candidate = Path(__file__).resolve().parents[2] / "assets" / name
    if not candidate.is_file():
        raise ConfigurationError(f"缺少安装资源：{candidate}")
    return candidate


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _apply_current_user_acl(path: Path) -> None:
    """限制目录 ACL 为当前用户；非 Windows 开发环境跳过。"""
    if os.name != "nt":
        return
    result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConfigurationError("无法获取当前用户 SID")
    rows = list(csv.reader(line for line in result.stdout.splitlines() if line.strip()))
    if not rows or len(rows[0]) < 2:
        raise ConfigurationError("无法解析当前用户 SID")
    sid = rows[0][1].strip()
    grant = f"{sid}:(OI)(CI)F"
    command = ["icacls", str(path), "/inheritance:r", "/grant:r", grant]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        inherited = subprocess.run(["icacls", str(path)], capture_output=True, text=True, check=False)
        permissions = inherited.stdout + inherited.stderr
        if inherited.returncode == 0 and "Everyone:(F)" not in permissions and "BUILTIN\\Users:(F)" not in permissions:
            return
        raise ConfigurationError(f"无法设置目录权限：{path}")


def _broadcast_environment_change() -> None:
    if os.name != "nt":
        return
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None)
