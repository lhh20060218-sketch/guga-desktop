# 咕嘎智能体与个人软件生态

## 产品目标

用户开启长语音，说“咕嘎，打开我授权的软件”，咕嘎调用真实工具、收到结果、报告结果，然后继续听。文字和语音共享会话、项目、权限与执行器。日常任务授权后直接执行；删除、对外发送等动作在工具边界确认。

## 本版使用

1. 退出旧桌宠，重新启动。右键 → **对话 · 咕嘎智能体**。
2. 左侧新建项目、新对话；右键条目或双击更名，右键会话可移动、归档、恢复。数据本地保存，重启后保留。
3. 右上 **软件权限** → 选择可信软件的 `.exe` 或 `.lnk`，设置平时叫它的名称。该授权只允许打开，不自动授予软件内部控制。
4. 点击 **语音对话**，或者右键 **长语音 · 边聊边执行**，连接阿里 `qwen-audio-3.1-realtime-plus`。阿里负责持续收音、轮次判断、语气和实时语音播报；问题与任务通过原生 Function Calling 交给 DeepSeek。文字也可以在同一窗口发送。
5. 示例：“列出我授权的软件，再打开记事本”“把自己挪到右下角”“建一个学习项目”“先自己问自己这个方案哪里有问题，再告诉我”。
6. **打断**中断当前播报/语音任务但继续通话；**静音**暂停麦克风输入；**停止**取消后续工具并停止语音。右上 **关闭** 或 Esc 关闭对话窗、结束语音，桌宠继续运行。已经完成的操作保留。网络中已有请求最多等待本次网络超时，迟到响应不会继续执行工具。

长语音沿用已有阿里配置、音色、免费额度保护和持续通话机制，不再通过本地 Vosk + Edge 串联。阿里通过 `ask_deepseek` 将完整问题/任务交给当前聊天模型 `deepseek-v4.1-flash`，DeepSeek 可调用既有权限工具，结果通过 `function_call_output` 返回阿里，再触发阿里的原生音频回复。问候和简单附和由阿里直接完成，实质问答与任务按系统指令转交 DeepSeek。文字聊天的可选朗读仍使用原 Edge TTS。

耳机模式沿用服务端语音打断；外放模式在生成和播放期间抑制麦克风输入以避免回声，可点击 **打断**。当前没有软件声学回声消除。语音或按钮打断会取消尚未完成的 DeepSeek 后续操作；关闭、断线或重连时丢弃旧调用的迟到结果。原生工具事件按 `call_id` 去重，转录文本只用于显示/上下文，不会额外触发一次执行。开启语音时带入当前会话的近期文字上下文；通话期间先结束通话再切换会话。

## 结构与权限

```text
文字 ──────────────────────────┐
阿里端到端长语音 → ask_deepseek ─┤
                               ↓
                     同一个会话与 DeepSeek 智能体
       ↓
工具循环（单轮最多 6 轮模型请求、12 次工具操作、自问一次）
       ├─ 软件自身执行器 → Qt 主线程 → 桌宠、窗口、会话、项目
       ├─ 软件启动授权表 → Windows 启动请求
       └─ MCP Host → 已启用的软件服务 → 已授权的工具
       ↓
操作记录 / 真实返回值 → DeepSeek 答复 → function_call_output → 阿里原生语音回复

外部 MCP Host → 咕嘎 stdio MCP Server → 同用户本地管道 → 同一个自身执行器
```

模型没有任意 shell、修改源码或自行增加权限的入口。软件授权只能由用户在界面添加；MCP 授权通过用户维护的本地配置。MCP 不自动提供管理员权限。已注册的自身能力包含位置、显示隐藏、透明度、置顶、音量、互动/动画、Bongo 面板、既有战棋窗口、项目/会话管理。其他功能后续继续注册工具，不宣称已经覆盖应用全部功能。

工具结果在聊天中默认折叠，可展开查看。没有把 API Key 写入聊天数据库或 MCP 输出。数据保存在 `runtime/chat/`，已加入 Git 忽略；旧迷你输入条历史没有自动导入。

