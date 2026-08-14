from dataclasses import dataclass
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.paths import AppPaths
from luna_agent_bridge.pipe_client import PipeClient
from luna_agent_bridge.pipe_server import PipeServer
from luna_agent_bridge.protocol import (
    BrokerRequest,
    ProtocolError,
    decode_request,
    encode_request,
)


class ProtocolPipeTests(unittest.TestCase):
    def test_request_round_trip_uses_json_bytes(self):
        request = BrokerRequest(version=1, request_id="r1", command="status", params={"agent": "a1"}, cwd=r"D:\p")
        self.assertEqual(request, decode_request(encode_request(request)))

    def test_unknown_command_is_rejected(self):
        with self.assertRaises(ProtocolError):
            decode_request(b'{"version":1,"request_id":"r1","command":"delete","params":{},"cwd":"D:\\\\p"}')

    def test_named_pipe_health_and_parallel_clients(self):
        with tempfile.TemporaryDirectory() as directory:
            base = AppPaths.for_user(Path(directory) / "app")
            paths = replace(base, pipe_name=rf"\\.\pipe\codex-luna-test-{uuid4().hex}")
            server = PipeServer(paths, _FakeService())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            client = PipeClient(paths, starter=lambda: None, connect_timeout_seconds=3)
            deadline = time.monotonic() + 3
            while True:
                try:
                    self.assertEqual({"status": "ok"}, client.request("health", {}).data)
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            responses = []

            def request_health():
                responses.append(client.request("health", {}).data)

            workers = [threading.Thread(target=request_health) for _ in range(20)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=3)
            self.assertEqual(20, len(responses))
            self.assertTrue(all(response == {"status": "ok"} for response in responses))
            server.stop()
            thread.join(timeout=3)


@dataclass
class _FakeService:
    def list_agents(self, *args, **kwargs):
        return []


if __name__ == "__main__":
    unittest.main()
