# Luna Agent 主会话隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 Codex 主会话自动隔离同一工作区的 Luna Agent，并提供显式跨会话查看与接管能力。

**Architecture:** CLI 从显式 `--session`、`CODEX_THREAD_ID` 或 `standalone` 解析统一会话键，并将其随 Broker 请求传递；Broker 在 Storage 层按工作区、会话键和名称解析 Agent。SQLite 从版本 1 平滑迁移到版本 2，新增 `owner_session_id`，全局 Agent UUID 仍绕过会话筛选以支持恢复和接管。

**Tech Stack:** Python 3.12、SQLite、`argparse`、Windows named pipe、`unittest`、PyInstaller。

## Global Constraints

- 不引入第三方依赖。
- 数据库升级必须保留现有 Agent、消息、轮次、结果和子 Agent Codex thread ID。
- 会话键不得为空或超过 128 个字符；不得静默截断。
- 全局 Agent UUID 继续支持跨工作区、跨会话寻址。
- 运行中的 Agent允许显式 `adopt`，不得改变其进程或消息生命周期。
- 遵循项目 AGENTS.md：UTF-8、LF、4 空格、中文错误信息、公共方法保留 Javadoc、避免魔法值。
- 项目约定禁止 Agent 自动提交 Git；计划中的 commit 步骤不执行。

---

### Task 1: 会话上下文解析与领域记录

**Files:**
- Create: `src/luna_agent_bridge/session.py`
- Modify: `src/luna_agent_bridge/domain.py`
- Test: `tests/test_session.py`
- Test: `tests/test_config_domain.py`

**Interfaces:**
- `resolve_session_id(explicit: str | None = None, environ: Mapping[str, str] | None = None) -> str`
- `validate_session_id(value: str) -> str`
- `AgentRecord.owner_session_id: str`

- [ ] **Step 1: Write the failing tests**

```python
def test_explicit_session_has_priority_over_codex_thread_id():
    self.assertEqual("manual", resolve_session_id("manual", {"CODEX_THREAD_ID": "desktop"}))

def test_codex_thread_id_is_used_before_standalone_fallback():
    self.assertEqual("desktop", resolve_session_id(None, {"CODEX_THREAD_ID": "desktop"}))
    self.assertEqual("standalone", resolve_session_id(None, {}))

def test_empty_or_overlong_session_is_rejected():
    with self.assertRaises(ValueError):
        validate_session_id(" ")
    with self.assertRaises(ValueError):
        validate_session_id("x" * 129)
```

- [ ] **Step 2: Run the focused tests and verify the expected missing-symbol failure**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_session -v`

Expected: FAIL because `session.py` and the new session functions do not yet exist.

- [ ] **Step 3: Implement the minimal session module and record field**

Implement constants `STANDALONE_SESSION_ID`, `LEGACY_SESSION_ID`, `MAX_SESSION_ID_LENGTH = 128`; use explicit value first, then `CODEX_THREAD_ID`, then `standalone`; reject non-string, blank, and overlong values. Add `owner_session_id` to `AgentRecord` and preserve dataclass field ordering for all storage constructors.

- [ ] **Step 4: Run focused tests and the existing domain tests**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_session tests.test_config_domain -v`

Expected: PASS.

### Task 2: SQLite v2 migration and session-scoped Storage

**Files:**
- Modify: `src/luna_agent_bridge/storage.py`
- Modify: `src/luna_agent_bridge/domain.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- `Storage.create_agent(name, workspace, settings, owner_session_id="standalone") -> AgentRecord`
- `Storage.resolve_agent(identifier, workspace=None, owner_session_id=None, include_archived=False) -> AgentRecord`
- `Storage.list_agents(workspace=None, include_archived=False, owner_session_id=None) -> list[AgentRecord]`
- `Storage.adopt_agent(identifier, owner_session_id, workspace=None) -> AgentRecord`

- [ ] **Step 1: Add failing Storage tests for isolation and migration**

```python
def test_same_name_is_allowed_for_different_sessions(self):
    first = self.storage.create_agent("reviewer", self.workspace, Settings.defaults(), "session-a")
    second = self.storage.create_agent("reviewer", self.workspace, Settings.defaults(), "session-b")
    self.assertNotEqual(first.id, second.id)
    self.assertEqual(first.id, self.storage.resolve_agent("reviewer", self.workspace, "session-a").id)
    self.assertEqual(second.id, self.storage.resolve_agent("reviewer", self.workspace, "session-b").id)

