# Luna Agent Bridge

这是一个 Windows/Python 本地项目，包含两个明确分离的交付物：

1. `packages/native-luna-subagents`：推荐的 Codex 原生 Luna 子 Agent Skill。
2. `plugins/luna-agent-bridge`：用户明确选择后才使用的外部桥接插件。

外部桥接器不是 Codex 官方原生功能。它可以通过本地 Codex CLI、Windows Named Pipe 和 SQLite 提供任务消息排队、跨会话接管和显式恢复；这些能力不属于原生 Skill 的承诺范围。

## 推荐路径：原生 Skill

普通的任务拆解、代码审查、测试和资料整理应使用 Codex 原生子 Agent。Skill 只提供拆解、并发、文件归属、消息交接和验证规则，不启动 Broker、不修改 PATH、不保存凭据，也不承诺跨会话持久化。

将 Skill 复制到用户级 Skill 目录（Windows PowerShell）：

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex\skills' }
Copy-Item -Recurse -Force '.\packages\native-luna-subagents' (Join-Path $skillRoot 'native-luna-subagents')
```

若运行环境支持用户级 Agent 配置，可以将模型和推理强度设为：

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "max"
```

模型是否可用、子 Agent 是否显示在侧边栏，以及会话关闭后的生命周期，仍由 Codex 运行环境决定；本项目不把它们包装成持久化保证。

## 可选路径：外部桥接器

只有在用户明确要求跨 Codex 会话保存、恢复或接管任务时，才考虑安装外部桥接器。它要求 Windows 和 Python 3.12 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
luna-agent install
```

常用命令：

```powershell
luna-agent spawn --name reviewer --cwd <workspace-path> --task "检查当前修改"
luna-agent status <agent-id>
luna-agent send <agent-id> "补充检查边界条件"
luna-agent wait <agent-id> --timeout 300
luna-agent result <agent-id>
luna-agent interrupt <agent-id>
luna-agent archive <agent-id>
```

外部桥接器默认将状态保存到 `%LOCALAPPDATA%\CodexLunaAgent`。运行中的消息会排队到当前轮次边界，不能像原生内部通道一样即时注入模型生成过程。

用户准备关闭 Codex 时，必须先中断仍在运行的外部 Agent，再执行：

```powershell
luna-agent broker shutdown
```

不要假设关闭 Codex 会自动回收外部 Broker。普通卸载保留数据库；只有用户明确确认后才执行：

```powershell
luna-agent uninstall --purge-data --yes
```

## 插件入口

`plugins/luna-agent-bridge` 包含 `.codex-plugin/plugin.json` 和一个明确标注为“可选兼容层”的 Skill。它不会自动安装可执行文件、修改全局配置或添加个人 Marketplace 条目；请通过 Codex 的本地插件安装流程显式添加。

## 安全边界

- 不开放 TCP 远程控制。
- 不读取或保存 Codex 凭据。
- 不提供完全绕过沙箱的模式。
- Named Pipe、自动批准、用户数据目录和进程生命周期都属于外部桥接器的安全审查范围。
- 不要把外部桥接器或其跨会话恢复能力描述为 Codex 官方原生 Luna。

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

发布前请移除 `.venv`、`build`、`dist`、`outputs`、`__pycache__` 和运行日志。Skill 与插件清单应通过对应的官方校验脚本。

项目采用 MIT License，详见 [LICENSE](LICENSE)。
