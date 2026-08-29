---
name: luna-agent-bridge
description: Use the local Windows or macOS `luna-agent` bridge only when the user explicitly requests cross-session persistence, recovery, or adoption of an external task. Do not trigger for ordinary native subagent work or start a background broker without explicit opt-in.
---

# Luna Agent Bridge (optional compatibility layer)

This is an unofficial Windows and macOS external bridge, not a Codex native Luna subagent. Prefer native subagents for ordinary parallel work. Use this skill only when the user explicitly requests cross-session persistence, recovery, or adoption.

## Before use

1. Confirm that the user explicitly requested the external bridge and that `luna-agent` is already installed.
2. Do not install executables, edit PATH, write global Codex configuration, or start a persistent broker automatically.
3. Tell the user that the bridge stores agents, messages, turns, and recovery state under `%LOCALAPPDATA%\CodexLunaAgent` on Windows or `~/Library/Application Support/CodexLunaAgent` on macOS.
4. Confirm that the task does not require the native Codex sidebar, native message channel, or an official persistence guarantee.

## Common commands

```console
luna-agent spawn --name reviewer --cwd <workspace-path> --task "Review the current changes"
luna-agent status <agent-id>
luna-agent send <agent-id> "Check boundary conditions"
luna-agent wait <agent-id> --timeout 300
luna-agent result <agent-id>
luna-agent interrupt <agent-id>
luna-agent archive <agent-id>
```

For cross-session or cross-workspace work, use the global agent ID and record the ID, workspace, owner session, and last state in the handoff. Do not resolve a target by name alone.

## Lifecycle and security

- Never describe `luna-agent` results as Codex official native behavior.
- Do not use full sandbox bypasses, store Codex credentials, or expose TCP remote control.
- Before closing Codex, interrupt every active external agent and run `luna-agent broker shutdown`; do not assume Codex closing will reclaim the external broker.
- When the user wants to remove persistence, stop the broker first and only then use `luna-agent uninstall --purge-data --yes` after explicit confirmation.
- The external CLI cannot inject a message during model generation; messages queue until a turn boundary.

## Handoff format

Report the global agent ID, workspace, state, last result, queued message count, whether explicit recovery is needed, and the cleanup commands required before closing Codex.
