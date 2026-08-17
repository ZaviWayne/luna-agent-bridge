# Native Luna 子 Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 将用户级 Codex 默认子 Agent 切换为原生 gpt-5.6-luna、max，让线程由桌面端原生界面管理，并停止旧外部 Broker 的默认路径。

**Architecture:** 只修改用户级 Codex 配置和 Agent manifest，不再创建 Broker 到桌面端的镜像层。旧桥接执行无数据清除卸载，停止其可执行文件、技能和默认规则，保留 SQLite 数据库和备份以便回滚；原生子 Agent 的线程、通信、等待和生命周期全部由 Codex 编排。

**Tech Stack:** Codex config.toml, Codex custom-agent TOML, user-level AGENTS.md, existing luna-agent installer, Python tomllib verification.

## Global Constraints

- 默认模型必须为 gpt-5.6-luna。
- 默认推理强度必须为 max。
- 最大并行原生子 Agent 为 4 个。
- 工作区权限保持 workspace-write，继承项目级 AGENTS.md。
- Codex 完全退出后不得有外部 Luna Broker 继续执行。
- 旧桥接卸载不得删除 SQLite 历史数据。
- 不修改或覆盖用户现有 Codex 配置、MCP、插件和项目可信设置。
- 不主动提交代码或配置变更。

---

### Task 1: 停止并无数据清除卸载旧桥接

**Files:**
- Modify: <USER_HOME>/AGENTS.md via the existing installer block removal
- Remove: <BRIDGE_DATA_ROOT>/bin/luna-agent.exe
- Remove: <CODEX_HOME>/skills/luna-agent-bridge/SKILL.md
- Preserve: <BRIDGE_DATA_ROOT>/data/agents.db
- Preserve: <BRIDGE_DATA_ROOT>/backups/

**Interfaces:**
- Consumes: Installed luna-agent.exe uninstall command.
- Produces: No old executable, skill, PATH entry, or Luna bridge instruction block; data directory remains.

- [ ] Step 1: Verify old Broker and Agent state.

Run:

~~~
Get-Process | Where-Object { $_.ProcessName -match 'luna-agent|codex' } | Select-Object Id,ProcessName,Path
luna-agent list --all-sessions --include-archived --json
~~~

Expected: record any active old Agent IDs; do not purge the database.

- [ ] Step 2: Stop active old Broker work.

For each active old Agent ID, run interrupt, then run:

~~~
luna-agent broker shutdown --json
~~~

Expected: no old Agent remains in a running state.

- [ ] Step 3: Uninstall without purging data.

Run:

~~~
luna-agent uninstall --json
~~~

Expected: executable, skill directory, PATH entry, and bridge marker are removed; agents.db remains.

- [ ] Step 4: Verify the migration boundary.

Run:

~~~
Test-Path '<BRIDGE_DATA_ROOT>/data/agents.db'
Test-Path '<BRIDGE_DATA_ROOT>/bin/luna-agent.exe'
Test-Path '<CODEX_HOME>/skills/luna-agent-bridge/SKILL.md'
Select-String -Path '<CODEX_HOME>/AGENTS.md' -Pattern 'CODEX LUNA AGENT BRIDGE'
~~~

Expected: database is True; executable and skill are False; marker search returns no match.

### Task 2: Configure native Luna defaults

**Files:**
- Modify: <CODEX_HOME>/config.toml
- Create: <CODEX_HOME>/agents/luna-worker.toml

**Interfaces:**
- Consumes: Existing user config.toml.
- Produces: agents defaults and a named luna_worker custom Agent.

- [ ] Step 1: Back up the current Codex config.

Create a timestamped backup under <BRIDGE_DATA_ROOT>/backups/native-migration/ before editing. Preserve the original bytes exactly.

- [ ] Step 2: Add native defaults without replacing existing keys.

Append this TOML block only if an equivalent key is absent; otherwise replace only the four agents keys:

