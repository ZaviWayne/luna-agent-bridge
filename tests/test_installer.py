import os
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import luna_agent_bridge.installer as installer_module
from luna_agent_bridge.installer import BEGIN_MARKER, SHELL_PATH_BEGIN, Installer
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
        self.paths = AppPaths.for_user(self.root, platform_name="windows")
        self.source_exe = Path(self.directory.name) / "source.exe"
        self.source_exe.write_bytes(b"bridge")
        self.path_store = FakePathStore()
        self.installer = Installer(
            self.paths,
            home=self.home,
            path_store=self.path_store,
            acl_runner=lambda path: None,
            platform_name="windows",
        )

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
        self.assertFalse((self.paths.bin_dir / self.paths.executable_name).exists())

    def test_macos_install_is_executable_and_updates_zprofile_once(self):
        paths = AppPaths.for_user(self.root / "mac", platform_name="macos")
        installer = Installer(
            paths,
            home=self.home,
            acl_runner=lambda path: path.chmod(0o700),
            platform_name="macos",
        )
        installer.install(self.source_exe)
        installer.install(self.source_exe)
        target = paths.bin_dir / "luna-agent"
        profile = self.home / ".zprofile"
        self.assertTrue(target.is_file())
        if os.name != "nt":
            self.assertEqual(0o700, target.stat().st_mode & 0o777)
        self.assertEqual(1, profile.read_text(encoding="utf-8").count(SHELL_PATH_BEGIN))
        self.assertIn(str(paths.bin_dir), profile.read_text(encoding="utf-8"))
        installer.uninstall()
        self.assertFalse(target.exists())
        self.assertFalse(profile.exists())

    def test_atomic_write_closes_temporary_file_before_replace(self):
        target = self.home / "config.toml"
        handles = []
        original_named_temporary_file = installer_module.tempfile.NamedTemporaryFile
        original_replace = installer_module.os.replace

        def track_handle(*args, **kwargs):
            handle = original_named_temporary_file(*args, **kwargs)
            handles.append(handle)
            return handle

        def assert_closed_then_replace(source, destination):
            self.assertTrue(handles[-1].closed)
            original_replace(source, destination)

        with patch.object(installer_module.tempfile, "NamedTemporaryFile", side_effect=track_handle):
            with patch.object(installer_module.os, "replace", side_effect=assert_closed_then_replace):
                installer_module._write_atomic(target, "enabled = true\n")

        self.assertEqual("enabled = true\n", target.read_text(encoding="utf-8"))

    def test_atomic_write_removes_temporary_file_when_replace_fails(self):
        target = self.home / "config.toml"

        with patch.object(installer_module.os, "replace", side_effect=PermissionError("占用")):
            with self.assertRaises(PermissionError):
                installer_module._write_atomic(target, "enabled = true\n")

        self.assertEqual([], list(self.home.iterdir()))


if __name__ == "__main__":
    unittest.main()
