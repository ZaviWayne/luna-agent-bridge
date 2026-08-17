# README 项目定位重写 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写公开 README 和 Python 项目描述，让用户先理解将适合的 Codex 子 Agent 任务路由到 `gpt-5.6-luna` 的成本/质量动机，再理解可选的跨会话 Bridge 能力。

**Architecture:** 只修改公开文案和元数据，不改变运行时代码。README 使用“动机场景 → 路径决策表 → 快速开始 → 能力边界”的顺序；`pyproject.toml` 使用一句可被包索引直接展示的精确描述。内部设计/计划文档保留在本地，不进入 GitHub 提交。

**Tech Stack:** Markdown、TOML、Python `unittest`、现有 Skill/Plugin 校验脚本、GitHub Contents/Git Tree API。

## Global Constraints

- `gpt-5.6-luna` 是模型，`max` 是推理强度；文案不得将二者描述成一个独立模型。
- 不承诺固定成本节省、模型可用性、侧边栏显示或跨会话恢复；这些取决于任务、账号和运行环境。
- 保留“原生 Skill 优先、外部 Bridge 可选”的安全边界。
- 不上传 `docs/superpowers/`、`.venv/`、`build/`、`dist/`、`outputs/` 或日志。
- 公开文件不得包含本机绝对路径。

---

### Task 1: Add documentation regression coverage

**Files:**
- Modify: `tests/test_release_layout.py`

**Interfaces:**
- Consumes: `README.md` and `pyproject.toml` UTF-8 text.
- Produces: a regression test proving the public explanation names model routing, Luna, reasoning effort, and the cost/quality caveat.

- [ ] **Step 1: Add the failing assertions**

Add a test method named `test_public_docs_explain_model_routing_motivation` that reads `README.md` and `pyproject.toml` with `encoding="utf-8"` and asserts:

```python
self.assertIn("模型路由", readme_text)
self.assertIn("gpt-5.6-luna", readme_text)
self.assertIn("max", readme_text)
self.assertIn("成本", readme_text)
self.assertIn("cross-session", pyproject_text)
self.assertIn("gpt-5.6-luna", pyproject_text)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_release_layout.ReleaseLayoutTests.test_public_docs_explain_model_routing_motivation -v
```

Expected: `FAIL` because the current README does not yet contain the model-routing motivation and the current `pyproject.toml` description does not contain `gpt-5.6-luna`.

### Task 2: Rewrite the public README around the motivation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the approved positioning in `docs/superpowers/specs/2026-08-14-readme-positioning-design.md`.
- Produces: a self-contained public explanation and two installation paths.

- [ ] **Step 1: Replace the opening with a direct value proposition**

Use this opening immediately below the title:

```markdown
让 Codex 用户把适合的子 Agent 任务路由到 `gpt-5.6-luna`，在主 Agent 保持高能力的同时，为高频、边界清晰的任务提供更可控的成本/质量选择；需要时再启用本地队列和跨会话恢复。
```

- [ ] **Step 2: Add a concrete motivation scenario**

Explain that a main Agent may use a high-capability model while decomposed review, test, search, and file organization tasks do not always need the same model. State that Luna is a cost-sensitive/high-volume option, while `max` is reasoning effort and its cost/quality trade-off must be measured.

- [ ] **Step 3: Add the native-versus-bridge decision table**

Include these rows:

| 需求 | 推荐路径 |
| --- | --- |
| 普通拆解、审查、测试、资料整理 | Codex 原生子 Agent + `native-luna-subagents` Skill |
| 需要显式指定子任务模型/推理强度 | 本项目的外部 Bridge，在运行环境允许时路由到 `gpt-5.6-luna` |
| 需要关闭 Codex 后保留、恢复或接管任务 | 外部 Bridge；这是增强能力，不是原生 Codex 保证 |

- [ ] **Step 4: Add capability and non-guarantee sections**

List the Bridge capabilities (local SQLite state, Named Pipe transport, queueing, session isolation, explicit recovery) and explicitly state that model availability, sidebar display, lifecycle, and exact cost savings remain runtime/account dependent.

- [ ] **Step 5: Preserve practical installation and safety content**

Keep the existing PowerShell setup, CLI examples, shutdown guidance, security boundary, tests, and MIT license sections after the new explanation. Replace any wording that presents the Bridge as an official native Luna implementation.

### Task 3: Synchronize package metadata

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: the README value proposition.
- Produces: a package-index description that names the model-routing purpose.

- [ ] **Step 1: Update the description field**

Replace:

```toml
description = "Persistent local bridge for Codex Luna sub-agents"
```

with:

```toml
description = "Cost-conscious local bridge for routing Codex sub-agent tasks to GPT-5.6 Luna with optional cross-session persistence"
```

- [ ] **Step 2: Run the focused regression test and verify it passes**

Run the focused test from Task 1 and expect `OK`.

### Task 4: Validate public documentation

**Files:**
- Read: `README.md`
- Read: `pyproject.toml`
- Read: `tests/test_release_layout.py`

**Interfaces:**
- Consumes: updated public docs and metadata.
- Produces: evidence that the explanation is UTF-8, portable, and compatible with existing release checks.

- [ ] **Step 1: Run the full test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run public path and patch-marker scans**

Run a recursive scan excluding generated directories for user-home paths, absolute workspace paths, generic drive-letter examples, and patch markers such as `*** Delete File:` and `*** Add File:`. Expected: no matches.

- [ ] **Step 3: Run official Skill and Plugin validators**

Run the existing `quick_validate.py` checks for both Skill directories and `validate_plugin.py` for the plugin. Expected: all validators report success.

### Task 5: Publish one documentation commit to master

**Files:**
- Upload: `README.md`, `pyproject.toml`, `tests/test_release_layout.py`
- Exclude: `docs/superpowers/`, `.venv/`, `build/`, `dist/`, `outputs/`, and logs

**Interfaces:**
- Consumes: the validated local file contents and the current `master` tree SHA.
- Produces: one GitHub commit with a clear public documentation summary.

- [ ] **Step 1: Create a tree from the current master tree**

Create blobs for only the three intended files and build a tree using the current master tree as `base_tree_sha`; do not include internal plans or generated artifacts.

- [ ] **Step 2: Create the commit with a summary**

Use:

```text
docs: clarify Luna routing motivation and project boundaries

Explain why cost-conscious users may route suitable Codex sub-agent tasks to GPT-5.6 Luna, distinguish model from reasoning effort, and document when the optional persistent bridge is appropriate.
```

- [ ] **Step 3: Move `master` to the new commit and verify**

Update `master`, then fetch the branch tree and confirm the three files changed while `docs/superpowers/` and generated directories remain absent.
