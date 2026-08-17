# Open-Source Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a native Codex Luna subagent Skill and an explicitly optional external bridge plugin without confusing the two capabilities.

**Architecture:** Keep the native Skill stateless and native-only under `packages/native-luna-subagents`. Keep the Windows CLI/Broker under the existing Python project and expose it only through `plugins/luna-agent-bridge`, with explicit opt-in and lifecycle warnings.

**Tech Stack:** Codex Skill metadata, Codex plugin manifest, Python 3.12, setuptools, unittest, PyYAML validation tooling.

## Global Constraints

- Native Skill must not start a broker, modify PATH, store credentials, bypass the sandbox, or promise cross-session persistence.
- External bridge remains Windows-only and unofficial; it must be explicitly selected by the user.
- Maximum native subagent concurrency remains 4 per session.
- Runtime dependencies remain empty; `PyYAML>=6.0` is a development-only extra for manifest validation.
- Do not commit generated `.venv`, build, dist, outputs, caches, or logs.

---

### Task 1: Record the package boundary

**Files:**
- Create: `docs/superpowers/specs/2026-08-14-open-source-packaging-design.md`

- [x] Define native Skill, optional bridge plugin, security boundaries, and acceptance criteria.
- [x] Self-review for conflicting claims about native persistence and external lifecycle.

### Task 2: Create the native Skill

**Files:**
- Create: `packages/native-luna-subagents/SKILL.md`
- Create: `packages/native-luna-subagents/agents/openai.yaml`

- [x] Generate the Skill with the standard initializer.
- [x] Add bounded decomposition, ownership, messaging, lifecycle, and verification rules.
- [x] Enable implicit invocation for native work and keep the Skill ASCII-valid on Windows.

### Task 3: Create the optional bridge plugin

**Files:**
- Create: `plugins/luna-agent-bridge/.codex-plugin/plugin.json`
- Create: `plugins/luna-agent-bridge/skills/luna-agent-bridge/SKILL.md`
- Create: `plugins/luna-agent-bridge/skills/luna-agent-bridge/agents/openai.yaml`

- [x] Generate and validate the plugin manifest.
- [x] Mark the bridge non-official, Windows-only, and opt-in.
- [x] Disable implicit invocation for the bridge Skill.

### Task 4: Prepare open-source governance and release metadata

**Files:**
- Create: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.gitignore`, `MANIFEST.in`
- Modify: `README.md`, `pyproject.toml`
- Modify: `assets/SKILL.md`, `assets/AGENTS.block.md`

- [x] Document the two release paths, lifecycle shutdown, security boundaries, and development commands.
- [x] Preserve legacy installer markers while clearly deprecating the old global bridge instructions.
- [x] Add MIT licensing and a development-only PyYAML extra.

### Task 5: Verify the release layout

**Files:**
- Create: `tests/test_release_layout.py`

- [x] Add tests for Skill boundaries, optional plugin metadata, governance files, and legacy warnings.
- [x] Run the official Skill validators for both Skills.
- [x] Run the official plugin validator.
- [x] Run `python -m unittest discover -s tests -q` and verify all tests pass.
