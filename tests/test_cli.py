import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.cli import _normalized_windows_environment, _start_broker, build_parser, main
from luna_agent_bridge.paths import AppPaths
from luna_agent_bridge.protocol import BrokerResponse


class FakeClient:
    def __init__(self):
        self.response = BrokerResponse.success("r1", {"status": "ok"})
        self.requests = []

    def request(self, command, params, cwd=None):
        self.requests.append((command, params, cwd))
        return self.response


class CliTests(unittest.TestCase):
    def test_broker_proxy_environment_has_one_case_insensitive_path(self):
        with patch.dict("luna_agent_bridge.cli.os.environ", {"Path": "one", "PATH": "two", "TEMP": "t", "Temp": "u"}, clear=True):
            environment = _normalized_windows_environment()
        names = [name.lower() for name in environment]
        self.assertEqual(1, names.count("path"))
        self.assertEqual(1, names.count("temp"))

    def test_broker_startup_uses_hidden_proxy_and_keeps_lock_until_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.for_user(Path(directory) / "app", platform_name="windows")

            with patch(
                "luna_agent_bridge.cli.subprocess.Popen"
            ) as popen, patch(
                "luna_agent_bridge.cli.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="1234\r\n", stderr=""),
            ) as run:
                _start_broker(paths)

            popen.assert_not_called()
            run.assert_called_once()
            command = run.call_args.args[0]
            self.assertIn("-EncodedCommand", command)
            self.assertTrue(paths.pipe_lock.exists())
            self.assertEqual("1234", paths.pipe_lock.read_text(encoding="utf-8"))

    def test_broker_proxy_does_not_redirect_child_stdio(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.for_user(Path(directory) / "app", platform_name="windows")
            with patch(
                "luna_agent_bridge.cli.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="1234\r\n", stderr=""),
            ) as run:
                _start_broker(paths)
            script = __import__("base64").b64decode(run.call_args.args[0][-1]).decode("utf-16le")
            self.assertNotIn("RedirectStandardOutput", script)
            self.assertNotIn("RedirectStandardError", script)

    def test_broker_proxy_allows_empty_stdout_when_start_process_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.for_user(Path(directory) / "app", platform_name="windows")
            with patch("luna_agent_bridge.cli.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")):
                _start_broker(paths)
            self.assertTrue(paths.pipe_lock.exists())

    def test_source_broker_startup_passes_app_root_to_child(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.for_user(Path(directory) / "app", platform_name="windows")
            with patch("luna_agent_bridge.cli.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="1234\r\n", stderr="")) as run:
                with patch("luna_agent_bridge.cli.Path.exists", return_value=False):
                    _start_broker(paths)
            command = run.call_args.args[0]
            encoded = command[-1]
            import base64

            script = base64.b64decode(encoded).decode("utf-16le")
            self.assertIn(str(paths.root), script)

    def test_macos_broker_starts_in_detached_session(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.for_user(Path(directory) / "app", platform_name="macos")
            paths.ensure_directories()
            (paths.bin_dir / paths.executable_name).write_bytes(b"binary")
            process = SimpleNamespace(pid=1234)
            with patch("luna_agent_bridge.cli.subprocess.Popen", return_value=process) as popen:
                with patch.object(sys, "frozen", True, create=True):
                    _start_broker(paths)
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            self.assertEqual("1", popen.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"])
            self.assertEqual("1234", paths.pipe_lock.read_text(encoding="utf-8"))
            self.assertIn("--app-root", popen.call_args.args[0])
            self.assertIn(str(paths.root), popen.call_args.args[0])

    def test_spawn_defaults_to_current_directory(self):
        args = build_parser().parse_args(["spawn", "--name", "reviewer", "--task", "检查修改"])
        self.assertEqual("spawn", args.command)
        self.assertIsNone(args.cwd)

    def test_wait_timeout_maps_to_exit_code_five(self):
        client = FakeClient()
        client.response = BrokerResponse.error("r1", "WAIT_TIMEOUT", "等待超时")
        self.assertEqual(5, main(["wait", "reviewer", "--timeout", "1"], client=client))

    def test_spawn_sends_expected_parameters(self):
        client = FakeClient()
        with patch.dict("luna_agent_bridge.cli.os.environ", {"CODEX_THREAD_ID": "desktop"}):
            with redirect_stdout(io.StringIO()):
                exit_code = main(["spawn", "--name", "reviewer", "--task", "检查"], client=client)
        self.assertEqual(0, exit_code)
        self.assertEqual("spawn", client.requests[0][0])
        self.assertEqual("desktop", client.requests[0][1]["session_id"])
        self.assertEqual("reviewer", client.requests[0][1]["name"])
        self.assertEqual("检查", client.requests[0][1]["task"])

    def test_list_all_sessions_sends_flag(self):
        client = FakeClient()
        main(["list", "--all-sessions"], client=client)
        self.assertTrue(client.requests[0][1]["all_sessions"])

    def test_adopt_command_is_available(self):
        args = build_parser().parse_args(["adopt", "agent-id"])
        self.assertEqual("adopt", args.command)

    def test_help_contains_all_lifecycle_commands(self):
        help_text = build_parser().format_help()
        for command in ("spawn", "send", "status", "list", "messages", "result", "wait", "interrupt", "resume", "archive"):
            self.assertIn(command, help_text)


if __name__ == "__main__":
    unittest.main()
