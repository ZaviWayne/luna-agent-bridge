# Luna Agent 主会话隔离设计

## 目标

让同一工作区中并行运行的多个 Codex 主会话能够各自管理同名 Luna 子 Agent；新会话默认只看到自己创建的 Agent，同时保留通过全局 Agent ID 跨会话接管和恢复任务的能力。

## 现状与约束

- `agents` 表目前只保存工作区、名称和 Luna 子 Agent 自身的 `codex_thread_id`，没有父 Codex 主会话标识。
- Agent 名称当前在同一工作区内唯一，因此不同主会话创建同名 Agent 会冲突。
- Codex Desktop 当前为每个主会话注入 `CODEX_THREAD_ID` 环境变量；该值在不同会话间不同，适合作为持久化归属键。
- 全局 Agent UUID 必须继续跨工作区、跨会话解析。
- 不改变 Luna 子 Agent自身的 Codex 会话恢复机制。
- 不引入第三方依赖；SQLite 数据库须平滑升级。

## 方案选择

### 方案 A：使用 `CODEX_THREAD_ID` 作为父会话键（采用）

每次 CLI 请求从显式 `--session` 参数读取会话键；未提供时读取 `CODEX_THREAD_ID`；两者都不存在时使用固定 `standalone` 键。Agent 唯一性和默认名称解析范围变为“工作区 + 父会话键 + 名称”。

优点是无需用户手工维护任务组 ID，Codex 会话天然隔离，关闭并重新打开同一会话后仍可通过原会话键恢复。缺点是手工终端必须使用 `--session` 才能模拟多个主会话。

### 方案 B：Bridge 自行生成任务组 ID

首次调用时生成任务组 ID，并要求主 Agent 在后续消息中携带该 ID。实现简单但依赖主 Agent持续记忆；会话重开后容易丢失归属。

### 方案 C：只按工作区和名称推断

不增加归属字段，仅在名称冲突时显示候选。改动最小，但无法提供默认隔离，也不能满足多个主会话同名 Agent的要求。

## 数据模型

将数据库版本从 1 升级到 2，在 `agents` 表新增：

```sql
owner_session_id TEXT NOT NULL
```

取值规则：

1. `--session <id>`（显式参数优先）。
2. `CODEX_THREAD_ID`（Codex Desktop 默认来源）。
3. `standalone`（无会话上下文的手工调用）。

现有版本 1 数据迁移时统一写入 `legacy`，不改变 Agent UUID、消息、轮次、结果和子 Agent自身的 `codex_thread_id`。

所有迁移在 SQLite 事务中执行；迁移失败回滚并保留原数据库。

## CLI 与协议行为

### 默认隔离

- `spawn` 将当前会话键写入新 Agent。
- `status/send/wait/messages/result/interrupt/resume/archive` 使用名称时，仅在当前工作区和当前会话键内解析。
- 使用全局 Agent UUID 时维持现有行为，直接解析目标 Agent，允许显式跨会话接管。
- `list` 默认列出当前工作区和当前会话的 Agent。

### 全局查看与接管

新增：

```text
luna-agent list --all-sessions
luna-agent adopt <agent-id>
```

`list --all-sessions` 查看当前工作区所有会话的 Agent，并返回 `owner_session_id`。

`adopt <agent-id>` 将目标 Agent的 `owner_session_id` 更新为当前会话键。只有非归档 Agent可接管；运行中的 Agent允许接管，以支持 Codex 重开后继续协调后台任务。全局 UUID 访问仍是显式操作，旧会话若仍持有 UUID 仍可发送消息。

所有 JSON 响应中的 Agent记录增加 `owner_session_id`，文本输出显示会话键的短形式和完整 Agent UUID。

### 协议兼容

Broker 请求增加可选 `session_id` 参数，缺省时由 Broker 使用请求携带的环境解析结果；协议版本保持 1，因为新增字段和参数均向后兼容。旧客户端连接新 Broker 时使用 `standalone` 作为缺省会话键。

## 会话解析组件

新增单一职责的会话上下文解析函数，负责：

- 校验并规范化显式 `--session`。
- 读取 `CODEX_THREAD_ID`。
- 回退到 `standalone`。
- 为所有 CLI 命令和 Broker 请求提供同一会话键，避免不同入口产生不同隔离逻辑。

会话键只作为本地数据库分组标识，不作为外部认证凭据；Agent UUID 仍是唯一寻址标识。

## 测试设计

必须先编写并运行失败测试，再实现：

1. 同一工作区、不同会话可创建同名 Agent。
2. 同一工作区、同一会话仍拒绝同名未归档 Agent。
3. 按名称的 `status/send/list` 默认只命中当前会话。
4. 按全局 Agent UUID 可跨会话读取和发送。
5. `list --all-sessions` 返回所有会话并包含归属字段。
6. `adopt` 将 Agent迁移到当前会话，之后可按名称访问。
7. `CODEX_THREAD_ID`、显式 `--session`、`standalone` 的优先级正确。
8. 版本 1 数据迁移到版本 2 后保持原有 Agent、消息和轮次数据。
9. 空会话键、过长会话键和非法参数返回明确错误。
10. 现有端到端生命周期、恢复和并发测试继续通过。

## 错误处理与边界

- 会话键为空或超过固定长度时拒绝请求，不静默截断。
- `adopt` 目标不存在或已归档时返回领域错误。
- 默认名称解析找不到目标时，错误消息提示当前工作区和会话范围，并建议使用全局 Agent UUID 或 `--all-sessions`。
- 同一 Agent 的消息、轮次和进程生命周期不因归属迁移而改变。
- 数据库升级只增加列和索引，不删除历史数据。

## 验收标准

- 两个 Codex Desktop 会话在同一工作区均能创建 `reviewer`，互不冲突。
- 每个会话的 `list/status/send` 默认只操作自己的 `reviewer`。
- 新会话使用旧 Agent UUID 或 `adopt` 后可以继续读取、发送、等待和恢复后台 Agent。
- 旧版本数据库可自动升级，所有既有测试和新增回归测试通过。
