import json
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseLayoutTests(unittest.TestCase):
    def test_native_skill_is_self_contained_and_native_only(self):
        skill_path = PROJECT_ROOT / "packages" / "native-luna-subagents" / "SKILL.md"
        metadata_path = PROJECT_ROOT / "packages" / "native-luna-subagents" / "agents" / "openai.yaml"
        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertTrue(skill_path.is_file())
        self.assertTrue(metadata_path.is_file())
        self.assertIn("name: native-luna-subagents", skill_text)
        self.assertIn("Do not invoke the external `luna-agent` CLI", skill_text)
        self.assertIn("does not guarantee cross-session recovery", skill_text)
        self.assertNotIn("luna-agent spawn", skill_text)

    def test_bridge_plugin_is_explicitly_optional(self):
        manifest_path = PROJECT_ROOT / "plugins" / "luna-agent-bridge" / ".codex-plugin" / "plugin.json"
        skill_path = PROJECT_ROOT / "plugins" / "luna-agent-bridge" / "skills" / "luna-agent-bridge" / "SKILL.md"
        metadata_path = PROJECT_ROOT / "plugins" / "luna-agent-bridge" / "skills" / "luna-agent-bridge" / "agents" / "openai.yaml"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skill_text = skill_path.read_text(encoding="utf-8")
        metadata_text = metadata_path.read_text(encoding="utf-8")

        self.assertEqual("luna-agent-bridge", manifest["name"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertIn("non-official", manifest["interface"]["longDescription"])
        self.assertIn("explicitly requests", skill_text)
        self.assertIn("optional compatibility layer", skill_text)
        self.assertIn("do not assume Codex closing will reclaim the external broker", skill_text)
        self.assertIn("allow_implicit_invocation: false", metadata_text)

    def test_open_source_governance_files_exist(self):
        for filename in ("LICENSE", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md"):
            with self.subTest(filename=filename):
                self.assertTrue((PROJECT_ROOT / filename).is_file())

    def test_legacy_assets_are_marked_deprecated(self):
        skill_text = (PROJECT_ROOT / "assets" / "SKILL.md").read_text(encoding="utf-8")
        agents_text = (PROJECT_ROOT / "assets" / "AGENTS.block.md").read_text(encoding="utf-8")

        self.assertIn("已弃用", skill_text)
        self.assertIn("已弃用", agents_text)
        self.assertIn("packages/native-luna-subagents", skill_text)
        self.assertIn("不要将本文件复制为全局 AGENTS.md", agents_text)

    def test_public_release_files_do_not_embed_machine_paths_or_patch_markers(self):
        public_files = (
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "luna-agent.spec",
        )
        forbidden_fragments = (
            "C:" + "\\Users\\",
            "C:" + "/Users/",
            "D:" + "\\software\\" + "luna-agent-bridge",
            "D:" + "/software/" + "luna-agent-bridge",
            "*** " + "Delete File:",
            "*** " + "Add File:",
        )

        for path in public_files:
            content = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                with self.subTest(path=path, fragment=fragment):
                    self.assertNotIn(fragment, content)

    def test_public_docs_explain_model_routing_motivation(self):
        readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("模型路由", readme_text)
        self.assertIn("gpt-5.6-luna", readme_text)
        self.assertIn("max", readme_text)
        self.assertIn("成本", readme_text)
        self.assertIn("cross-session", pyproject_text)
        self.assertIn("gpt-5.6-luna", pyproject_text)

    def test_bridge_setup_documents_virtual_environment_command_resolution(self):
        readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(r".\.venv\Scripts\Activate.ps1", readme_text)
        self.assertIn('python -m pip install -e ".[dev]"', readme_text)
        self.assertIn(r".\.venv\Scripts\luna-agent.exe", readme_text)


if __name__ == "__main__":
    unittest.main()

