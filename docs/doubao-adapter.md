# 豆包适配器（Doubao Adapter）

让咕嘎把文本任务真的交给豆包桌面端完成，并把正文抓回。**正文只可能来自豆包窗口**，
任何失败都明确报失败码，绝不用咕嘎自己的模型代写、也不给模型输出贴“来自豆包”的标签。

- 实现：`core/adapters/doubao_adapter.py`
- 声明（他人维护，本适配器只读取、不修改）：`core/adapters/apps/doubao.json`（`schema: guga.app_adapter/1`）
- MCP 配置：`core/adapters/doubao_mcp.json`，或环境变量 `GUGA_DOUBAO_MCP_URL`
- 抓取证据：`runtime/doubao_evidence/<call_id>/attemptN/`（`runtime/` 已被 .gitignore 忽略）

## 1. 通道顺序

| 顺序 | 通道 | 条件 | 界面标注 |
| --- | --- | --- | --- |
| 1 | `mcp` | `doubao_mcp.json` 里 `enabled=true` 且端点可达，或设置了 `GUGA_DOUBAO_MCP_URL` | `豆包（接口调用）` |
| 2 | `ui_automation` | MCP 不可用（未配置 / 端点不通 / 无文本工具） | `豆包（界面自动化，非接口调用）` |

`notice` 字段会写明为什么没走接口，例如：

> 未走接口：豆包桌面端没有对外 MCP Server（其“连接器”是让豆包调用外部 MCP），
> 本次走的是界面自动化，不是接口调用。

### 关于豆包“连接器 / 个人 MCP”的实测结论

- 入口：豆包 → `插件·技能·工作台` → 插件 → 添加 → 新建自定义连接器。
- 形态：云端创建（接口 `AGWManageCreatePersonalConnector`），支持 `stdio/http/sse`。
- 方向：**客户端方向**，即“豆包去调用外部 MCP Server”，供豆包扩展能力。
- 本机没有豆包暴露给第三方的 MCP Server：没有 `mcpServers` 配置文件、没有监听端口。
- 因此 `guga → 豆包` 的 MCP 调用默认不可用；`McpChannel.probe()` 会如实返回
  `not_configured` 或 `unreachable`，不会假装可用。

如果将来拿到可调用的豆包文本端点，在 `core/adapters/doubao_mcp.json` 填：

```json
{
  "enabled": true,
  "transport": "http",
  "endpoint": "http://127.0.0.1:PORT/mcp",
  "server_name": "doubao",
  "tool": "chat",
  "prompt_argument": "prompt",
  "call_timeout_seconds": 60
}
```

或临时用环境变量覆盖（会强制启用 HTTP 通道）：

```powershell
$env:GUGA_DOUBAO_MCP_URL = "http://127.0.0.1:PORT/mcp"
```

stdio 形态则配置 `transport: "stdio"`、`command`、`args`、`env`、`cwd`，按行分隔的 JSON-RPC。

## 2. 调用方式（接入说明，不改受限文件）

`core/tool_router.py`、`core/local_tools.py`、`ui/first_run.py`、`ui/sprite_animator.py`
由其它部门维护，本适配器不改它们，接入时按下面任一方式挂载：

```python
from core.adapters.doubao_adapter import DoubaoAdapter, ask_doubao

# 常驻实例（复用窗口、保留 MCP 连接）
doubao = DoubaoAdapter()

result = doubao.ask(
    "用豆包写一篇 200 字作文",
    timeout_seconds=150,
    retry=1,          # 失败自动重试一次
    prefer_mcp=True,  # 先试 MCP，再回落界面自动化
)
```

```python
# 一次性调用
result = ask_doubao("用豆包写一篇 200 字作文")
```

把 `apps/doubao.json` 的 `adapter` 字段指向本模块即可（该字段目前为 `""`，由声明维护方填写）：

```json
"adapter": "core.adapters.doubao_adapter:DoubaoAdapter"
```

命令行自测：

```powershell
python -m core.adapters.doubao_adapter --probe
python -m core.adapters.doubao_adapter --prompt "用豆包写一篇200字作文" --timeout 150 --json
python -m core.adapters.doubao_adapter --prompt "..." --no-mcp   # 强制走界面自动化
```

## 3. 返回契约

成功：

```json
{
  "ok": true,
  "channel": "ui_automation",
  "text": "……豆包生成的正文……",
  "source": {
    "tool": "doubao",
    "label": "豆包（界面自动化，非接口调用）",
    "call_id": "doubao-20261107235007-8c9e",
    "started_at": "2026-11-07T23:50:07.554",
    "duration_ms": 34653,
    "provenance": "clipboard:312c9b73…"
  },
  "evidence": {
    "dir": "runtime/doubao_evidence/doubao-…/attempt1",
    "window": {"hwnd": 5113140, "pid": 33696, "title": "豆包", "...": "..."},
    "page_sha256": "2d9df0f5…",
    "capture_sha256": "312c9b73…",
    "copied_from": "answer_button",
    "visible_in_page": {"ratio": 0.883, "windows": 7},
    "local_model_used": false,
    "origin": "doubao_desktop_window",
    "screenshots": ["01_window.png", "07_sent_1.png", "09_before_copy.png", "..."]
  },
  "notice": "未走接口：……本次走的是界面自动化，不是接口调用。",
  "elapsed_ms": 34653
}
```

