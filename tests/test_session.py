import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.session import resolve_session_id, validate_session_id


class SessionTests(unittest.TestCase):
    def test_explicit_session_has_priority_over_codex_thread_id(self):
        self.assertEqual("manual", resolve_session_id("manual", {"CODEX_THREAD_ID": "desktop"}))

    def test_codex_thread_id_is_used_before_standalone_fallback(self):
        self.assertEqual("desktop", resolve_session_id(None, {"CODEX_THREAD_ID": "desktop"}))
        self.assertEqual("standalone", resolve_session_id(None, {}))

    def test_empty_or_overlong_session_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_session_id(" ")
        with self.assertRaises(ValueError):
            validate_session_id("x" * 129)


if __name__ == "__main__":
    unittest.main()
