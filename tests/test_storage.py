import tempfile
import threading
import unittest
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.config import Settings
from luna_agent_bridge.domain import AgentState, MessageStatus
from luna_agent_bridge.storage import Storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.storage = Storage.open(Path(self.directory.name) / "agents.db")
        self.workspace = Path(self.directory.name) / "project"
        self.workspace.mkdir()
        self.agent = self.storage.create_agent("reviewer", self.workspace, Settings.defaults(), "default")

    def tearDown(self):
        self.storage.close()
        self.directory.cleanup()

    def test_claim_next_message_is_fifo_and_exactly_once(self):
        first = self.storage.enqueue_message(self.agent.id, "一")
        second = self.storage.enqueue_message(self.agent.id, "二")
        self.assertEqual(first.id, self.storage.claim_next_message(self.agent.id).id)
        self.assertEqual(second.id, self.storage.claim_next_message(self.agent.id).id)
        self.assertIsNone(self.storage.claim_next_message(self.agent.id))

    def test_claimed_message_can_be_marked_delivered(self):
        message = self.storage.enqueue_message(self.agent.id, "检查")
        claimed = self.storage.claim_next_message(self.agent.id)
        self.assertEqual(MessageStatus.DELIVERING, claimed.status)
        self.storage.mark_message_delivered(claimed.id, "turn-1")
        self.assertEqual(MessageStatus.DELIVERED, self.storage.get_message(message.id).status)

    def test_startup_marks_running_agent_recoverable(self):
        self.storage.force_state_for_test(self.agent.id, AgentState.RUNNING)
        turn = self.storage.create_turn(self.agent.id, self.storage.enqueue_message(self.agent.id, "运行" ).id)
        count = self.storage.recover_incomplete_agents()
        self.assertEqual(1, count)
        self.assertEqual(AgentState.RECOVERABLE, self.storage.get_agent(self.agent.id).state)
        self.assertEqual("Broker 异常退出，任务可恢复", self.storage.get_turn(turn.id).error)

    def test_concurrent_writers_preserve_unique_sequences(self):
        errors = []

        def write_batch():
            try:
                for index in range(25):
                    self.storage.enqueue_message(self.agent.id, f"消息-{threading.get_ident()}-{index}")
            except Exception as error:  # pragma: no cover - assertion below reports the failure
                errors.append(error)

        threads = [threading.Thread(target=write_batch) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([], errors)
        messages = self.storage.list_messages(self.agent.id)
        self.assertEqual(200, len(messages))
        self.assertEqual(list(range(1, 201)), [message.sequence for message in messages])

    def test_same_name_is_allowed_for_different_sessions(self):
        first = self.storage.create_agent("reviewer", self.workspace, Settings.defaults(), "session-a")
        second = self.storage.create_agent("reviewer", self.workspace, Settings.defaults(), "session-b")
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.id, self.storage.resolve_agent("reviewer", self.workspace, "session-a").id)
        self.assertEqual(second.id, self.storage.resolve_agent("reviewer", self.workspace, "session-b").id)

    def test_same_name_remains_unique_within_one_session(self):
        with self.assertRaises(ValueError):
            self.storage.create_agent("reviewer", self.workspace, Settings.defaults(), "default")

    def test_adopt_moves_agent_to_target_session(self):
        agent = self.storage.create_agent("adopt-me", self.workspace, Settings.defaults(), "old")
        adopted = self.storage.adopt_agent(agent.id, "new")
        self.assertEqual("new", adopted.owner_session_id)
        self.assertEqual(agent.id, self.storage.resolve_agent("adopt-me", self.workspace, "new").id)

    def test_v1_database_migrates_existing_agents_to_legacy(self):
        database_path = Path(self.directory.name) / "legacy.db"
        connection = sqlite3.connect(database_path)
        connection.executescript(
            """
            CREATE TABLE schema_version (version INTEGER NOT NULL);
            INSERT INTO schema_version(version) VALUES (1);
            CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                workspace TEXT NOT NULL,
                state TEXT NOT NULL,
                model TEXT NOT NULL,
                reasoning_effort TEXT NOT NULL,
                sandbox TEXT NOT NULL,
                approve_for_me INTEGER NOT NULL,
                codex_thread_id TEXT,
                last_result TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                turn_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                delivered_at TEXT
            );
            CREATE TABLE turns (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                state TEXT NOT NULL,
                codex_thread_id TEXT,
                exit_code INTEGER,
                result TEXT,
                error TEXT,
                usage_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                turn_id TEXT,
                event_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE broker_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        connection.execute(
            """
            INSERT INTO agents(
                id, name, workspace, state, model, reasoning_effort, sandbox,
                approve_for_me, codex_thread_id, last_result, last_error, created_at, updated_at
            ) VALUES ('legacy-agent', 'reviewer', ?, 'idle', 'gpt-5.6-luna', 'max', 'workspace-write', 1, 'thread-1', '结果', NULL, 'now', 'now')
            """,
            (str(self.workspace),),
        )
        connection.commit()
        connection.close()

        migrated = Storage.open(database_path)
        try:
            agent = migrated.get_agent("legacy-agent")
            self.assertEqual("legacy", agent.owner_session_id)
            self.assertEqual("thread-1", agent.codex_thread_id)
        finally:
            migrated.close()


if __name__ == "__main__":
    unittest.main()
