# Privacy Notice

This project is an open-source, skills-only Codex plugin with an optional local Windows and macOS bridge. The plugin does not collect, sell, or transmit personal data to the project maintainers.

When the optional bridge is used, task metadata, events, queued messages, and recovery state are stored locally under `%LOCALAPPDATA%\CodexLunaAgent` on Windows or `~/Library/Application Support/CodexLunaAgent` on macOS. The bridge invokes the user's local Codex CLI. Prompts and command results may therefore be processed by the user's Codex account and the services configured in that local environment, subject to their terms and privacy policies.

The project does not request, read, or store Codex credentials. Users are responsible for reviewing local permissions, command execution, and any third-party services used by their Codex installation.

For privacy questions or requests concerning this project, open a public issue in the [GitHub repository](https://github.com/ZaviWayne/luna-agent-bridge/issues). Changes to this notice will be published in this repository.
