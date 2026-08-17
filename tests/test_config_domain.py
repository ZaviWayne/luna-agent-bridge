import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.config import Settings
from luna_agent_bridge.domain import AgentState, can_transition
from luna_agent_bridge.paths import AppPaths


class DomainTests(unittest.TestCase):
    def test_default_settings_are_luna_max_with_four_workers(self):
        settings = Settings.defaults()
        self.assertEqual("gpt-5.6-luna", settings.model)
        self.assertEqual("max", settings.reasoning_effort)
        self.assertEqual(4, settings.max_workers)
        self.assertEqual("workspace-write", settings.sandbox)
        self.assertTrue(settings.approve_for_me)

    def test_running_can_become_idle_or_recoverable_only(self):
        self.assertTrue(can_transition(AgentState.RUNNING, AgentState.IDLE))
        self.assertTrue(can_transition(AgentState.RUNNING, AgentState.RECOVERABLE))
        self.assertFalse(can_transition(AgentState.RUNNING, AgentState.ARCHIVED))

    def test_settings_reject_non_luna_values(self):
        with self.assertRaises(Exception):
            Settings(model="gpt-5.6-sol").validate()

    def test_paths_are_user_rooted_and_injectable(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = AppPaths.for_user(Path(directory) / "CodexLunaAgent")
            self.assertEqual(paths.root, Path(directory).joinpath("CodexLunaAgent").resolve())
            self.assertEqual(paths.database, paths.root / "data" / "agents.db")

    def test_pipe_name_isolated_by_effective_windows_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "CodexLunaAgent"
            with patch("luna_agent_bridge.paths._effective_identity_suffix", return_value="sid-1001"):
                first = AppPaths.for_user(root)
            with patch("luna_agent_bridge.paths._effective_identity_suffix", return_value="sid-1003"):
                second = AppPaths.for_user(root)
            self.assertNotEqual(first.pipe_name, second.pipe_name)
            self.assertIn("sid-1001", first.pipe_name)


if __name__ == "__main__":
    unittest.main()
