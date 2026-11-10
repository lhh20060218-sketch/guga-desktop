# MCP 负责发现，界面自动化负责指挥

> 一句话：**MCP 让咕嘎知道"这台机器上有哪些软件、装在哪"，界面自动化负责"让它们干活"。**
> 两者不是替代关系，是两个不同的活。

## 为什么这样分工（给非技术评委）

你可以把咕嘎想成一个刚进公司的包工头。

- **发现**＝认人和记工位。它得知道这台电脑上到底装了哪些能干活的 AI 软件、各自在哪个目录。这件事靠 MCP：软件自己连上咕嘎时调 `report_app` 报一句"我叫什么、我的 exe 绝对路径在哪、我是什么版本、我会干什么"，咕嘎就不用满硬盘猜。
- **指挥**＝走到工位前把活交代清楚。软件没有"接单接口"，咕嘎只能像人一样：切到它的窗口、把话打进输入框、回车、盯着它干完、把结果抄回来。

把指挥也交给 MCP，等于要求每家公司都对外开放一个"接单窗口"——三家都不提供，所以这条路在协议层就不成立（下面第三节）。

## 一、两件事必须分开

| | 发现（Discovery） | 指挥（Command） |
| --- | --- | --- |
| 目的 | 这台机器上有哪些可用软件、装在哪、能力是什么 | 让某个软件真正执行任务、拿回结果 |
| 手段 | **MCP**：软件作为 client 连上咕嘎的 server，调 `report_app` 自报 exe 绝对路径 | **界面自动化**：视觉定位 + UIA + 键鼠 + 剪贴板 |
| 代码 | `core/adapters/guga_mcp_server.py`、`core/adapters/app_reports.py`、`core/adapters/app_registry.py` | `agent/guga_executor.py`、`core/adapters/apps/*.json` 的锚点与失败码 |
| 产出 | `app_reports.json`（name / exe_path / version / capabilities） | 产物落盘 + 界面回执 + 来源标注 |

MCP 连接记录由连上来的那一端自己写（`guga_mcp_server.py:_record_connection`），`report_app` 再把 exe 绝对路径写进 `%LOCALAPPDATA%\GUGA\app_reports.json`。**以后启动直接用这条路径，不需要猜盘符。**

## 二、发现为什么不能只靠猜路径

用户装软件的方式不可能穷举：绿色版、装到 D 盘、自己改目录名、便携解压、多版本共存。只靠一份"常见路径清单"必然漏。

现有探测是一条**逐级兜底**链（`core/adapters/app_registry.py` 的 `probe()`）：

1. 用户显式指定的路径（最可靠，绿色版/异盘）
2. **MCP 自报路径**（`report_app` 写入 `app_reports.json`，绝对路径 + 存在性校验）
3. 环境变量（如 `GUGA_JOYCODE_LAUNCHER`）
4. 声明里的常见安装路径（纯文件系统 `stat`，最快）
5. 注册表卸载项 / `App Paths`
6. 开始菜单与桌面快捷方式
7. 系统 `PATH`
8. 正在运行的进程（窗口标题 + 进程名反查）
9. 绿色版/自定义目录扫描（仅在前面的来源全没命中时兜底）

前面这些探测能覆盖大多数机器，但第 3～9 级**都是"猜"，不是"知道"**。MCP 自报的价值就在这里：软件自己报上来，咕嘎不用猜；自报路径失效时只记原因并回退到第 3 级，不阻断启动。

## 三、为什么"指挥"不换成 MCP

**方向不对。** MCP 有 server / client 两个角色。咕嘎做的是 **server**：打包后的 `GUGA-Desktop.exe --guga-mcp` 起一个 stdio MCP server。按新口径，它对外的主工具是"自报安装位置"：

| 工具 | 作用 | 口径 |
| --- | --- | --- |
| `report_app` | 软件自报名称、exe 绝对路径、版本、能力，咕嘎落盘成本机注册表 | **发现**，当前主用途 |
| `get_task` / `report_progress` / `submit_artifact` / `ask_guga` | 历史任务总线工具（领任务、报进度、交产物、提问） | **不属于"发现"，也不作为推荐派单方式**；正在按"只发现、不指挥"收敛 |

被适配的三个软件，声明里方向统一是 `guga_server`（见 `core/adapters/apps/*.json` 的 `channel` 块）：**它们都是 client，只连别人的 server，不对外提供 server。**

实测也印证了：写入配置并重启后，WorkBuddy 的工具清单里能看到连接成功（23:57:46），JoyCode 出现 `Connection established`（23:58:02）。**这条连接当前用于让软件自报路径，不用来领任务；派活仍走界面自动化。** 三家都没有对外暴露"执行任务"的 MCP 端点。

| 软件 | MCP 注册方式 | 能否被咕嘎用 MCP 指挥 | 实际指挥方式 |
| --- | --- | --- | --- |
| WorkBuddy | 文件 `%USERPROFILE%\.workbuddy\mcp.json` | 否 | 界面：切窗 → 填输入框 → 回车 → 抓回答 |
| JoyCode | 文件 `{workspace}/.joycode/mcp.json` | 否 | 界面/工作区：输入 → 触发 → 读 `.guga/outbox` 回执 |
| 豆包 | **界面**：登录后在"个人 MCP 连接器"新建（无本地文件） | 否 | 界面：自动拉起 → 填输入框 → 复制回答 |

