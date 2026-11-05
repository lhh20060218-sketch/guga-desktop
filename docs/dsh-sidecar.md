# DSH sidecar 接入

2026-11-02 更新：现在非快捷执行任务默认交给 DSH，不再只由 SelfAgent 偶尔选用。MCP 工具桥、长期记忆、任务续接和回滚详见 [个人智能体升级](dsh-personal-upgrade-20261102.md)。以下保留底层协议说明。

咕嘎把长任务交给独立 `dsh` 进程，避免让两套 Agent 在同一个 Qt 进程里争抢会话、麦克风和工具状态。咕嘎外壳负责声音、权限、气泡、停止和汇报，DSH 负责长时多阶段执行。

2026-11-02 已在本机验证 `0.2.1-rc.5`。咕嘎会把自己的 `ai_config.json` 中 `OPENCODE_GO_API_KEY` 注入 sidecar，开发态和打包态都一致；不要再依赖 DSH 自己保存的过期 Key。旧版本可通过 `tools/rollback_dsh.ps1` 回到 `0.1.7-rc.2`。

## 前置条件

- 安装 `dsh`，确保 `dsh --version` 可运行。
- 通过 DSH 自己的配置或登录设置模型凭据。
- 用以下命令确认事件协议可用：

```powershell
@'
回答一个词：READY
'@ | dsh --profile headless --json -
```

正常输出至少包含 `session`、`status` 和 `final` NDJSON 事件。若出现 AUTH/401，需要先在 DSH 侧更换有效凭据。

## 从咕嘎调用

对咕嘎说：“这个任务很复杂，交给 DSH 长任务执行器，完成后告诉我。”模型会调用 `dsh_task(action=start, task=..., seconds=...)`。`start` 返回只代表子进程已受理，不代表任务完成；后续进度和结果通过节点事件流回到原会话、气泡和长语音。

支持：

- `start`：启动 headless sidecar，默认最多 900 秒。
- `status`：查看运行状态和最近事件。
- `stop`：终止 DSH 进程树。
- `session_id`：继续一个已有 DSH session。
- `cwd`：指定已存在的工作目录。

## 事件映射

- `session`：记录 DSH session ID。
- `status/turn_start/step_start`：节流后显示进度，避免每步都发语音。
- `tool_call/tool_result`：新版会在 NDJSON 里报告工具名称和真实结果；当前咕嘎保留完整事件供记录，后续应只展示工具名、状态和可核对摘要，不展示密钥或完整输出。
- `text/thinking/final`：最终文本以 `final` 为准；thinking 只作诊断，不应作为完成证据或向用户暴露隐藏推理。
- `dsh_completed`：仅按 DSH 最终事件和退出码确定成功/失败。
- stderr 只保存为错误摘要，不朗读密钥或完整响应体。

DSH 是独立进程，拥有自己的工具、权限和工作区；它不会自动获得咕嘎语音调用或战棋控制。需要共享能力时通过 MCP、CLI 或明确的文件/事件协议连接。
