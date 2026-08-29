# Luna Agent Bridge

English | [中文](README_CN.md)

Use Codex native subagents by default and route suitable tasks to `gpt-5.6-luna` through the native `[agents]` configuration. Enable the external bridge only when cross-session persistence, recovery, or task adoption is explicitly required.

## Why This Project Exists

The Codex main agent usually owns requirement analysis, technical decisions, and final integration. Subtasks such as code review, test execution, research, and focused repository searches have clearer boundaries, so users may prefer a model configuration suited to frequent delegated work instead of inheriting the main agent's configuration for every task.

This project separates two concepts in model routing: `gpt-5.6-luna` is the model, while `max` is the reasoning effort. The default path configures both through Codex native `[agents]` settings. The external bridge passes the same configuration to the Codex CLI only when the user explicitly opts into cross-session capabilities. Users should measure cost, latency, and quality in their own tasks, accounts, and environments. This project does not promise a fixed cost reduction or guarantee model availability in every Codex environment.

The task flow is:

```text
Main agent (planning, decisions, and integration)
├─ Complex or high-risk tasks ─────────────→ Main agent's high-capability model
└─ Frequent, well-bounded subtasks ────────→ gpt-5.6-luna + max
                                             └─ Optional local queue and cross-session recovery
```

## Choose a Path

| Requirement | Recommended path |
| --- | --- |
| Routine decomposition, code review, testing, or research | Codex native subagents + this project's Skill |
| Route work to `gpt-5.6-luna` with `max` reasoning | Codex native subagents + `[agents]` configuration |
| Persist, recover, or adopt tasks across Codex sessions | External bridge |
| Concurrent work contained in the current session | Prefer Codex native subagents |

Codex manages native subagent scheduling, making it the lightest path in most cases. The external bridge is an optional compatibility layer, not an official Codex native feature. It cannot extend native internal channels, sidebar integration, or lifecycle guarantees to every environment.

## Recommended: Native Skill

This is the default entry point for routine task decomposition. The Skill defines decomposition, concurrency, file ownership, messaging, and verification rules. It does not start a broker, modify `PATH`, store credentials, or claim cross-session persistence.

Each formal release includes `native-luna-subagents-skill-<version>.zip`. Extract it and place the included `native-luna-subagents` directory in your user-level Skill directory. You can also install it directly from a source checkout.

Windows PowerShell:

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex\skills' }
Copy-Item -Recurse -Force '.\packages\native-luna-subagents' (Join-Path $skillRoot 'native-luna-subagents')
```

macOS:

```bash
skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skill_root"
cp -R ./packages/native-luna-subagents "$skill_root/native-luna-subagents"
```

When user-level agent configuration is supported, set the model and reasoning effort as follows:

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "max"
```

After installing the Skill, saving the configuration, and reopening Codex, routine subtasks that need delegation use Codex native subagents by default. The external bridge is enabled only when the user explicitly requests cross-session persistence, recovery, or task adoption.

Model availability, native subagent visibility in the sidebar, and lifecycle behavior after a session closes remain controlled by the Codex environment. This project does not present them as persistence guarantees.

## Optional: External Bridge

Install the external bridge only when tasks must be persisted, recovered, or adopted across Codex sessions. Selecting `gpt-5.6-luna` with `max` reasoning is not, by itself, a reason to install the bridge. The bridge supports Windows, macOS, and Python 3.12 or later.

Install a published version from PyPI:

```powershell
python -m pip install luna-agent-bridge
luna-agent install
```

