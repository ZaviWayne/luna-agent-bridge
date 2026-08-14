# 贡献指南

感谢参与 Luna Agent Bridge。项目包含两个有意分离的发布面：

- `packages/native-luna-subagents`：只指导 Codex 原生子 Agent 的 Skill。
- `plugins/luna-agent-bridge`：用户主动选择的 Windows 外部桥接插件。

## 开发约束

1. 不把外部 Broker、SQLite 持久化或 `luna-agent` CLI 描述为 Codex 原生能力。
2. 原生 Skill 不得启动后台进程、修改 PATH、保存凭据或绕过沙箱。
3. 外部桥接器的进程、Named Pipe、自动批准和数据目录变更必须补充测试和安全说明。
4. 修改 Python 代码后运行：

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -q
   ```

5. 使用 `pip install -e ".[dev]"` 安装 `PyYAML` 后，修改 Skill 或插件清单时运行对应的官方校验脚本。

## 提交内容

提交说明应包含变更范围、测试命令和已知风险。不要提交 `.venv`、`build`、`dist`、`outputs`、`__pycache__` 或运行日志。
