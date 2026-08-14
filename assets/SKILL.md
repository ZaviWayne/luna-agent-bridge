---
name: luna-agent-bridge-legacy
description: 已弃用的外部桥接 Skill，仅供用户明确安装旧版 luna-agent CLI 时使用；普通任务请使用 packages/native-luna-subagents。
---

# Luna Agent Bridge（已弃用兼容入口）

<!--
本文件只服务于显式执行 `luna-agent install` 的旧版外部桥接器。
普通任务不得复制或启用本文件；请使用 packages/native-luna-subagents。
-->

需要跨会话持久化的外部桥接任务时，使用用户级 `luna-agent` CLI，不要将其描述为 Codex 原生子 Agent。固定策略为 `gpt-5.6-luna`、`max`、`workspace-write`，最多四个并发 Agent。

常用命令：

```powershell
luna-agent spawn --name reviewer --cwd <workspace-path> --task "检查当前修改"
luna-agent send reviewer "重点检查事务边界"
luna-agent status reviewer
luna-agent list --all-sessions
luna-agent adopt <global-agent-id>
luna-agent wait reviewer --timeout 300
luna-agent result reviewer
luna-agent interrupt reviewer
luna-agent resume reviewer
luna-agent archive reviewer
```

会话隔离规则：CLI 优先使用显式 `--session`，其次使用 Codex Desktop 注入的 `CODEX_THREAD_ID`，没有会话上下文时使用 `standalone`。跨项目或跨主会话操作使用全局 Agent ID；新主会话接管时应在交接信息中保留该 Agent ID。

用户关闭 Codex 前必须先中断外部 Agent，再执行 `luna-agent broker shutdown`。消息会排队到轮次边界，不能在模型生成过程中即时注入。