Alternatively, download the standalone Windows `luna-agent.exe` from [GitHub Releases](https://github.com/ZaviWayne/luna-agent-bridge/releases/latest). It does not require Python. Run `.\luna-agent.exe --help` to inspect the CLI, then run `.\luna-agent.exe install` before using the external bridge for the first time.

On macOS, download the binary matching your architecture: `luna-agent-macos-arm64` or `luna-agent-macos-x86_64`.

```bash
chmod +x ./luna-agent-macos-arm64
./luna-agent-macos-arm64 --help
./luna-agent-macos-arm64 install
```

The installer copies the executable to `~/Library/Application Support/CodexLunaAgent/bin/luna-agent` and adds a managed `PATH` block to `~/.zprofile`. Open a new terminal to use `luna-agent`, or run `source ~/.zprofile` in the current terminal.

The automated macOS build uses ad-hoc signing and is not yet notarized with an Apple Developer ID. Verify the SHA-256 checksum in the release. If Gatekeeper blocks a browser-downloaded binary, the user must explicitly allow it in macOS Privacy & Security settings; this project does not bypass platform security controls.

For source development or testing, use an editable installation.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
luna-agent install
```

After activation, PowerShell displays `(.venv)` in the prompt and `luna-agent` is available directly. Without activation, use the full virtual-environment path:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\luna-agent.exe install
```

If PowerShell blocks `Activate.ps1`, temporarily relax the policy for the current process or use the full-path commands above:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
luna-agent install
```

Common commands are shown below. They assume the virtual environment is active or the installation directory is already in `PATH`. On Windows without activation, replace `luna-agent` with `.\.venv\Scripts\luna-agent.exe`.

```console
luna-agent spawn --name reviewer --cwd <workspace-path> --task "Review the current changes"
luna-agent status <agent-id>
luna-agent send <agent-id> "Check the boundary conditions"
luna-agent wait <agent-id> --timeout 300
luna-agent result <agent-id>
luna-agent interrupt <agent-id>
luna-agent archive <agent-id>
```

The bridge starts tasks through the local Codex CLI and passes:

```text
--model gpt-5.6-luna
--config model_reasoning_effort="max"
```

Local state is stored under `%LOCALAPPDATA%\CodexLunaAgent` on Windows and `~/Library/Application Support/CodexLunaAgent` on macOS. It includes task metadata, events, queued messages, and recovery state. Messages sent while an agent is running are queued until a turn boundary; the bridge cannot inject them into an active model generation like a native internal channel.

Before closing Codex, interrupt all running external agents and shut down the broker:

```console
luna-agent broker shutdown
```

Do not assume that closing Codex reclaims the external broker. A normal uninstall preserves the database. Purge data only after explicit user confirmation:

```console
luna-agent uninstall --purge-data --yes
```

## Capability Boundaries

The bridge provides:

- Explicit model and reasoning-effort routing through the local Codex CLI.
- SQLite state storage, task events, message queues, and recovery entry points.
- Task lookup, messaging, waiting, and adoption after switching workspaces or reopening Codex.
- Up to four local workers, with managed processes stopped during broker shutdown.

The bridge does not provide:

- Official Codex native subagents, official sidebar integration, or official lifecycle guarantees.
- A way to bypass account permissions, model availability, sandboxing, or approval policies.
- Fixed cost savings, fixed latency, or model availability across accounts.
- Remote TCP control. State and control use a local Windows Named Pipe or macOS Unix Domain Socket only.

## Plugin Entry Point

`plugins/luna-agent-bridge` contains `.codex-plugin/plugin.json` and a Skill explicitly described as an optional compatibility layer. It does not automatically install executables, modify global configuration, or add a personal Marketplace entry. Add it explicitly through the Codex local plugin installation flow.

## Security Boundaries

- No remote TCP control.
- No reading or storage of Codex credentials.
- No full sandbox bypass mode.
- Named Pipe, Unix Domain Socket, automatic approval, user data directories, and process lifecycle remain part of the external bridge's security review surface.
- Never describe the external bridge or its cross-session recovery as official native Codex Luna behavior.

## Development and Testing

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

```bash
.venv/bin/python -m unittest discover -s tests -q
```

The JSONL files in `tests/fixtures` are deterministic Codex CLI response samples. They cover parsing, events, and recovery without network access or model usage and are not packaged at runtime.

## Automated GitHub Release and PyPI Publishing

The tag-triggered workflow is defined in `.github/workflows/release.yml`. Before the first release, configure a PyPI Trusted Publisher with:

- Owner: `ZaviWayne`
- Repository: `luna-agent-bridge`
- Workflow: `.github/workflows/release.yml`
- GitHub Environment: `pypi`

Update and commit the version in `pyproject.toml`, then push a matching tag:

```powershell
git tag v0.2.0
git push origin v0.2.0
```

The workflow builds a Windows EXE, macOS arm64 and x86_64 standalone binaries, wheel, sdist, optional bridge plugin archive, bridge Skill archive, native Skill archive, and checksums from the tagged commit. It creates a draft GitHub Release, publishes to PyPI, and then publishes the GitHub Release. A tag that does not match the `pyproject.toml` version fails before publishing. Never move a published tag.

Before release, remove `.venv`, `.venv-macos`, `build`, `dist`, `outputs`, `__pycache__`, and runtime logs. Validate Skills and plugin manifests with their corresponding official validators.

This project is licensed under the [MIT License](LICENSE).
