import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.installer import Installer, BEGIN_MARKER
from luna_agent_bridge.paths import AppPaths


class FakePathStore:
    def __init__(self):
        self.value = r"C:\Windows\System32"

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "app"
        self.home = Path(self.directory.name) / "home"
        self.home.mkdir()
        self.paths = AppPaths.for_user(self.root)
        self.source_exe = Path(self.directory.name) / "source.exe"
        self.source_exe.write_bytes(b"bridge")
        self.path_store = FakePathStore()
        self.installer = Installer(self.paths, home=self.home, path_store=self.path_store, acl_runner=lambda path: None)

    def tearDown(self):
        self.directory.cleanup()

    def test_install_twice_does_not_duplicate_path_or_agents_block(self):
        self.installer.install(self.source_exe)
        self.installer.install(self.source_exe)
        self.assertEqual(1, self.path_store.get().split(";").count(str(self.paths.bin_dir)))
        agents_file = self.home / "AGENTS.md"
        self.assertEqual(1, agents_file.read_text("utf-8").count(BEGIN_MARKER))

    def test_install_preserves_existing_agents_content(self):
        agents_file = self.home / "AGENTS.md"
        agents_file.write_text("# Existing\n\n规则\n", encoding="utf-8")
        self.installer.install(self.source_exe)
        content = agents_file.read_text("utf-8")
        self.assertIn("# Existing", content)
        self.assertIn("规则", content)
        self.assertIn(BEGIN_MARKER, content)

    def test_install_writes_session_isolation_and_handoff_guidance(self):
        self.installer.install(self.source_exe)
        skill = (self.home / ".codex" / "skills" / "luna-agent-bridge" / "SKILL.md").read_text("utf-8")
        agents = (self.home / "AGENTS.md").read_text("utf-8")
        self.assertIn("CODEX_THREAD_ID", skill)
        self.assertIn("--all-sessions", skill)
        self.assertIn("adopt", skill)
        self.assertIn("Agent ID", agents)

    def test_uninstall_preserves_data_without_purge(self):
        self.installer.install(self.source_exe)
        self.paths.database.parent.mkdir(parents=True, exist_ok=True)
        self.paths.database.write_bytes(b"db")
        self.installer.uninstall(purge_data=False)
        self.assertTrue(self.paths.database.exists())
        self.assertFalse((self.paths.bin_dir / "luna-agent.exe").exists())


if __name__ == "__main__":
    unittest.main()