单轮在模型请求之间检查 90 秒预算，请求连接/读取分别上限 5/35 秒，因此进行中的网络请求可能越过运行预算；每次 MCP 请求上限 20 秒，确认框最多等待 30 秒。任务不自动无限递归。自问副本无工具，只返回分析。

## 给自己做的软件接入 MCP

你的软件实现标准 MCP `initialize`、`tools/list`、`tools/call`。提供清晰的参数和真实结果，例如 `get_status`、`create_note`、`delete_note`。咕嘎当前实现 **stdio tools 子集**，支持 `2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05` 的初始化协商；不宣称支持完整协议、HTTP 传输、2026 新协议、resources 或 prompts。

复制根目录 `mcp_servers.example.json` 为 `mcp_servers.json`，替换为自己的程序路径并明确启用：

```json
{
  "mcpServers": {
    "my-notes": {
      "enabled": true,
      "command": "C:/Python/python.exe",
      "args": ["C:/my-notes/mcp_server.py"],
      "allowed_tools": ["get_status", "create_note", "delete_note", "send_message"],
      "routine_tools": ["get_status", "create_note"],
      "confirmation_tools": ["delete_note", "send_message"]
    }
  }
}
```

`allowed_tools` 是总授权范围，`routine_tools` 是允许直接执行的常规操作。其他已授权工具，以及 `confirmation_tools` 中的工具，调用前弹出本次确认。请把删除、对外发送等工具留在确认范围，不能因服务器自报“安全”就放行。模型不能修改这份配置。未确认、超时或取消都不调用目标工具。

对咕嘎说：“查看接入了哪些软件，列出 my-notes 的工具，帮我创建一条笔记。”目前每次生态调用建立一个有限生命周期的 stdio 子进程，结束后关闭；适合使用已有应用服务或持久数据库的桥接程序，不依赖 MCP 子进程内存长期保存状态。

## 让其他 MCP Host 控制咕嘎

保持桌宠运行，将以下服务器条目加入目标 Host 的 MCP 配置（替换成本机绝对路径）：

```json
{
  "mcpServers": {
    "guga": {
      "command": "C:/Python/python.exe",
      "args": ["C:/guga-penguin-pet/tools/guga_mcp_server.py"]
    }
  }
}
```

暴露 `app_state`、`pet_control`、`workspace`、`applications`。stdio 仅输出协议消息；通过仅当前 Windows 用户可访问的本地命名管道到达 Qt，未开公网端口。外部工具调用同样执行软件授权检查。咕嘎的工具循环与 MCP Server 共享执行器，而不是让模型模拟点击自己的界面。

## 验证与边界

- `python tools/test_agent_workspace.py`：存储与隔离、归档恢复、工具反馈、自问上限、取消后无后续操作、MCP 握手、软件授权/撤销、权限确认边界。
- `python tools/smoke_agent_ui.py`：离屏 Qt 窗口、实际桌宠移动、项目创建、记录展示、真实 stdio/命名管道/Qt 往返；不联网、不录音、不朗读。
- `python tools/test_ai_go.py`：原 Go 模型路由回归。
- `python tools/test_realtime_voice.py`：原阿里持续语音回归；`python tools/test_realtime_agent.py`：双模型配置、工具事件去重、返回顺序、打断与关闭后拒绝迟到结果。
- 对话窗集成检查同时覆盖默认语音入口确实创建阿里端到端引擎、DeepSeek 答复返回阿里而非 Edge、关闭按钮/Esc 停止通话但保留桌宠。
- `python tools/probe_realtime_agent.py`：一次有限的真实阿里 → DeepSeek → 阿里语音链路测试，使用通用计算问题，不使用麦克风或扬声器。2026-10-19 实测双模型链路完成，返回 130560 字节音频，约 4.3 秒；这是文本输入协议测试，不是实际麦克风往返延迟。
- 开发时已用现有模型配置完成最小联网验证：真实模型返回 `app_state` 工具调用，反馈后正常完成。仅发送通用协议测试文本和测试状态，不发送真实会话。
- 尚需用户现场验收麦克风识别、实际听感和授权软件启动。软件启动返回“Windows 已接受请求”，不冒称已经看见软件窗口或完成其内部任务。

协议依据：[MCP 生命周期](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)、[MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)、[stdio 传输](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)。