豆包是最典型的一家：**既没有对外的 MCP server，也没有可用的 API**（声明里 `verified.level = unsupported_file_registration`，创建连接器还要登录后走云端接口 `AGWManageCreatePersonalConnector`）。它只能靠界面操作。

代码层面也一致：

- `core/workbuddy_bridge.py:1188` 的 `ask()` 直接走 `capture(prompt, timeout)`（界面抓取），没有 MCP 执行分支；
- `core/adapters/joycode_adapter.py:1028` 的 `ask()` 走 `run_task()`（界面触发 + outbox 回执），`prefer_mcp` 参数保留但未接执行路径；
- `core/adapters/doubao_adapter.py:452` 的 `ask()` 有 MCP 优先分支，但它需要显式配置一个外部豆包 MCP 端点（`doubao_mcp.json` / `GUGA_DOUBAO_MCP_URL`），默认返回 `mcp_unavailable`，然后回落到界面。

所以现状是：声明里的 `channel` 块只记录各软件的接入方式与状态，**不等于指挥通道**；真正能跑的仍是界面自动化。MCP 只用于发现，不用于派单。

## 四、路径优先级（设计口径）

```
用户手动指定  >  MCP 自报 exe 绝对路径（report_app）  >  声明清单与自动探测兜底
```

- **用户手动指定**最优先：用户说"我装在这里"，就听用户的。
- **MCP 自报**第二：软件连上来时自己报 exe 绝对路径、版本、能力，比任何启发式都准。
- **声明清单 + 注册表 + 开始菜单 + 常见目录 + PATH + 进程反查**做兜底：用户没指定、软件也还没连过时用。

> 如实说明：第 ② 级已经落在 `core/adapters/app_registry.py` 的 `probe()` 里（`source=mcp_report`，读 `app_reports.json`，失效自动回退并记 `mcp_report_invalid`）；但豆包/WorkBuddy/JoyCode 三个适配器目前仍各自扫描路径，尚未全部消费自报记录，属于实现中，**以代码为准**。

## 五、三家实测与已知边界

数据一律取自仓库内留档（`docs/demo/evidence/`），可用 SHA256 核对：

| 软件 | 结果 | 耗时 | 来源 |
| --- | --- | --- | --- |
| WorkBuddy | `answer_chars=174` | `elapsed_ms=54860`（54.9 秒） | `20261108-workbuddy-inpackage/package.json` |
| 豆包 | `text` 122 字 | 约 31 秒（`open_window` 06:08:39.272 → `capture_verify` 06:09:10.319） | `20261108-doubao-autolaunch/result.json` |
| JoyCode | 产物 2,571 字符 | 65 秒出产物、84 秒出回执（任务号 06:05:58 → 文件时间 06:07:03 / 06:07:22） | `20261108-joycode-workspace/outbox-receipt.json` + `answer.md` |

> **口径差异（如实标注）**：口述版本是 WorkBuddy 160 字/56 秒、JoyCode 1142 字/157 秒、豆包 135 字/40 秒，与上表留档**不一致**，本页按留档更正。另"模型请求增量 0"回执里没有该字段，已撤回不作对外结论；仅 `20261108-recorder-local-endpoint/recorder.log`（本地端点 18110 启动后 0 请求行）可作内部旁证，但它只覆盖该端点，不等于全链路零调用。

已知边界（都在派单阶段才暴露，不是启动时能提前判断的）：

- **未登录**：豆包停在登录页时，只有派单才会被发现并提示登录（`login_required`）。
- **白屏**：豆包窗口偶发空白，一般会自愈（留档 4 秒恢复）；恢复不了才报 `window_blank`，提示按 `Ctrl+R` 或重启。
- **编辑页/工程状态**：WorkBuddy 停在上一单的 PPT 编辑页时没有输入框（`core/workbuddy_bridge.py` 有专门的回退页逻辑）；JoyCode 没设工作区时找不到工程，要在弹窗里手动选一次。这两种状态只有在真正派单时才知道。

## 六、以后软件换路径，只需要重新自报

每家软件的接入方式写在 `core/adapters/apps/*.json` 的 `channel` 块里（`primary` / `fallback` / `direction` / `transport` / `registration` / `config_path` / `server_name` / `verified` / `ui_steps`），`mcp_channels.channel_status()` 据此返回状态：`connected` / `restart_required` / `config_conflict` / `not_configured` / `server_unavailable` / `ui_manage`（豆包这种只能界面注册的落在 `ui_manage`）。这个块只描述"怎么连上咕嘎"，不描述"咕嘎怎么指挥"。

软件升级、换安装目录后，只需重新调用一次 `report_app`，咕嘎覆盖旧记录并用新路径拉起；旧记录失效时自动回退声明探测并记录原因。声明清单退居为兜底，不需要因为换路径去改声明。

**边界不因软件能力改变**：即使将来某家对外提供"执行任务"的 MCP 端点，咕嘎也不会把派单改成 MCP 通道——MCP 只承担发现（自报名称/路径/版本/能力），指挥始终是界面自动化。

**结论**：MCP 解决"知道有哪些软件、在哪"，界面自动化解决"让它们干活"。前者是发现，后者是指挥；三家目前都只肯当 client，所以指挥只能靠眼睛和手。
