"""受控 Codex 子进程及其平台进程组生命周期。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Sequence

from .codex_adapter import CodexInvocation


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:
    _kernel32 = None


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _WindowsJob:
    """每个 Codex 子进程独占的 Job Object。"""

    def __init__(self):
        self.handle = None
        if _kernel32 is None:
            return
        handle = _kernel32.CreateJobObjectW(None, None)
        if not handle:
            return
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        success = _kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not success:
            _kernel32.CloseHandle(handle)
            return
        self.handle = handle

    def assign(self, process_handle: int) -> None:
        """将子进程加入 Job Object。"""
        if self.handle is not None and _kernel32 is not None:
            _kernel32.AssignProcessToJobObject(self.handle, process_handle)

    def terminate(self, exit_code: int = 1) -> None:
        """终止 Job 中的子进程。"""
        if self.handle is not None and _kernel32 is not None:
            _kernel32.TerminateJobObject(self.handle, exit_code)

    def close(self) -> None:
        """关闭 Job 句柄。"""
        if self.handle is not None and _kernel32 is not None:
            _kernel32.CloseHandle(self.handle)
            self.handle = None


class RunningProcess:
    """已启动的受控进程。"""

    def __init__(self, process: subprocess.Popen[bytes], job: _WindowsJob, owns_process_group: bool):
        self.process = process
        self.job = job
        self.owns_process_group = owns_process_group

    @property
    def pid(self) -> int:
        """返回进程 ID。"""
        return self.process.pid

    def poll(self) -> int | None:
        """返回进程退出码。"""
        return self.process.poll()

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes, int]:
        """读取 stdout/stderr 并等待进程结束。"""
        try:
            stdout, stderr = self.process.communicate(timeout=timeout)
        finally:
            if self.process.poll() is not None:
                self.job.close()
        return stdout, stderr, self.process.returncode

    def _close_pipes(self) -> None:
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()

    def interrupt(self, grace_seconds: float = 5.0) -> None:
        """先优雅终止，超时后只终止本 Agent 所属进程。"""
        if self.process.poll() is not None:
            self._close_pipes()
            self.job.close()
            return
        if os.name == "nt":
            try:
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            except (AttributeError, OSError):
                self.process.terminate()
        else:
            self._signal_process_group(signal.SIGTERM)
        deadline = time.monotonic() + grace_seconds
        while self.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if self.process.poll() is None:
            if os.name == "nt":
                self.job.terminate(130)
            else:
                self._signal_process_group(signal.SIGKILL)
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        self._close_pipes()
        self.job.close()

    def _signal_process_group(self, signal_number: int) -> None:
        """向当前 Agent 独占的 POSIX 进程组发送信号。"""
        try:
            if self.owns_process_group:
                os.killpg(self.process.pid, signal_number)
            else:
                self.process.send_signal(signal_number)
        except ProcessLookupError:
            return


class ProcessController:
    """创建并拥有 Codex 子进程。"""

    def start(self, invocation: CodexInvocation) -> RunningProcess:
        """启动指定命令。"""
        invocation.cwd.mkdir(parents=True, exist_ok=True)
        creationflags = 0
        startupinfo = None
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(
            list(invocation.argv),
            cwd=str(invocation.cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            startupinfo=startupinfo,
            start_new_session=os.name != "nt",
        )
        job = _WindowsJob()
        if job.handle is not None:
            job.assign(process._handle)
        return RunningProcess(process, job, owns_process_group=os.name != "nt")
