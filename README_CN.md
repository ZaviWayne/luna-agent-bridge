# Luna Agent Bridge

[English](README.md) | 中文

默认使用 Codex 原生子 Agent，并可通过原生 `[agents]` 配置把适合的任务路由到 `gpt-5.6-luna`；只有明确需要跨会话持久化、恢复或接管时，才启用外部 Bridge。

## 为什么做这个项目

Codex 主 Agent 通常负责需求理解、方案判断和最终整合。代码审查、测试执行、资料整理、局部搜索等子任务边界更清晰，用户可能希望用更适合高频任务的模型配置，而不是让每个子任务都沿用主 Agent 的配置。

这个项目把模型路由中的两个概念明确分开：`gpt-5.6-luna` 是模型，`max` 是推理强度。默认路径由 Codex 原生 `[agents]` 配置这两个值；外部 Bridge 只在用户明确选择跨会话能力时，才把同一组配置传给 Codex CLI。用户仍需根据自己的任务、账号和运行环境测量成本、延迟与质量；项目不承诺固定比例的省钱效果，也不保证所有 Codex 运行环境都开放该模型。

可以把任务流理解为：

```text
主 Agent（负责规划、判断和整合）
├─ 复杂或高风险任务 ───────────────→ 主 Agent 使用的高能力模型
└─ 高频、边界清晰的子任务 ─────────→ gpt-5.6-luna + max
                                      └─ 可选：本地队列与跨会话恢复
```

## 选择哪条路径

| 需求 | 推荐路径 |
| --- | --- |
| 普通拆解、代码审查、测试或资料整理 | Codex 原生子 Agent + 本项目提供的 Skill |
| 希望指定 `gpt-5.6-luna` 和 `max` | Codex 原生子 Agent + `[agents]` 配置 |
| 需要跨 Codex 会话保存、恢复或接管任务 | 外部桥接器 |
| 只需要当前会话内的并发协作 | 优先使用 Codex 原生子 Agent |

原生子 Agent 由 Codex 运行环境负责调度，通常是最轻量的路径。外部桥接器是可选兼容层，不是 Codex 官方原生功能；它不能把原生子 Agent 的内部通道、侧边栏展示或生命周期承诺扩展到所有环境。

## 推荐路径：原生 Skill

这是普通任务拆解的默认入口。Skill 只提供拆解、并发、文件归属、消息交接和验证规则，不启动 Broker、不修改 PATH、不保存凭据，也不承诺跨会话持久化。

正式 Release 提供 `native-luna-subagents-skill-<版本号>.zip`。解压后将其中的 `native-luna-subagents` 目录放入用户级 Skill 目录即可；源码仓库也保留下面的直接复制方式。

将 Skill 复制到用户级 Skill 目录（Windows PowerShell）：

```powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex\skills' }
Copy-Item -Recurse -Force '.\packages\native-luna-subagents' (Join-Path $skillRoot 'native-luna-subagents')
```

macOS：

```bash
skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skill_root"
cp -R ./packages/native-luna-subagents "$skill_root/native-luna-subagents"
```

若运行环境支持用户级 Agent 配置，可以将模型和推理强度设为：

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 4
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "max"
```

安装 Skill、保存配置并重新打开 Codex 后，后续需要拆分的普通子任务默认使用 Codex 原生子 Agent；只有用户明确要求跨会话持久化、恢复或接管时，才启用外部 Bridge。

模型是否可用、子 Agent 是否显示在侧边栏，以及会话关闭后的生命周期，仍由 Codex 运行环境决定；本项目不把它们包装成持久化保证。

## 可选路径：外部桥接器

只有在用户明确要求跨 Codex 会话保存、恢复或接管任务时，才考虑安装外部桥接器。指定 `gpt-5.6-luna` + `max` 本身不是安装 Bridge 的理由。Bridge 支持 Windows、macOS 和 Python 3.12 或更高版本：

发布版本可直接从 PyPI 安装：

```powershell
python -m pip install luna-agent-bridge
luna-agent install
```

也可以从 [GitHub Releases](https://github.com/ZaviWayne/luna-agent-bridge/releases/latest) 下载 Windows 单文件 `luna-agent.exe`，无需配置 Python。下载后可用 `.\luna-agent.exe --help` 查看命令；首次使用外部桥接器前运行 `.\luna-agent.exe install`。

macOS 可以下载与当前架构匹配的 `luna-agent-macos-arm64` 或 `luna-agent-macos-x86_64`：

```bash
chmod +x ./luna-agent-macos-arm64
./luna-agent-macos-arm64 --help
./luna-agent-macos-arm64 install
```

安装命令会把可执行文件复制到 `~/Library/Application Support/CodexLunaAgent/bin/luna-agent`，并在 `~/.zprofile` 中添加受管 PATH 块。打开新终端后可直接运行 `luna-agent`；当前终端可先执行 `source ~/.zprofile`。

当前自动构建的 macOS 单文件使用 ad-hoc 签名，尚未接入 Apple Developer ID 公证。请先核对 Release 中的 SHA-256 校验值；从浏览器下载后若被 Gatekeeper 拦截，需要由用户在 macOS“隐私与安全性”中明确允许，项目不会自动绕过系统安全检查。

如果需要从源码开发或测试，再使用下面的可编辑安装方式：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
luna-agent install
```