失败：

```json
{
  "ok": false,
  "code": "window_not_found",
  "hint": "没有找到豆包窗口；请确认已安装豆包桌面端。",
  "message": "没能调起豆包完成这次任务；不会用咕嘎自己的模型代写。",
  "text": "",
  "attempts": [{"code": "...", "hint": "...", "timeline": ["..."]}]
}
```

界面层必须原样展示 `source.label` 或 `notice`；失败时展示 `message` + `hint`，
**不得**在 `ok=false` 时把任何其它模型的内容当作豆包结果返回。

### 失败码

| code | 含义 | 自动处理 | 用户动作 |
| --- | --- | --- | --- |
| `window_not_found` | 窗口不存在且启动失败 | 自动启动 exe + `doubaoapp://chat` 拉起 | 确认已安装 / 手动打开豆包 |
| `not_installed` | 找不到 exe，也没有 `doubaoapp://` 协议 | 立即失败，不空等 | 先安装豆包桌面端并登录 |
| `launch_failed` | 已安装但 exe/协议都没拉出窗口 | 两轮唤起后失败 | 手动启动一次，确认能打开并登录 |
| `window_blank` | 窗口在但内容白屏 | 用协议重新唤起一次 | 仍白屏则 `Ctrl+R` 或重启豆包 |
| `window_lost` | 运行中窗口消失 | 重试一次（会重新拉起） | 无需操作 |
| `blocked_by_window` | 目标坐标被别的窗口压着、置顶失败 | 自动置顶重试 3 次 | 关掉遮挡窗口 |
| `blocked_by_dialog` | 页面内弹窗挡住输入/复制 | 按 OCR 锚点自动点关闭/确定 | 仍失败则手动关闭弹窗 |
| `login_required` | 未登录 / 扫码页 | 不自动越权 | 见第 5 节 |
| `input_not_found` | 找不到输入框 | 重试整轮 | 确认已登录、窗口完全加载 |
| `readback_mismatch` | 粘贴后回读不一致 | 清空重注最多 3 次 | 无需操作 |
| `send_not_confirmed` | 回车后页面没有增长 | 仍在输入框时补一次回车 | 无需操作 |
| `generate_not_started` | 有页面变化但没进入生成 | 重试一次 | 无需操作 |
| `timeout` | 限定时间内没有稳定回复 | 只补抓、不重发 | 检查网络 |
| `capture_empty` | 有回复但复制/校验失败 | 只补抓、不重发 | 手动点回答下方“复制”后重试 |

重试规则：`retry=1` 时最多两轮。若上一轮**已确认发出**（`evidence.send.ok=true`）
且失败码是 `timeout`/`capture_empty`，第二轮只补抓，不会重复发问。

## 4. 来源可信证明（防“看起来调用了”）

每次成功都会落盘以下证据，可回放：

1. **窗口身份**：`hwnd / pid / title / class / rect`，进程名在 `process_names` 内。
2. **过程截图**：打开、恢复白屏、新对话、注入前后、发送后、抓取前各一张，均在 `evidence.dir`。
3. **页面 OCR 哈希**：`page_sha256`，来自当前窗口的实时截图。
4. **剪贴板哈希**：`capture_sha256`，`10_clipboard.txt` 保存原始剪贴板，`11_answer.txt` 保存正文。
5. **交叉校验**：正文按字符与同一时刻的窗口 OCR 比对，记录 `visible_in_page.ratio`（≥0.6）
   与连续 8 字窗口命中数（≥2）才放行。实测一次为 `ratio=0.883, windows=7`。
6. **来源标记**：`local_model_used=false`、`origin="doubao_desktop_window"`、
   `copied_from="answer_button"`（点击的是豆包回答下方自带的“复制”按钮）。
7. **时间线**：`attempts[].timeline` 记录每一步的时间戳、字符数、是否在生成。

正文抓取方式：点击回答操作行左侧的“复制”按钮（OCR 用“免”字或“今天 HH:MM”作锚点定位）。
**不用 Ctrl+A**：豆包对话区点击会把焦点交回输入框，Ctrl+A 只能选中空输入框；
也不点回答下方的推荐问题，点了会触发第二轮生成、污染结果。

## 5. 状态处理与恢复

### 自动拉起（默认行为）

用户点名豆包时，如果豆包没在运行，适配器会**自动拉起**：先启动已安装的
`Doubao.exe`，再用 `doubaoapp://chat` 唤起对话窗口；已有窗口只复用，不会重复拉起。
演示话术可以直说“你点了豆包，我就把它打开”，不会出现“说调用了、窗口却没出现”。

