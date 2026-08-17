# 开源打包设计：原生 Luna Skill 与可选桥接器

## 目标

将项目整理成两个边界清晰的可开源交付物：一个只依赖 Codex 原生子 Agent 的 Skill，以及一个明确标注为可选兼容层的 Windows 外部桥接器。

## 方案

### 原生 Skill

`packages/native-luna-subagents` 是可复制、可安装的独立 Skill。它只提供任务拆解、并发限制、文件归属、消息交接和验证规则，不启动进程、不写入 SQLite、不修改 PATH，也不承诺跨会话持久化。它通过 Codex 原生子 Agent 和用户级 `luna-worker` 配置使用 `gpt-5.6-luna`/`max`；具体模型可用性和生命周期由 Codex 决定。

### 可选桥接插件

`plugins/luna-agent-bridge` 只作为外部桥接器的可选入口。插件清单声明它依赖本地 `luna-agent` CLI，明确提醒用户这是 Windows 专用、非原生、实验性能力；插件不会自动修改全局配置、PATH 或启动常驻 Broker。需要持久化和跨会话恢复的用户必须显式安装并管理桥接器。

## 安全边界

- 不把外部桥接器描述为 Codex 官方原生功能。
- 不在 Skill 中提供绕过沙箱、网络暴露或凭据存储逻辑。
- README 必须说明自动批准、Named Pipe、进程生命周期、数据目录和卸载行为。
- 发行包不包含 `.venv`、构建产物、缓存或运行日志。

## 发布结构

- `packages/native-luna-subagents/`：原生 Skill 包，包含 `SKILL.md` 与 `agents/openai.yaml`。
- `plugins/luna-agent-bridge/`：可选 Codex 插件清单及其桥接 Skill 入口。
- 根目录治理文件：`LICENSE`、`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`。
- `tests/test_release_layout.py`：校验发布结构、清单和遗留 Skill 的安全声明。

## 验收标准

1. Skill 和插件清单均通过官方脚本校验。
2. 原有 Python 测试全部通过。
3. 默认文档路径只推荐原生 Skill；桥接器必须显式 opt-in。
4. 仓库中不再有未标注的“外部桥接即原生 Luna”表述。