~~~
[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "max"
~~~

- [ ] Step 3: Create the custom Agent manifest.

Write luna-worker.toml with:

~~~
name = "luna_worker"
description = "使用 Luna max 执行边界清晰、可独立完成的代码探索、实现、测试和审查任务。"
model = "gpt-5.6-luna"
model_reasoning_effort = "max"
sandbox_mode = "workspace-write"
developer_instructions = """
只处理主 Agent 委派的有界任务。
遵循当前工作区的 AGENTS.md 和用户指令。
开始前确认任务范围，完成后返回结论、修改文件和验证证据。
不要主动提交代码，不要扩大任务范围。
"""
~~~

- [ ] Step 4: Parse and validate the resulting TOML.

Run a Python tomllib check asserting agents.enabled is True, max_concurrent_threads_per_session is 4, default_subagent_model is gpt-5.6-luna, default_subagent_reasoning_effort is max, and the custom Agent has the same model and effort with workspace-write sandbox.

### Task 3: Install the native delegation rule

**Files:**
- Modify: <CODEX_HOME>/AGENTS.md

**Interfaces:**
- Consumes: Existing user-level Codex rules and Java project rules.
- Produces: An idempotent native Luna delegation block.

- [ ] Step 1: Remove stale Luna bridge text.

Verify that the old CODEX LUNA AGENT BRIDGE block is absent. Do not remove unrelated Java rules.

- [ ] Step 2: Append the native rule block.

Add exactly one marked block:

~~~
<!-- BEGIN CODEX NATIVE LUNA AGENTS -->
## 原生 Luna 子 Agent

默认使用 Codex 原生子 Agent，模型为 gpt-5.6-luna，推理强度为 max，最多 4 个并发线程。
遇到两个及以上互不依赖的有界任务时，可以主动拆解并委派；共享文件、强顺序依赖或冲突风险高的任务不得并行。
主 Agent 负责最终决策、冲突处理、验证和结果汇总。
不要调用外部 luna-agent CLI，也不要创建镜像线程。
<!-- END CODEX NATIVE LUNA AGENTS -->
~~~

- [ ] Step 3: Verify idempotence and scope.

Run a marker count and content check. Expected: exactly one native block, zero bridge blocks, and all unrelated existing rules preserved.

### Task 4: Verify native desktop behavior after restart

**Files:**
- Read: <CODEX_HOME>/config.toml
- Read: <CODEX_HOME>/agents/luna-worker.toml
- Read: <CODEX_HOME>/AGENTS.md

**Interfaces:**
- Consumes: Native configuration and rules from Tasks 2-3.
- Produces: Fresh evidence from a new Codex process; no source-code changes.

- [ ] Step 1: Restart Codex Desktop so user-level config and custom Agent files load.
- [ ] Step 2: Ask the new main session to use luna_worker for a read-only task returning a fixed marker; do not use luna-agent CLI.
- [ ] Step 3: Confirm the child thread appears in native Subagents activity/sidebar, reports a completed result, and the parent receives it.
- [ ] Step 4: Start a bounded long-running native task, fully exit Codex, and verify no luna-agent Broker or external Luna process remains; reopen Codex and confirm no automatic external resume occurs.

### Task 5: Repository-level verification and handoff

**Files:**
- Read: docs/superpowers/specs/2026-08-14-native-luna-subagent-design.md
- Read: docs/superpowers/plans/2026-08-14-native-luna-subagent-plan.md

**Interfaces:**
- Consumes: Completed configuration migration and fresh desktop evidence.
- Produces: Verification report with exact paths, checks, and any limitation.

- [ ] Step 1: Run existing bridge unit tests.

~~~
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

Expected: existing source tests remain green; no source behavior was changed by the native migration.

- [ ] Step 2: Re-read the acceptance checklist and report any item requiring manual confirmation after restart.
- [ ] Step 3: Do not commit; leave the worktree uncommitted per project instructions.
