import tempfile
import threading
import time
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.codex_adapter import CodexTurnResult
from luna_agent_bridge.config import Settings
from luna_agent_bridge.domain import AgentState, MessageStatus, WaitTimeoutError
from luna_agent_bridge.scheduler import Scheduler
from luna_agent_bridge.service import AgentService
from luna_agent_bridge.storage import Storage


class FakeExecutor:
    def __init__(self):
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self, agent, message, turn):
        self.calls.append((agent.id, message.content, turn.id))
        self.started.set()
        if len(self.calls) == 1:
            self.release.wait(3)
        return CodexTurnResult(
            thread_id="thread-1",
            final_text=f"完成：{message.content}",
            usage={"output_tokens": 1},
            events=(),
        )


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name) / "project"
        self.workspace.mkdir()
        self.storage = Storage.open(Path(self.directory.name) / "agents.db")
        self.scheduler = Scheduler(max_workers=2)
        self.executor = FakeExecutor()
        self.service = AgentService(self.storage, self.scheduler, Settings.defaults(), execute_turn=self.executor)

    def tearDown(self):
        self.executor.release.set()
        self.scheduler.shutdown(wait=True)
        self.storage.close()
        self.directory.cleanup()

    def _wait_state(self, agent_id, state):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.service.status(agent_id).state == state:
                return
            time.sleep(0.01)
        self.fail(f"未等到状态 {state}")

    def test_send_while_running_is_delivered_after_current_turn(self):
        agent = self.service.spawn("reviewer", self.workspace, "第一轮")
        self.assertTrue(self.executor.started.wait(2))
        self._wait_state(agent.id, AgentState.RUNNING)
        second = self.service.send(agent.id, "第二轮")
        self.assertEqual(MessageStatus.QUEUED, second.status)
        self.executor.release.set()
        self._wait_state(agent.id, AgentState.IDLE)
        self.assertEqual(["第一轮", "第二轮"], [call[1] for call in self.executor.calls])
        self.assertEqual("完成：第二轮", self.service.result(agent.id).last_result)

    def test_wait_timeout_does_not_interrupt_agent(self):
        agent = self.service.spawn("slow", self.workspace, "慢任务")
        self.assertTrue(self.executor.started.wait(2))
        with self.assertRaises(WaitTimeoutError):
            self.service.wait([agent.id], timeout_seconds=0.01)
        self.assertEqual(AgentState.RUNNING, self.service.status(agent.id).state)

    def test_same_name_isolated_between_parent_sessions(self):
        first = self.service.spawn("reviewer", self.workspace, "会话 A", "session-a")
        second = self.service.spawn("reviewer", self.workspace, "会话 B", "session-b")
        self.executor.release.set()
        self.service.wait([first.id, second.id], timeout_seconds=3)
        self.assertEqual(first.id, self.service.status("reviewer", self.workspace, "session-a").id)
        self.assertEqual(second.id, self.service.status("reviewer", self.workspace, "session-b").id)


if __name__ == "__main__":
    unittest.main()