激活成功后，当前 PowerShell 提示符会带有 `(.venv)`，后续可以直接使用 `luna-agent`。如果不希望激活虚拟环境，改用虚拟环境中的完整路径：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\luna-agent.exe install
```

如果 PowerShell 阻止执行 `Activate.ps1`，可以在当前窗口临时放宽策略后重试，或直接使用上面的完整路径方式：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

macOS 源码开发：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
luna-agent install
```

常用命令：

以下命令假设虚拟环境已经激活或安装目录已加入 PATH；Windows 未激活虚拟环境时，请将命令前缀替换为 `.\.venv\Scripts\luna-agent.exe`。

```console
luna-agent spawn --name reviewer --cwd <workspace-path> --task "检查当前修改"
luna-agent status <agent-id>
luna-agent send <agent-id> "补充检查边界条件"
luna-agent wait <agent-id> --timeout 300
luna-agent result <agent-id>
luna-agent interrupt <agent-id>
luna-agent archive <agent-id>
```

桥接器通过本地 Codex CLI 启动任务，并传递：

```text
--model gpt-5.6-luna
--config model_reasoning_effort="max"
```

Windows 本地状态默认保存到 `%LOCALAPPDATA%\CodexLunaAgent`，macOS 保存到 `~/Library/Application Support/CodexLunaAgent`，包括任务元数据、事件和恢复所需的队列状态。运行中的消息会排队到当前轮次边界，不能像原生内部通道一样即时注入模型生成过程。

用户准备关闭 Codex 时，必须先中断仍在运行的外部 Agent，再执行：

```console
luna-agent broker shutdown
```

不要假设关闭 Codex 会自动回收外部 Broker。普通卸载保留数据库；只有用户明确确认后才执行：

```console
luna-agent uninstall --purge-data --yes
```

## 能力边界

桥接器提供：

- 面向本地 Codex CLI 的显式模型与推理强度路由。
- SQLite 状态存储、任务事件、消息队列和恢复入口。
- 在工作区切换或重新打开 Codex 后，通过任务 ID 查询、发送、等待和接管。
- 最多 4 个本地 Worker，并在 Broker 关闭时停止其管理的进程。

桥接器不提供：

- Codex 官方原生子 Agent、官方侧边栏展示或官方生命周期保证。
- 绕过账号权限、模型可用性、沙箱或批准策略的能力。
- 固定的成本节省比例、固定延迟或跨账号的模型可用性承诺。
- 远程 TCP 控制；状态和控制面仅通过 Windows Named Pipe 或 macOS Unix Domain Socket 在本机工作。

## 插件入口

`plugins/luna-agent-bridge` 包含 `.codex-plugin/plugin.json` 和一个明确标注为“可选兼容层”的 Skill。它不会自动安装可执行文件、修改全局配置或添加个人 Marketplace 条目；请通过 Codex 的本地插件安装流程显式添加。

## 安全边界

- 不开放 TCP 远程控制。
- 不读取或保存 Codex 凭据。
- 不提供完全绕过沙箱的模式。
- Named Pipe、Unix Domain Socket、自动批准、用户数据目录和进程生命周期都属于外部桥接器的安全审查范围。
- 不要把外部桥接器或其跨会话恢复能力描述为 Codex 官方原生 Luna。

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

```bash
.venv/bin/python -m unittest discover -s tests -q
```

`tests/fixtures` 中的 JSONL 文件是确定性的 Codex CLI 响应样本，用于在不访问网络、不消耗模型调用额度的情况下覆盖解析、事件和恢复逻辑；它们是测试输入，不会被打包到运行时。

## 自动发布 GitHub Release 和 PyPI

仓库包含 Tag 触发的 `.github/workflows/release.yml`。首次使用前，在 PyPI 的 Trusted Publishers 设置中登记：

- Owner：`ZaviWayne`
- Repository：`luna-agent-bridge`
- Workflow：`.github/workflows/release.yml`
- GitHub Environment：`pypi`

之后，更新 `pyproject.toml` 版本并提交，再推送同版本 Tag：

```powershell
git tag v0.2.0
git push origin v0.2.0
```

Workflow 会从这个 Tag 构建 Windows EXE、macOS arm64/x86_64 单文件可执行程序、wheel、sdist、可选 Bridge 插件包、Bridge Skill 包、原生 Skill 包和校验文件，先创建 GitHub Release 草稿，再发布到 PyPI，最后公开 GitHub Release。Tag 与 `pyproject.toml` 版本不一致时会在发布前失败。不要移动已经公开的 Tag。

发布前请移除 `.venv`、`.venv-macos`、`build`、`dist`、`outputs`、`__pycache__` 和运行日志。Skill 与插件清单应通过对应的官方校验脚本。

项目采用 MIT License，详见 [LICENSE](LICENSE)。
