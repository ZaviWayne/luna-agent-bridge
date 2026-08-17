# 原生 Luna 子 Agent 设计

## 目标

使用 Codex 原生子 Agent 能力运行 `gpt-5.6-luna`、`max` 任务，使子 Agent 线程直接出现在 Codex 桌面端原生 Subagents 活动区和任务界面中，并由主 Agent 使用原生工具完成创建、通信、等待、中断和结果汇总。

## 核心决策

1. 默认子 Agent 模型为 `gpt-5.6-luna`，默认推理强度为 `max`。
2. 使用 Codex 原生子 Agent 编排，不再通过 `luna-agent` Broker 创建默认子 Agent。
3. 子 Agent 生命周期由 Codex 桌面端和所属主会话管理；Codex 完全退出后不允许存在独立的外部 Luna 执行进程。
4. 原生子 Agent 线程直接使用 Codex 的侧边栏和 Subagents `Active / Done` 界面，不创建镜像线程或执行侧边栏同步。
5. 现有 `luna-agent-bridge` 执行无数据清除卸载：停止 Broker，移除可执行文件、默认技能和旧指令，但保留 SQLite 历史数据与备份用于回滚。

## 用户级配置

在用户级 Codex 配置中启用并设置原生子 Agent 默认值：

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "max"
```

配置写入 `~/.codex/config.toml`，因此跨项目路径和新 Codex 会话持续生效。已有配置项必须保留，不能覆盖主 Agent 的模型、权限、插件、MCP 或项目可信设置。

## 自定义原生 Agent

创建用户级 `~/.codex/agents/luna-worker.toml`：

```toml
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
```

默认模型配置保证未显式指定模型的原生子 Agent 使用 Luna max；命名 Agent 配置用于主 Agent 需要明确选择执行型 Luna Worker 的场景。

## 主 Agent 委派策略

用户级 `~/.codex/AGENTS.md` 增加带标记的原生 Luna 配置块，规则如下：

- 遇到两个及以上互不依赖、可并行执行的有界任务时，主 Agent 可以主动拆解并委派；
- 默认使用原生 `luna_worker` 或未显式覆盖模型的原生子 Agent；
- 同一主会话最多并行四个子 Agent；
- 写入同一文件、依赖前序结果或存在共享状态的任务不得并行；
- 主 Agent 必须保留最终决策、冲突处理、验证和用户汇总责任；
- 用户明确要求不使用子 Agent 时不得委派；
- 不调用外部 `luna-agent` CLI；用户要求访问旧历史时使用保留数据库的只读导出流程。

## 侧边栏与线程行为

原生 Codex 子 Agent 创建后：

1. Codex 自动创建 Agent thread；
2. 桌面端显示子 Agent 活动和线程；
3. 用户可以打开线程检查过程和结果；
4. 主 Agent 使用原生通信工具发送补充指令；
5. 主 Agent 等待一个或多个子 Agent 完成并汇总结果；
6. 完成线程由 Codex 归入已完成状态。

不实现自定义标题同步、置顶同步、影子线程或 Broker 到桌面端的 UI 映射。

## 生命周期

- 子 Agent 只在所属 Codex 运行环境中执行；
- 完全退出 Codex 后不启动、不保留独立外部 Broker 执行；
- 重新打开 Codex 后，历史线程由 Codex 自身展示和管理；
- 不承诺未完成子 Agent 在新主会话中自动续跑；
- 需要继续时，用户可以打开原线程或让新的主 Agent 基于现有线程结果重新委派。

本设计选择原生生命周期一致性，而不是外部执行进程的跨应用存活。

## 会话与工作区隔离

- 子 Agent 归属于创建它的主 Codex 会话；
- 同一工作区的不同主会话由 Codex 原生线程 ID 区分；
- 不再维护桥接层 `owner_session_id` 作为新子 Agent 的身份来源；
- 工作区权限、沙箱和 `AGENTS.md` 由原生 Codex 配置继承；
- 新项目自动获得用户级 Luna 默认模型，同时继续叠加项目级配置。

## 旧桥接迁移

为避免外部 Broker 与原生子 Agent 同时生效，本次切换采用无数据清除卸载：

1. 切换前列出旧 Agent，并中断仍在运行的旧任务；
2. 关闭旧 Broker，确认其创建的 Codex 子进程均已退出；
3. 执行不带 `--purge-data` 的卸载；
4. 移除用户级 `luna-agent-bridge` 技能和“使用 `luna-agent` CLI”指令块；
5. 移除用户级 `luna-agent.exe`，防止旧 Broker 被再次自动启动；
6. 保留 SQLite 数据库、日志和安装备份；
7. 如需读取旧历史，先从保留数据生成只读导出，或由用户明确批准后重新安装桥接器。

## 错误处理

- 原生 Luna 模型不可用：子 Agent 创建失败并向主 Agent 报告，不自动回退到其他模型。
- `max` 不受当前模型支持：创建失败并报告配置不兼容，不静默降低推理强度。
- 达到四个并发线程：主 Agent 等待现有子 Agent 完成后再创建新的任务。
- 子 Agent 需要额外审批：由 Codex 原生审批流程处理，主 Agent不得绕过。
- 子 Agent 中断或失败：主 Agent读取线程错误，决定重试、重新委派或在主线程处理。
- 用户级配置解析失败：保留原文件备份并恢复修改前内容。

## 测试策略

### 配置测试

- 验证 `~/.codex/config.toml` 保留全部原配置并新增合法 `[agents]` 配置。
- 验证 `~/.codex/agents/luna-worker.toml` 能被 Codex 加载。
- 验证用户级 `AGENTS.md` 不再默认调用外部桥接。
- 验证旧桥接技能、可执行文件和默认指令已移除，SQLite 历史数据仍存在。

### 原生运行测试

- 创建一个只返回固定文本的原生 Luna 子 Agent；
- 确认实际模型为 `gpt-5.6-luna`，推理强度为 `max`；
- 确认子 Agent 活动和线程出现在 Codex 桌面端；
- 向运行中的子 Agent 发送补充消息并读取结果；
- 并行创建四个独立子 Agent，确认主 Agent在有空闲槽位前不会创建第五个并行任务；
- 确认不同主会话和不同工作区的线程不会混淆。

### 生命周期验收

- 启动一个耗时原生 Luna 子 Agent；
- 完全退出 Codex 桌面端；
- 确认没有外部 `luna-agent` Broker 或由其创建的 Codex 子进程继续运行；
- 重新打开 Codex，确认历史线程仍可查看；
- 确认系统没有自动启动旧桥接 Agent。

## 验收标准

- 默认原生子 Agent 使用 `gpt-5.6-luna` 和 `max`，不静默回退。
- 原生子 Agent 线程出现在 Codex 桌面端原生界面中。
- 主 Agent 能原生创建、通信、等待、中断并汇总子 Agent。
- 用户级配置跨项目和新会话持续生效。
- Codex 完全退出后没有外部 Luna Broker 继续执行。
- 旧桥接数据完整保留，旧 Broker、可执行文件、技能和默认调用路径均已移除。
