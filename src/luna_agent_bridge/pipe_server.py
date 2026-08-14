"""Luna Broker 命名管道服务端。"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from multiprocessing.connection import Listener
from pathlib import Path
import threading
import traceback
from typing import Any

from .domain import DomainError, WaitTimeoutError
from .paths import AppPaths
from .pipe_client import load_or_create_authkey
from .protocol import BrokerRequest, BrokerResponse, ProtocolError, decode_request, encode_response
from .session import STANDALONE_SESSION_ID


class PipeServer:
    """仅监听本机命名管道的 Broker。"""

    def __init__(self, paths: AppPaths, service: Any):
        self.paths = paths
        self.service = service
        self._stop_event = threading.Event()
        self._listener = None

    def serve_forever(self) -> None:
        """启动并持续接受客户端。"""
        self.paths.ensure_directories()
        authkey = load_or_create_authkey(self.paths)
        self._listener = Listener(self.paths.pipe_name, family="AF_PIPE", authkey=authkey)
        try:
            self.paths.pipe_lock.unlink()
        except FileNotFoundError:
            pass
        try:
            while not self._stop_event.is_set():
                try:
                    connection = self._listener.accept()
                except (OSError, EOFError):
                    if self._stop_event.is_set():
                        break
                    continue
                threading.Thread(target=self._handle_connection, args=(connection,), daemon=True).start()
        finally:
            self._listener.close()
            self._listener = None

    def stop(self) -> None:
        """停止服务端。"""
        self._stop_event.set()
        listener = self._listener
        if listener is not None:
            listener.close()

    def _handle_connection(self, connection) -> None:
        try:
            raw = connection.recv_bytes()
            request = decode_request(raw)
            response = self.dispatch(request)
        except ProtocolError as error:
            response = BrokerResponse.error("unknown", "PROTOCOL_ERROR", str(error))
        except Exception as error:  # noqa: BLE001 - Broker boundary must not kill accept loop.
            response = BrokerResponse.error("unknown", "INTERNAL_ERROR", "Broker 内部错误")
            self._write_error_log(error)
        try:
            connection.send_bytes(encode_response(response))
        except (OSError, EOFError):
            pass
        finally:
            connection.close()

    def dispatch(self, request: BrokerRequest) -> BrokerResponse:
        """分发单个请求。"""
        try:
            data = self._dispatch_command(request)
            return BrokerResponse.success(request.request_id, data)
        except WaitTimeoutError as error:
            return BrokerResponse.error(request.request_id, "WAIT_TIMEOUT", str(error))
        except (KeyError, ValueError) as error:
            return BrokerResponse.error(request.request_id, "LOOKUP_ERROR", str(error))
        except DomainError as error:
            return BrokerResponse.error(request.request_id, "INVALID_STATE", str(error))
        except Exception as error:  # noqa: BLE001 - structured boundary response.
            log_path = self._write_error_log(error)
            return BrokerResponse.error(request.request_id, "INTERNAL_ERROR", "Broker 内部错误", log_path)

    def _dispatch_command(self, request: BrokerRequest) -> Any:
        params = request.params
        cwd = Path(request.cwd)
        session_id = params.get("session_id", STANDALONE_SESSION_ID)
        if request.command == "health":
            return {"status": "ok"}
        if request.command == "shutdown":
            self.service.shutdown()
            self.stop()
            return {"status": "stopping"}
        if request.command == "spawn":
            return self.service.spawn(
                params["name"], params.get("cwd", request.cwd), params["task"], session_id
            )
        if request.command == "send":
            return self.service.send(
                params["agent"], params["content"], params.get("cwd", request.cwd), session_id
            )
        if request.command == "status":
            return self.service.status(params["agent"], params.get("cwd", request.cwd), session_id)
        if request.command == "list":
            workspace = None if params.get("all") else cwd
            owner_session_id = None if params.get("all") or params.get("all_sessions") else session_id
            return self.service.list_agents(workspace, bool(params.get("include_archived")), owner_session_id)
        if request.command == "messages":
            return self.service.messages(params["agent"], params.get("cwd", request.cwd), session_id)
        if request.command == "result":
            return self.service.result(params["agent"], params.get("cwd", request.cwd), session_id)
        if request.command == "wait":
            return self.service.wait(
                params["agents"], params.get("cwd", request.cwd), params.get("timeout"), session_id
            )
        if request.command == "interrupt":
            return self.service.interrupt(params["agent"], params.get("cwd", request.cwd), session_id)
        if request.command == "resume":
            return self.service.resume(params["agent"], params.get("cwd", request.cwd), session_id)
        if request.command == "archive":
            return self.service.archive(params["agent"], params.get("cwd", request.cwd), session_id)
        if request.command == "adopt":
            return self.service.adopt(params["agent"], session_id, params.get("cwd", request.cwd))
        raise ProtocolError(f"未知 Broker 命令：{request.command}")

    def _write_error_log(self, error: Exception) -> str:
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        path = self.paths.logs_dir / "broker-errors.log"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(traceback.format_exc())
            handle.write("\n")
        return str(path)
