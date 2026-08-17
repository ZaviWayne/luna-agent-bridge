import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.codex_adapter import CodexCommandFactory, CodexEventParser, CodexProtocolError
from luna_agent_bridge.config import Settings


class CodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.executable = Path(r"C:\Codex\codex.exe")
        self.factory = CodexCommandFactory(self.executable, Settings.defaults())

    def test_spawn_command_pins_luna_max_and_safe_sandbox(self):
        invocation = self.factory.spawn(Path("workspace-fixture"), "检查修改")
        self.assertIn("gpt-5.6-luna", invocation.argv)
        self.assertIn('model_reasoning_effort="max"', invocation.argv)
        self.assertIn("--approve-for-me", invocation.argv)
        self.assertNotIn("--sandbox", invocation.argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", invocation.argv)
        self.assertEqual(Path("workspace-fixture").resolve(), invocation.cwd)

    def test_resume_command_uses_saved_thread_id(self):
        invocation = self.factory.resume("thread-1", "继续检查")
        self.assertEqual("thread-1", invocation.argv[-2])
        self.assertEqual("继续检查", invocation.argv[-1])
        self.assertIn("gpt-5.6-luna", invocation.argv)
        self.assertIn('model_reasoning_effort="max"', invocation.argv)

    def test_parser_extracts_thread_final_text_and_usage(self):
        fixture = Path(__file__).parent / "fixtures" / "codex_success.jsonl"
        parser = CodexEventParser()
        for line in fixture.read_text(encoding="utf-8").splitlines():
            parser.feed(line)
        result = parser.result(0)
        self.assertEqual("019ffa26-defc-7ac1-9980-4f7f0ec6536c", result.thread_id)
        self.assertEqual("OK", result.final_text)
        self.assertEqual(5, result.usage["output_tokens"])

    def test_parser_keeps_unknown_events_and_ignores_malformed_lines(self):
        parser = CodexEventParser()
        parser.feed("not-json")
        parser.feed(json.dumps({"type": "thread.started", "thread_id": "thread-2"}))
        parser.feed(json.dumps({"type": "custom.event", "payload": 1}))
        parser.feed(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "完成"}}))
        result = parser.result(0)
        self.assertEqual("完成", result.final_text)
        self.assertEqual(2, len(result.events))

    def test_success_without_thread_id_is_rejected(self):
        parser = CodexEventParser()
        parser.feed(json.dumps({"type": "turn.completed", "usage": {}}))
        with self.assertRaises(CodexProtocolError):
            parser.result(0)


if __name__ == "__main__":
    unittest.main()