### 未安装

`probe()` 返回 `installed=false`；`ask()` 立即返回 `not_installed` +
“没装豆包：请先安装豆包桌面端……”。安装地址：<https://www.doubao.com/download/desktop>。
不会空等 30 秒启动超时。

### 已安装但打不开

exe 存在或协议已注册，但两轮唤起后仍没有可用窗口，返回 `launch_failed` +
“装了豆包但没能打开窗口：请手动启动一次，确认能打开并登录后再派”。

### 未登录 / 首次引导页

适配器能识别（整页出现“登录 / 扫码 / 验证码 / 同意并继续 / Sign in”，且找不到输入框），
返回 `login_required`，并在 `hint` 里给出可执行步骤。**不会尝试绕过登录**。

恢复步骤（人工一次，之后自动化可继续）：

1. 打开豆包窗口（咕嘎已经帮你拉到前台）。
2. 按提示扫码或手机号登录，勾选同意协议。
3. 登录完成后停在主对话页（能看到“发消息…”输入框）。
4. 不需要重启咕嘎：下一轮 `ask()` 会重新探测输入框，随后自动注入、发送、抓取。

> 说明：登录态属于账号凭据，适配器不读取、不保存、不代替用户登录。
> 本轮验证没有执行“退出登录”，因为会破坏当前用户会话；这条恢复路径由
> `_ui_attempt` 的状态机保证：只要输入框出现，同一轮调用就会继续往下走。

### 白屏 / 窗口被遮挡

- 白屏：用 `doubaoapp://chat` 再唤起一次（实测可恢复渲染），仍白屏返回可执行提示。
- 遮挡：截图优先用 `PrintWindow`；豆包（Chromium）内容区不自绘，因此退化为
  “`HWND_TOPMOST` 置顶 + 区域截图”，点击前用 `WindowFromPoint` 校验该坐标确实属于豆包，
  被别的窗口占着就自动重试置顶，仍不行返回 `blocked_by_window`，绝不盲点。
- 运行结束会撤销置顶，不长期占用前台。

### 进程偶发退出（本机实测）

豆包 2.35.8 在本机偶发 `app_crashed`（0 字节崩溃转储）并在 1–2 分钟后退出。
适配器以 `--disable-gpu --disable-gpu-compositing` 启动（`GUGA_DOUBAO_GPU=on` 可关闭该行为），
并在每轮开始时复用已有窗口；窗口丢失会重新拉起一次。

## 6. 实测记录（2026-11-07）

成功样例：`call_id=doubao-20261107235007-8c9e`

| 项 | 值 |
| --- | --- |
| 通道 | `ui_automation`（MCP `not_configured`，已在 `notice` 标注） |
| 总耗时 | 34,653 ms（启动+恢复白屏+注入+发送+生成+抓取） |
| 正文 | 206 字，两段，`11_answer.txt` 可查 |
| 复制方式 | `answer_button` |
| 剪贴板 SHA-256 | `312c9b73184c8d1230ba6594e42b27be286a857d6e0104313650c772680f0f9b` |
| 页面 OCR SHA-256 | `2d9df0f532168340b503da21c2303592025e11af7f3c5763d2bf8b6fc833370c` |
| 交叉校验 | `ratio=0.883`，连续 8 字窗口命中 `7` 个 |
| 本地模型参与 | `false` |

时间线要点：`23:50:09` 找到窗口 → `23:50:11` 检测到白屏 → `23:50:14` 协议恢复成功 →
`23:50:18` 新对话 → `23:50:23` 注入回读一致（42 字）→ `23:50:28` 发送确认 →
`23:50:30~40` 生成并稳定（311→405 字）→ `23:50:42` 复制并校验通过。

失败路径实测：

- 未安装（模拟 `_resolve_exe=None` 且无窗口）：`ok=false, code=window_not_found`，
  `text=""`，`message` 明确写“不会用咕嘎自己的模型代写”。
- MCP 端点不可达（`GUGA_DOUBAO_MCP_URL=http://127.0.0.1:9/mcp`）：
  `{"available": false, "reason": "unreachable", "detail": "<urlopen error timed out>"}`，
  随后回落到界面自动化并标注 `notice`。
- 其它窗口（WorkBuddy、咕嘎自检弹窗）压住豆包：已复现，旧实现会把别人的界面 OCR 进来；
  现实现用置顶 + 区域截图 + 点击归属校验处理，本轮成功样例未再出现串窗。

## 7. 已知限制

- 豆包桌面端无对外 MCP Server，当前只有界面自动化一条真实可用通道。
- 界面自动化依赖中文 OCR 锚点和固定布局比例；豆包大版本改版后需要更新锚点
  （锚点语义与 `apps/doubao.json` 的 `anchors.input/send/done` 保持一致）。
- 登录态无法自动建立，首次必须人工登录一次。
