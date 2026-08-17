"""luna-agent 命令行入口。"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from enum import Enum
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from . import __version__
from .config import Settings
from .pipe_client import PipeClient
from .pipe_server import PipeServer
from .protocol import BrokerResponse
from .scheduler import Scheduler
from .session import resolve_session_id
from .service import AgentService
from .storage import Storage


EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_BROKER = 3
EXIT_STATE = 4
EXIT_TIMEOUT = 5
EXIT_CODEX = 6
EXIT_STORAGE = 7


def _add_session_argument(parser: argparse.ArgumentParser) -> None:
    """为会话相关命令添加可选会话标识。"""
    parser.add_argument("--session", help="覆盖当前 Codex 主会话标识")


def build_parser() -> argparse.ArgumentParser:
    """构造 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(prog="luna-agent", description="持久化 Luna 子 Agent 桥接器")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--app-root", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    spawn = subparsers.add_parser("spawn", help="创建 Agent")
    spawn.add_argument("--name", required=True)
    spawn.add_argument("--cwd")
    spawn.add_argument("--task", required=True)
    _add_session_argument(spawn)
    spawn.add_argument("--json", action="store_true")

    send = subparsers.add_parser("send", help="发送后续消息")
    send.add_argument("agent")
    send.add_argument("content")
    send.add_argument("--cwd")
    _add_session_argument(send)
    send.add_argument("--json", action="store_true")

    for command, help_text in (
        ("status", "查看 Agent 状态"),
        ("messages", "查看消息"),
        ("result", "查看最近结果"),
        ("interrupt", "中断 Agent"),
        ("resume", "恢复 Agent"),
        ("archive", "归档 Agent"),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("agent")
        command_parser.add_argument("--cwd")
        _add_session_argument(command_parser)
        command_parser.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list", help="列出 Agent")
    list_parser.add_argument("--all", action="store_true", dest="all_agents")
    list_parser.add_argument("--all-sessions", action="store_true")
    list_parser.add_argument("--include-archived", action="store_true")
    _add_session_argument(list_parser)
    list_parser.add_argument("--json", action="store_true")

    wait_parser = subparsers.add_parser("wait", help="等待 Agent")
    wait_parser.add_argument("agents", nargs="+")
    wait_parser.add_argument("--cwd")
    wait_parser.add_argument("--timeout", type=float)
    _add_session_argument(wait_parser)
    wait_parser.add_argument("--json", action="store_true")

    adopt_parser = subparsers.add_parser("adopt", help="接管 Agent 到当前会话")
    adopt_parser.add_argument("agent")
    adopt_parser.add_argument("--cwd")
    _add_session_argument(adopt_parser)
    adopt_parser.add_argument("--json", action="store_true")

    broker_parser = subparsers.add_parser("broker", help="管理 Broker")
    broker_parser.add_argument("broker_command", choices=("serve", "health", "shutdown"))
    broker_parser.add_argument("--json", action="store_true")

    install = subparsers.add_parser("install", help="安装用户级桥接器")
    install.add_argument("--json", action="store_true")

    uninstall = subparsers.add_parser("uninstall", help="卸载桥接器")
    uninstall.add_argument("--purge-data", action="store_true")
    uninstall.add_argument("--yes", action="store_true")
    uninstall.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None, client: PipeClient | None = None, paths=None) -> int:
    """执行 CLI 并返回稳定退出码。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    if paths is None:
        from .paths import AppPaths

        paths = AppPaths.for_user(Path(args.app_root) if args.app_root else None)
    if args.command == "broker" and args.broker_command == "serve":
        return _serve_broker(paths)
    if args.command == "install":
        from .installer import Installer

        result = Installer(paths).install(Path(sys.argv[0]).resolve())
        _print_data(result, args.json, "install")
        return EXIT_SUCCESS
    if args.command == "uninstall":
        from .installer import Installer

        if args.purge_data and not args.yes and not _confirm_purge():
            print("已取消删除持久化数据", file=sys.stderr)
            return EXIT_USAGE
        result = Installer(paths).uninstall(args.purge_data)
        _print_data(result, args.json, "uninstall")
        return EXIT_SUCCESS
    if client is None:
        client = PipeClient(paths, starter=lambda: _start_broker(paths))
    if args.command == "broker":
        command = args.broker_command
        response = client.request(command, {})
        return _finish_response(response, args.json, command)
    try:
        command, params = _command_params(args)
        response = client.request(command, params, cwd=str(Path.cwd().resolve()))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return EXIT_USAGE
    except ConnectionError as error:
        print(str(error), file=sys.stderr)
        return EXIT_BROKER
    except OSError as error:
        print(f"无法执行命令：{error}", file=sys.stderr)
        return EXIT_BROKER
    return _finish_response(response, getattr(args, "json", False), args.command)


def _command_params(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    session_id = resolve_session_id(getattr(args, "session", None))
    if args.command == "spawn":
        params = {"name": args.name, "task": args.task, "session_id": session_id}
        if args.cwd:
            params["cwd"] = str(Path(args.cwd).expanduser().resolve())
        return "spawn", params
    if args.command == "send":
        params = {"agent": args.agent, "content": args.content, "session_id": session_id}
        if args.cwd:
            params["cwd"] = str(Path(args.cwd).expanduser().resolve())
        return "send", params
    if args.command in {"status", "messages", "result", "interrupt", "resume", "archive"}:
        params = {"agent": args.agent, "session_id": session_id}
        if args.cwd:
            params["cwd"] = str(Path(args.cwd).expanduser().resolve())
        return args.command, params
    if args.command == "list":
        return "list", {
            "all": args.all_agents,
            "all_sessions": args.all_sessions,
            "include_archived": args.include_archived,
            "session_id": session_id,
        }
    if args.command == "wait":
        params: dict[str, Any] = {"agents": args.agents, "session_id": session_id}
        if args.cwd:
            params["cwd"] = str(Path(args.cwd).expanduser().resolve())
        if args.timeout is not None:
            params["timeout"] = args.timeout
        return "wait", params
    if args.command == "adopt":
        params = {"agent": args.agent, "session_id": session_id}
        if args.cwd:
            params["cwd"] = str(Path(args.cwd).expanduser().resolve())
        return "adopt", params
    raise ValueError(f"不支持的命令：{args.command}")


def _finish_response(response: BrokerResponse, json_output: bool, command: str) -> int:
    if not response.ok:
        message = response.message or "命令执行失败"
        print(message, file=sys.stderr)
        if response.log_path:
            print(f"日志：{response.log_path}", file=sys.stderr)
        return {
            "WAIT_TIMEOUT": EXIT_TIMEOUT,
            "INVALID_STATE": EXIT_STATE,
            "CODEX_ERROR": EXIT_CODEX,
            "INTERNAL_ERROR": EXIT_STORAGE,
            "LOOKUP_ERROR": EXIT_USAGE,
            "PROTOCOL_ERROR": EXIT_USAGE,
        }.get(response.error_code, EXIT_USAGE)
    _print_data(response.data, json_output, command)
    return EXIT_SUCCESS


def _print_data(data: Any, json_output: bool, command: str) -> None:
    value = _json_value(data)
    if not json_output and command == "result" and isinstance(value, dict) and value.get("last_result"):
        print(value["last_result"])
        return
    if json_output:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    elif isinstance(value, (dict, list)):
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print(value if value is not None else "")


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _start_broker(paths) -> None:
    """按需启动隐藏 Broker。"""
    paths.ensure_directories()
    if not _acquire_startup_lock(paths):
        return
    try:
        executable = paths.bin_dir / "luna-agent.exe"
        if executable.exists():
            argv = [str(executable), "broker", "serve"]
        else:
            argv = [sys.executable, "-m", "luna_agent_bridge", "--app-root", str(paths.root), "broker", "serve"]
        log_path = paths.logs_dir / "broker-launch.log"
        if os.name == "nt":
            process = _start_broker_via_powershell(argv, log_path)
        else:
            log_handle = log_path.open("a", encoding="utf-8")
            try:
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=log_handle,
                    close_fds=True,
                )
            finally:
                log_handle.close()
        paths.pipe_lock.write_text(str(process.pid), encoding="utf-8", newline="\n")
    except Exception:
        try:
            paths.pipe_lock.unlink()
        except FileNotFoundError:
            pass
        raise


def _start_broker_via_powershell(argv: list[str], log_path: Path):
    """通过 Windows 原生进程代理脱离当前受限 Job Object。"""
    executable = Path(argv[0]).resolve()
    argument_values = argv[1:]
    quoted_executable = _powershell_quote(str(executable))
    quoted_arguments = ",".join(_powershell_quote(value) for value in argument_values)
    script = (
        f"$p=Start-Process -WindowStyle Hidden -FilePath {quoted_executable} "
        f"-ArgumentList @({quoted_arguments}) -PassThru; Write-Output $p.Id"
    )
    encoded = __import__("base64").b64encode(script.encode("utf-16le")).decode("ascii")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        check=False,
        env=_normalized_windows_environment(),
    )
    if completed.returncode != 0:
        raise OSError(f"无法启动 Luna Broker：{completed.stderr.strip()}")
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if lines and lines[-1].isdigit():
        return _StartedProcess(int(lines[-1]))
    if completed.returncode == 0:
        return _StartedProcess(0)
    raise OSError("无法获取 Luna Broker 进程号")


def _normalized_windows_environment() -> dict[str, str]:
    """去除受限运行时注入的大小写重复环境变量。"""
    normalized: dict[str, str] = {}
    for key, value in os.environ.items():
        lower_key = key.lower()
        if lower_key not in normalized:
            normalized[lower_key] = value
    return {key.upper() if key == "path" else key.upper() if key in {"temp", "tmp"} else key: value for key, value in normalized.items()}


def _powershell_quote(value: str) -> str:
    """以单引号形式安全嵌入 PowerShell 脚本。"""
    return "'" + value.replace("'", "''") + "'"


class _StartedProcess:
    """仅保存代理启动返回的进程号。"""

    def __init__(self, pid: int):
        self.pid = pid


def _acquire_startup_lock(paths) -> bool:
    """获取 Broker 启动锁；清理已退出 Broker 遗留的锁文件。"""
    for _ in range(2):
        try:
            with paths.pipe_lock.open("x", encoding="utf-8"):
                pass
            return True
        except FileExistsError:
            if _startup_lock_active(paths):
                return False
            try:
                paths.pipe_lock.unlink()
            except FileNotFoundError:
                continue
    return False


def _startup_lock_active(paths) -> bool:
    """判断锁文件记录的 Broker 进程是否仍存活。"""
    try:
        value = paths.pipe_lock.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return False
    if not value:
        return True
    try:
        pid = int(value)
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _serve_broker(paths) -> int:
    settings = Settings.load(paths)
    storage = Storage.open(paths.database)
    storage.recover_incomplete_agents()
    scheduler = Scheduler(settings.max_workers)
    service = AgentService(storage, scheduler, settings)
    server = PipeServer(paths, service)
    try:
        server.serve_forever()
    finally:
        service.shutdown()
        storage.close()
    return EXIT_SUCCESS


def _confirm_purge() -> bool:
    try:
        return input("请输入 PURGE 确认删除持久化数据：").strip() == "PURGE"
    except EOFError:
        return False
