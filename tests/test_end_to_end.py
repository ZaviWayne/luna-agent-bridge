import tempfile
import time
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.codex_adapter import CodexTurnResult
from luna_agent_bridge.config import Settings
from luna_agent_bridge.domain import AgentState, WaitTimeoutError
from luna_agent_bridge.scheduler import Scheduler
from luna_agent_bridge.service import AgentService
from luna_agent_bridge.storage import Storage


class DeterministicCodex:
    def __init__(self):
        self.calls = []

    def __call__(self, agent, message, turn):
        self.calls.append((agent.id, message.content, agent.codex_thread_id))
        return CodexTurnResult(
            thread_id=agent.codex_thread_id or "thread-persistent",
            final_text=message.content,
            usage={"output_tokens": 1},
            events=(),
        )


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.workspace = self.root / "project"
        self.workspace.mkdir()
        self.storage = Storage.open(self.root / "agents.db")
        self.scheduler = Scheduler(max_workers=4)
        self.executor = DeterministicCodex()
        self.service = AgentService(self.storage, self.scheduler, Settings.defaults(), execute_turn=self.executor)

    def tearDown(self):
        self.scheduler.shutdown(wait=True)
        self.storage.close()
        self.directory.cleanup()

    def test_spawn_send_resume_uses_same_thread_id_and_persists(self):
        agent = self.service.spawn("acceptance", self.workspace, "第一轮")
        self.service.wait([agent.id], timeout_seconds=2)
        first = self.service.status(agent.id)
        self.assertEqual("thread-persistent", first.codex_thread_id)
        self.service.send(agent.id, "第二轮")
        self.service.wait([agent.id], timeout_seconds=2)
        second = self.service.status(agent.id)
        self.assertEqual(first.codex_thread_id, second.codex_thread_id)
        self.assertEqual("第二轮", second.last_result)
        self.assertEqual(2, len(self.executor.calls))

        self.scheduler.shutdown(wait=True)
        self.storage.close()
        reopened = Storage.open(self.root / "agents.db")
        persisted = reopened.get_agent(agent.id)
        self.assertEqual(AgentState.IDLE, persisted.state)
        self.assertEqual("thread-persistent", persisted.codex_thread_id)
        reopened.close()

    def test_fifth_agent_is_queued_under_four_slot_limit(self):
        blockers = []
        release = __import__("threading").Event()
        original = self.executor

        def blocked(agent, message, turn):
            blockers.append(time.monotonic())
            release.wait(2)
            return original(agent, message, turn)

        self.service._execute_override = blocked
        for index in range(5):
            (self.workspace / str(index)).mkdir()
        agents = [self.service.spawn(f"a{index}", self.workspace / str(index), "任务") for index in range(5)]
        deadline = time.monotonic() + 2
        while self.scheduler.queued_count() < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(5, len(agents))
        self.assertGreaterEqual(self.scheduler.queued_count(), 1)
        release.set()

    def test_same_name_isolated_and_adopted_across_sessions(self):
        first = self.service.spawn("reviewer", self.workspace, "会话 A", "session-a")
        second = self.service.spawn("reviewer", self.workspace, "会话 B", "session-b")
        self.service.wait([first.id, second.id], timeout_seconds=2)

        self.assertEqual(first.id, self.service.status("reviewer", self.workspace, "session-a").id)
        self.assertEqual(second.id, self.service.status("reviewer", self.workspace, "session-b").id)
        self.assertEqual(1, len(self.service.list_agents(self.workspace, owner_session_id="session-a")))

        adopted = self.service.adopt(first.id, "session-c")
        self.assertEqual("session-c", adopted.owner_session_id)
        with self.assertRaises(KeyError):
            self.service.status("reviewer", self.workspace, "session-a")
        self.service.send("reviewer", "接管后续消息", self.workspace, "session-c")
        self.service.wait([first.id], timeout_seconds=2)
        self.assertEqual("接管后续消息", self.service.result(first.id).last_result)


if __name__ == "__main__":
    unittest.main()
