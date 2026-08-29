# Security Policy

English | [中文](SECURITY_CN.md)

## Scope

The native Skill does not execute external processes or provide a persistence service. The main security surface is the optional `luna-agent-bridge` external bridge. It starts local Codex CLI subprocesses, uses a Windows Named Pipe or macOS Unix Domain Socket, and writes agents, messages, turns, and recovery state to the user data directory.

## Current Boundaries

- No TCP listener or remote control port is exposed.
- Codex credentials are neither read nor stored.
- The macOS socket and authentication key are accessible only to the current user, and the broker does not listen on TCP.
- The bridge defaults to `workspace-write` and explicit Codex CLI approval parameters. It does not provide a full sandbox bypass mode.
- `--purge-data --yes` is an explicit data deletion operation. A normal uninstall must preserve the task database.
- Users must explicitly interrupt external agents and stop the broker before closing Codex. The external bridge must not be treated as native lifecycle management.

## Reporting a Vulnerability

Do not publish credentials, local IPC details, executable payloads, or reproducible local privilege-escalation steps in a public issue. Report them through a private channel provided by the maintainers and include the affected version, operating system and Python version, reproduction steps, and minimal logs.

Until a dedicated security email is configured, maintainers should provide a private reporting channel on the release page. Exploit details must remain private until a security fix is released.
