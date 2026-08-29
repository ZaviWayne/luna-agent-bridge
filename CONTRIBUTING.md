# Contributing

English | [中文](CONTRIBUTING_CN.md)

Thank you for contributing to Luna Agent Bridge. The project has two intentionally separate release surfaces:

- `packages/native-luna-subagents`: a Skill that only guides Codex native subagents.
- `plugins/luna-agent-bridge`: an external Windows/macOS bridge plugin that users explicitly opt into.

Codex native subagents are the default. Model routing also uses the native `[agents]` configuration. Use the external bridge only when cross-session persistence, recovery, or task adoption is explicitly required.

## Development Rules

1. Do not describe the external broker, SQLite persistence, or the `luna-agent` CLI as Codex native capabilities.
2. The native Skill must not start background processes, modify `PATH`, store credentials, or bypass sandbox controls.
3. Changes to external bridge processes, local IPC, automatic approval, or data directories require tests and security documentation.
4. After modifying Python code, run the test command for the relevant platform.

   Windows PowerShell:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -q
   ```

   macOS:

   ```bash
   .venv/bin/python -m unittest discover -s tests -q
   ```

5. After installing `PyYAML` with `pip install -e ".[dev]"`, run the corresponding official validator when modifying a Skill or plugin manifest.

## Submissions

Describe the change scope, test commands, and known risks. Do not commit `.venv`, `build`, `dist`, `outputs`, `__pycache__`, or runtime logs.
