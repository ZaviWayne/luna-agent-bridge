import json
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseLayoutTests(unittest.TestCase):
    def test_native_skill_is_self_contained_and_native_only(self):
        skill_path = PROJECT_ROOT / "packages" / "native-luna-subagents" / "SKILL.md"
        metadata_path = PROJECT_ROOT / "packages" / "native-luna-subagents" / "agents" / "openai.yaml"
        skill_text = skill_path.read_text(encoding="utf-8")
        metadata_text = metadata_path.read_text(encoding="utf-8")

        self.assertTrue(skill_path.is_file())
        self.assertTrue(metadata_path.is_file())
        self.assertIn("name: native-luna-subagents", skill_text)
        self.assertIn("Do not invoke the external `luna-agent` CLI", skill_text)
        self.assertIn("does not guarantee cross-session recovery", skill_text)
        self.assertNotIn("luna-agent spawn", skill_text)
        self.assertIn("allow_implicit_invocation: true", metadata_text)
        self.assertIn("keep the external bridge opt-in", metadata_text)

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
        self.assertIn("macOS", manifest["interface"]["longDescription"])
        self.assertIn("explicitly requests", skill_text)
        self.assertIn("optional compatibility layer", skill_text)
        self.assertIn("do not assume Codex closing will reclaim the external broker", skill_text)
        self.assertIn("allow_implicit_invocation: false", metadata_text)

    def test_open_source_governance_files_exist(self):
        for filename in (
            "LICENSE",
            "CONTRIBUTING.md",
            "CONTRIBUTING_CN.md",
            "SECURITY.md",
            "SECURITY_CN.md",
            "CODE_OF_CONDUCT.md",
            "CODE_OF_CONDUCT_CN.md",
        ):
            with self.subTest(filename=filename):
                self.assertTrue((PROJECT_ROOT / filename).is_file())

    def test_governance_language_navigation_and_packaging(self):
        manifest_text = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        document_pairs = (
            ("CONTRIBUTING.md", "CONTRIBUTING_CN.md"),
            ("SECURITY.md", "SECURITY_CN.md"),
            ("CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT_CN.md"),
        )

        for english_name, chinese_name in document_pairs:
            english_text = (PROJECT_ROOT / english_name).read_text(encoding="utf-8")
            chinese_text = (PROJECT_ROOT / chinese_name).read_text(encoding="utf-8")
            with self.subTest(document=english_name):
                self.assertIn(f"[中文]({chinese_name})", english_text)
                self.assertIn(f"[English]({english_name})", chinese_text)
                self.assertIn(f"include {chinese_name}", manifest_text)

        self.assertFalse((PROJECT_ROOT / "docs").exists())
        self.assertNotIn("recursive-include docs", manifest_text)

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
            PROJECT_ROOT / "README_CN.md",
            PROJECT_ROOT / "CONTRIBUTING.md",
            PROJECT_ROOT / "CONTRIBUTING_CN.md",
            PROJECT_ROOT / "SECURITY.md",
            PROJECT_ROOT / "SECURITY_CN.md",
            PROJECT_ROOT / "CODE_OF_CONDUCT.md",
            PROJECT_ROOT / "CODE_OF_CONDUCT_CN.md",
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
        chinese_readme_text = (PROJECT_ROOT / "README_CN.md").read_text(encoding="utf-8")
        pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("model routing", readme_text)
        self.assertIn("gpt-5.6-luna", readme_text)
        self.assertIn("max", readme_text)
        self.assertIn("cost", readme_text)
        self.assertIn("模型路由", chinese_readme_text)
        self.assertIn("成本", chinese_readme_text)
        self.assertIn("Native-first", pyproject_text)
        self.assertIn("optional cross-session bridge", pyproject_text)
        self.assertIn("is not, by itself, a reason to install the bridge", readme_text)
        self.assertIn("routine subtasks that need delegation use Codex native subagents by default", readme_text)
        self.assertIn("指定 `gpt-5.6-luna` + `max` 本身不是安装 Bridge 的理由", chinese_readme_text)
        self.assertIn("后续需要拆分的普通子任务默认使用 Codex 原生子 Agent", chinese_readme_text)
        self.assertLess(
            readme_text.index("## Recommended: Native Skill"),
            readme_text.index("## Optional: External Bridge"),
        )

    def test_readme_language_navigation_and_packaging(self):
        readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        chinese_readme_text = (PROJECT_ROOT / "README_CN.md").read_text(encoding="utf-8")
        manifest_text = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

        self.assertIn("English | [中文](README_CN.md)", readme_text)
        self.assertIn("[English](README.md) | 中文", chinese_readme_text)
        self.assertIn("include README_CN.md", manifest_text)

    def test_bridge_setup_documents_virtual_environment_command_resolution(self):
        readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(r".\.venv\Scripts\Activate.ps1", readme_text)
        self.assertIn('python -m pip install -e ".[dev]"', readme_text)
        self.assertIn(r".\.venv\Scripts\luna-agent.exe", readme_text)
        self.assertIn("luna-agent-macos-arm64", readme_text)
        self.assertIn("source .venv/bin/activate", readme_text)

    def test_github_ci_and_feedback_entrypoints_exist(self):
        workflow_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        bug_report_path = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md"
        feature_request_path = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md"
        issue_config_path = PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml"

        for path in (workflow_path, bug_report_path, feature_request_path, issue_config_path):
            with self.subTest(path=path):
                self.assertTrue(path.is_file())

        workflow_text = workflow_path.read_text(encoding="utf-8")
        bug_report_text = bug_report_path.read_text(encoding="utf-8")
        feature_request_text = feature_request_path.read_text(encoding="utf-8")
        issue_config_text = issue_config_path.read_text(encoding="utf-8")

        self.assertIn("windows-latest", workflow_text)
        self.assertIn("macos-14", workflow_text)
        self.assertIn('python-version: "3.12"', workflow_text)
        self.assertIn("python -m unittest discover -s tests -q", workflow_text)
        self.assertIn("## 环境信息", bug_report_text)
        self.assertIn("## 复现步骤", bug_report_text)
        self.assertIn("## 背景与问题", feature_request_text)
        self.assertIn("blank_issues_enabled: true", issue_config_text)

    def test_release_packaging_contract_exists(self):
        script_path = PROJECT_ROOT / "scripts" / "package-release.ps1"
        self.assertTrue(script_path.is_file())
        script_text = script_path.read_text(encoding="utf-8")

        for marker in (
            "param(",
            "python -m unittest discover -s tests -q",
            "python -m build",
            "python -m twine check",
            "SHA256SUMS.txt",
            "luna-agent.exe",
            "luna_agent_bridge-",
            "luna-agent-bridge-plugin-",
            "luna-agent-bridge-skill-",
            "native-luna-subagents-skill-",
            "quick_validate.py",
            "$skillDir",
            "$nativeSkillDir",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, script_text)

        macos_script = (PROJECT_ROOT / "scripts" / "package-macos.sh").read_text(encoding="utf-8")
        for marker in (
            "-m unittest",
            "PyInstaller",
            "luna-agent-macos-",
            "arm64",
            "x86_64",
            "expected_architecture",
            "broker serve",
            "broker_pid",
            "pipe_name",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, macos_script)

    def test_release_workflow_contract_exists(self):
        workflow_path = PROJECT_ROOT / ".github" / "workflows" / "release.yml"
        self.assertTrue(workflow_path.is_file())
        workflow_text = workflow_path.read_text(encoding="utf-8")

        for marker in (
            'v*.*.*',
            "windows-latest",
            "macos-14",
            "macos-15-intel",
            'python-version: "3.12"',
            "package-release.ps1",
            "package-macos.sh",
            "actions/upload-artifact@v4",
            "actions/download-artifact@v4",
            "pypa/gh-action-pypi-publish@release/v1",
            "id-token: write",
            "contents: write",
            "gh release create",
            "gh release edit",
            "luna-agent-macos-",
            "luna-agent-macos-arm64",
            "luna-agent-macos-x86_64",
            "-eq 2",
            "pattern: release-macos-*",
            "merge-multiple: true",
            "native-luna-subagents-skill-",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, workflow_text)

if __name__ == "__main__":
    unittest.main()