def test_adopt_moves_agent_to_target_session(self):
    agent = self.storage.create_agent("reviewer", self.workspace, Settings.defaults(), "old")
    adopted = self.storage.adopt_agent(agent.id, "new")
    self.assertEqual("new", adopted.owner_session_id)

def test_v1_database_migrates_existing_agents_to_legacy(self):
    # 创建版本 1 最小 schema 和一条 Agent，然后重新用 Storage.open 打开。
    migrated = Storage.open(database_path)
    self.assertEqual("legacy", migrated.get_agent(agent_id).owner_session_id)
```

- [ ] **Step 2: Run Storage tests and verify they fail for the missing owner column/scoping**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_storage -v`

Expected: FAIL with missing `owner_session_id` behavior or the existing same-name conflict.

- [ ] **Step 3: Implement schema version 2 and atomic migration**

Set `SCHEMA_VERSION = 2`; add `owner_session_id TEXT NOT NULL` to fresh schemas and an index on `(workspace, owner_session_id, name, state)`. When the stored version is 1, run one `BEGIN IMMEDIATE` transaction that executes `ALTER TABLE agents ADD COLUMN owner_session_id TEXT NOT NULL DEFAULT 'legacy'`, creates the new index, and updates `schema_version` to 2; rollback on any exception.

- [ ] **Step 4: Implement session-aware create, resolve, list, and adopt**

For name lookup, add `owner_session_id` to the workspace predicate when supplied; preserve direct UUID lookup before name lookup. Enforce duplicate names only for the same workspace and owner session among non-archived records. `adopt_agent` must reject archived records, validate the target session, update only ownership and `updated_at`, then return the updated record.

- [ ] **Step 5: Run focused Storage tests and all current Storage regression tests**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_storage -v`

Expected: PASS, including FIFO, recovery, concurrent sequence, same-session duplicate, cross-session same-name, adopt, and v1 migration cases.

### Task 3: Service, protocol, and CLI session routing

**Files:**
- Modify: `src/luna_agent_bridge/protocol.py`
- Modify: `src/luna_agent_bridge/pipe_client.py`
- Modify: `src/luna_agent_bridge/pipe_server.py`
- Modify: `src/luna_agent_bridge/service.py`
- Modify: `src/luna_agent_bridge/cli.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_protocol_pipe.py`
- Test: `tests/test_service.py`

**Interfaces:**
- CLI lifecycle commands accept `--session`; absent value resolves from `CODEX_THREAD_ID`.
- `list --all-sessions` lists all sessions in the current workspace.
- `adopt <agent>` moves ownership to the current session.
- Broker params carry optional `session_id`; absent old clients use `standalone`.

- [ ] **Step 1: Add failing CLI/protocol/service tests**

```python
def test_spawn_includes_resolved_session_id(self):
    client = FakeClient()
    with patch.dict("luna_agent_bridge.cli.os.environ", {"CODEX_THREAD_ID": "desktop"}, clear=True):
        main(["spawn", "--name", "reviewer", "--task", "检查"], client=client)
    self.assertEqual("desktop", client.requests[0][1]["session_id"])

def test_list_all_sessions_sends_flag(self):
    client = FakeClient()
    main(["list", "--all-sessions"], client=client)
    self.assertTrue(client.requests[0][1]["all_sessions"])
```

- [ ] **Step 2: Run CLI, protocol, and service tests to verify failure**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_cli tests.test_protocol_pipe tests.test_service -v`

Expected: FAIL because parser, params, and service methods do not accept session context.

- [ ] **Step 3: Add session flags and propagate params through PipeClient/PipeServer**

