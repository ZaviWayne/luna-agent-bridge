---
name: native-luna-subagents
description: Use Codex native subagents to split and coordinate independent development, review, testing, or research tasks. Apply when the configured gpt-5.6-luna/max subagents are wanted without an external broker, background daemon, or cross-session persistence.
---

# Native Luna Subagents

Use Codex native subagents for parallel work. This skill only defines decomposition and handoff rules; it does not start an external CLI, create a broker, modify PATH, or present cross-session persistence as a native guarantee.

## Decompose the work

1. State the final deliverable, verification command, and non-negotiable boundaries.
2. Parallelize only when there are at least two independent, bounded work units.
3. Give every subagent exclusive file or module ownership, inputs, outputs, and an acceptance command.
4. Keep shared files, strict ordering, and high-conflict work serial.
5. Require a small verifiable result from every subtask; do not dispatch vague research requests.

## Native dispatch rules

- Use Codex native subagent dispatch and messaging. Do not invoke the external `luna-agent` CLI.
- Honor the active Codex default model and reasoning effort. This project recommends `gpt-5.6-luna` and `max` unless the user explicitly chooses otherwise.
- Use no more than 4 concurrent subagents per session. Queue or serialize additional work; do not create mirror threads.
- Use `explorer` for read-only code location and fact gathering, `worker` for bounded implementation, and `default` when the task cannot be split further.
- Subagents share the workspace. Preserve other agents' edits and report conflicts to the main agent.

## Messages and handoff

- Start each subtask with its goal, workspace, file ownership, forbidden scope, verification command, and report format.
- The main agent owns final synthesis, conflict resolution, and verification. Subagents must not commit or reset the shared workspace.
- On completion, report changed files, key decisions, test output, and unresolved risks.
- Use native messages for follow-up context; do not write temporary global configuration as a communication channel.
- Wait for, recover, or interrupt a subagent when it is no longer needed so no task remains dangling.

## Lifecycle boundary

- Native subagent lifetime is managed by the Codex session. This skill does not guarantee cross-session recovery or continued execution after Codex closes.
- Before closing Codex, stop or interrupt active subagents and write any required handoff into the project or a user-selected location.
- If true cross-session persistence is required, explain that it belongs to the optional external bridge; never start a background service from this skill.

## Completion checklist

Before finishing, the main agent must:

1. Mark every subtask successful, failed, or explicitly blocked.
2. Inspect the workspace diff for unauthorized edits, credentials, and generated artifacts.
3. Run the project's required tests, build, or static checks.
4. Summarize model, concurrency, ownership, verification, and remaining risk.
