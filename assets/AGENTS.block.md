<!-- 已弃用：不要将本文件复制为全局 AGENTS.md；仅由显式执行 luna-agent install 的旧版外部桥接器使用。 -->
<!-- BEGIN CODEX LUNA AGENT BRIDGE -->
## Luna 子 Agent（旧版外部桥接）

仅当用户明确要求外部持久化时，使用用户级 `luna-agent` CLI；普通任务请使用 packages/native-luna-subagents。外部桥接默认使用 `gpt-5.6-luna`、`max`、`workspace-write`，最多 4 个并发 Agent。

跨工作区或跨主会话通信使用全局 Agent ID。CLI 通过显式 `--session` 或 Codex Desktop 的 `CODEX_THREAD_ID` 区分主会话；新主会话接管时必须保留 Agent ID。关闭 Codex 前先中断外部 Agent，再执行 `luna-agent broker shutdown`。
<!-- END CODEX LUNA AGENT BRIDGE -->