Add `--session` to `spawn`, `send`, lifecycle commands, `wait`, `list`, and `adopt`; add `--all-sessions` to `list`. Resolve with `resolve_session_id` in `_command_params`, put `session_id` into request params, and preserve `--all` as the existing all-workspaces behavior. Dispatch all name-based service calls with `session_id`; dispatch UUID calls unchanged. Add `adopt` to `KNOWN_COMMANDS` and Broker dispatch.

- [ ] **Step 4: Add AgentService session arguments and adopt operation**

Thread `owner_session_id` through `spawn`, `send`, `status`, `messages`, `result`, `wait`, `interrupt`, `resume`, `archive`, and `list_agents`. Keep default `standalone` for direct Python callers. Implement `AgentService.adopt(identifier, owner_session_id, workspace=None)` and return the updated record.

- [ ] **Step 5: Run focused tests and verify name isolation, all-session listing, UUID access, and adopt**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_cli tests.test_protocol_pipe tests.test_service -v`

Expected: PASS with no regressions in existing lifecycle and error-code mapping.

### Task 4: End-to-end regression coverage

**Files:**
- Modify: `tests/test_end_to_end.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_cli.py`

**Interfaces:** Reuse the session-aware Storage, Service, and CLI interfaces from Tasks 1-3.

- [ ] **Step 1: Add a failing end-to-end multi-session test**

Create two agents named `reviewer` in one workspace with `session-a` and `session-b`, wait for both, send a follow-up by each session-scoped name, then assert their last results remain separate. Also assert a third session can retrieve the selected Agent by UUID and adopt it.

- [ ] **Step 2: Run the new test and verify it fails before the integrated fix**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_end_to_end -v`

Expected: FAIL if any routing path drops or ignores the session key.

- [ ] **Step 3: Adjust only integration boundaries exposed by the failing test**

Keep persistence and process semantics unchanged; correct only missing session propagation, default filtering, or response serialization.

- [ ] **Step 4: Run the complete Python test suite**

Run: `\.venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: PASS with zero failures and errors.

### Task 5: User-facing skill, build, install, and final verification

**Files:**
- Modify: `assets/SKILL.md`
- Modify: `assets/AGENTS.block.md`
- Modify: `tests/test_installer.py`
- Modify: `outputs/docs/superpowers/specs/2026-08-14-luna-agent-session-isolation-design.md` only if implementation details require a corrected statement

**Interfaces:** Installed `luna-agent.exe` and user-level skill must describe automatic `CODEX_THREAD_ID` isolation, `--all-sessions`, and `adopt`.

- [ ] **Step 1: Add failing installer/asset assertions**

Assert the installed skill mentions session isolation, `--all-sessions`, and `adopt`; assert the global rule tells Codex to preserve and use the Agent UUID when handing off between sessions.

- [ ] **Step 2: Run installer tests and verify the new assertions fail**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_installer -v`

Expected: FAIL because the assets do not document the new commands.

- [ ] **Step 3: Update assets and installer-facing documentation**

Document the precedence `--session` → `CODEX_THREAD_ID` → `standalone`, default current-session listing, `--all-sessions`, UUID cross-session access, and `adopt`. Keep user-facing error and status text in Chinese.

- [ ] **Step 4: Run the full suite, compile, and package the executable**

Run: `\.venv\Scripts\python.exe -m unittest discover -s tests -v`; `\.venv\Scripts\python.exe -m compileall -q src tests`; `powershell -ExecutionPolicy Bypass -File scripts\build.ps1`

Expected: all tests pass, compileall exits 0, and `dist\luna-agent.exe --version` prints `0.1.0` or the current package version.

- [ ] **Step 5: Install the rebuilt executable and run a fresh isolation smoke test**

Run the packaged executable's `install` path, then create two same-name Agents under two explicit session IDs in a temporary workspace; verify default lists are isolated, `--all-sessions` shows both, and `adopt` makes the selected Agent visible by name in the adopting session. Preserve the existing persistent database and do not purge data.

- [ ] **Step 6: Record verification evidence without committing**

Capture test, compile, package, and smoke-test output in `outputs/luna-agent-bridge/verification-session-isolation.md`; inspect the final diff and installed paths before reporting completion.
