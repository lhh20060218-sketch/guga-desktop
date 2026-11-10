# 声明式软件适配注册表（AI 软件秒级定位）

## 1. 它解决什么问题

`core/local_tools.py` 里的 `APPS` 是写死的 exe 路径 glob + 每次扫描都重新解析快捷方式，
在真实用户环境里经常对不上：

- JoyCode 装在本机 `D:\JoyCode`，而 `local_tools` 里写的是 `%USERPROFILE%\..\JoyCode`；
- WorkBuddy 的注册表 `DisplayIcon` 是 `WorkBuddy.exe,0`，直接读取会拿到带结尾索引的字符串；
- 豆包注册表只有 `icon.ico`，没有 `InstallLocation`，必须回推安装目录；
- 绿色版、异盘安装、无管理员权限时读不到注册表、Program Files 不可写等情况都得有明确结果。

本注册表把“怎么找、怎么起、怎么算就绪、界面点哪里、回执怎么拿”写进 JSON 声明，
启动时一次性加载 + 只读探测 + 落盘缓存；之后 `resolve(id)` 直接返回 exe，不再扫盘。

## 2. 新增文件

| 文件 | 作用 |
| --- | --- |
| `core/adapters/app_registry.py` | 声明加载、校验、只读探测、缓存、启动与就绪判定 |
| `core/adapters/apps/doubao.json` | 豆包声明 |
| `core/adapters/apps/workbuddy.json` | WorkBuddy 声明 |
| `core/adapters/apps/joycode.json` | JoyCode 声明 |
| `core/adapters/apps/_template.json` | 新增软件模板（文件名以 `_` 开头，不会被加载） |
| `scripts/verify_app_registry.py` | 只读探测 + 模拟场景 + 一次启动链路验证 |
| `core/adapters/mcp_channels.py` | MCP 通道：生成三家的配置片段、检测已接入、写入/备份、真实握手、接入教程数据 |
| `ui/mcp_onboarding_dialog.py` | 首次接入教程对话框（复制配置 / 打开配置目录 / 写入 / 测试连接） |
| `scripts/verify_mcp_channels.py` | 三份片段 + 真实写入 + 握手 + 任务闭环实测 |
| `scripts/verify_frozen_channel.py` | 冻结态片段（exe 自身）+ 三家真实握手，输出 `build/frozen_channel_evidence.json` |
| `scripts/verify_restart_refresh.py` | 真实重启 WorkBuddy/JoyCode，校验工具清单/日志/连接见证 |
| `tools/comp_entry.py` | 新增 `--guga-mcp`（stdio server）与 `--mcp-onboarding` / `--mcp-onboarding-json` 验收入口 |
| `integrations/workbuddy/guga-worker/SKILL.md` | WorkBuddy 侧技能模板（装到 `~/.workbuddy/skills/`） |
| `integrations/doubao/guga-worker/SKILL.md` | 豆包侧技能模板（界面里上传） |
| `GUGA-Desktop.spec` | 增加一行 `datas`，把声明 JSON 随包分发 |

运行期文件（不随包、可在只读环境下降级）：

- 探测缓存：`runtime/app_registry.json`（可用 `GUGA_APP_REGISTRY_CACHE` 覆盖）
- 用户路径覆盖：`runtime/app_registry_user.json`（可用 `GUGA_APP_REGISTRY_USER` 覆盖；
  `runtime/` 即 `guga_paths.RUNTIME`，默认 `%LOCALAPPDATA%\GUGA\runtime`）

## 3. 声明格式

一份 JSON 对应一个软件，`id` 必须与 `core/local_tools.py` 里的 `APPS` id 一致，
这样路由层可以无缝复用。

```json
{
  "schema": "guga.app_adapter/1",
  "id": "joycode",
  "name": "JoyCode",
  "capabilities": ["code", "website"],
  "install": {
    "user_override": true,
    "env": ["GUGA_JOYCODE_LAUNCHER"],
    "common_paths": ["D:\\JoyCode\\JoyCode.exe"],
    "registry": {
      "uninstall": [
        {"hive": "HKCU", "view": "any", "display_name_contains": ["joycode"]},
        {"hive": "HKLM", "view": "any", "display_name_contains": ["joycode"]}
      ],
      "app_paths": ["JoyCode.exe"],
      "location_values": ["InstallLocation", "InstallDir", "InstallPath", "DisplayIcon"]
    },
    "start_menu": {"aliases": ["joycode"], "roots": []},
    "portable": {"roots": ["D:\\", "E:\\"], "name_globs": ["JoyCode.exe"],
                 "depth": 2, "budget_ms": 1500, "max_entries": 800}
  },
  "launch": {"exe_name": "JoyCode.exe", "args": [], "cwd": "exe_dir",
             "timeout_seconds": 30, "single_instance": true},
  "ready": {
    "window": {"title_keywords": ["joycode"], "process": "JoyCode.exe"},
    "min_width": 600, "min_height": 400,
    "input_anchor": {"must_exist": false, "name_contains": ["输入", "提问"]}
  },
  "anchors": {
    "input": {"uia": {"control_types": ["Edit", "Document"],
                      "name_contains": ["输入", "提问"]}},
    "send": {"keys": ["ENTER"], "button": {"name_contains": ["发送"]}},
    "done": {"any": ["outbox_receipt", "stop_button_gone"],
             "receipt_path": ".guga/outbox/<task_id>.json"},
    "failure_codes": [{"code": "manual_required", "signals": ["input_focus_unconfirmed"]}]
  },
  "receipt": {"mode": "workspace_outbox_receipt", "receipt_required": true},
  "login": {"required": true, "signals": ["登录", "扫码"], "hint": "首次运行需登录"}
}
```

关键字段说明：

- `install`：探测来源。顺序为
  用户覆盖 → 环境变量 → 常见路径 → 注册表卸载项 → App Paths → 开始菜单/桌面快捷方式
  → PATH → 正在运行的进程 → 绿色版目录扫描。
- `registry.location_values`：依次读取；`DisplayIcon` 的 `,0` 会被剥掉，`.ico` 会回推
  同目录下的 `launch.exe_name`，因此豆包/WorkBuddy 那种“只登记图标”的安装也能命中。
- `start_menu.roots` 为空时默认查三处：用户开始菜单、公共开始菜单、桌面；快捷方式用
  进程内 WScript.Shell 解析，失败时退回一次 PowerShell 批量解析。
- `portable`：只在前面所有来源都没命中时才做，`depth` 最大 4，带 `budget_ms` 与
  `max_entries` 上限；跳过 Windows/AppData/ProgramData 等目录，避免拖慢启动。
- `launch.show` 固定为 `min_no_activate`，实现上使用 `SW_SHOWNOACTIVATE`（正常显示、
  不抢前台）；不用 `SW_SHOWMINNOACTIVE`，因为最小化窗口无法做 UIA/点击。
- `ready`：窗口标题/进程名 + 最小尺寸；`input_anchor.must_exist=true` 时才会额外做
  UIA 文本校验，UIA 不可用按“未确认”处理，不误判失败。
- `anchors`：给后续界面自动化用的锚点与失败码，不写绝对像素坐标。
- `receipt`：回答/产物的获取方式；WorkBuddy 是“页面全选 + 剪贴板回读 + 产物目录”，
  JoyCode 是 `.guga/outbox/<task_id>.json` 回执。
- `login`：首次运行未登录的识别信号与给用户的话术。
- `channel`：该软件走哪条通道。`direction=guga_server` 表示咕嘎做 MCP server、软件做 client；
  `transport` 目前统一 `stdio`；`registration=file` 才可自动写入与检测，`registration=ui`
  （豆包）表示只能在界面添加，`config_path` 必须留空。
  `fallback=ui-auto` 表示 MCP 不可用时退回界面自动化，且界面上要标注“界面操作，不是接口调用”。
  `verified` 记录该通道验证到了哪一步、证据与日期，未验证的写 `unverified`，不假装通过。
- `download`：官网下载页与常见安装位置；未安装时探测结果和接入教程用它给出下载指引。

## 4. 返回状态

`probe(id)` / `resolve(id)` 永远返回结构化结果，不会静默返回空：

| status | 含义 | `installed` |
| --- | --- | --- |
| `ready` | 找到真实存在的 exe | `true` |
| `not_installed` | 所有声明的来源都检查成功且未命中 | `false` |
| `unknown` | 有来源失败/被拒绝/超预算，无法断言未安装 | `null` |
| `invalid_declaration` | 声明本身不合法 | `null` |
| `unknown_app` | 没有对应声明 | `null` |

其它字段：`exe`、`source`/`source_label`（命中来源）、`errors`（如 `registry_denied`）、
`incomplete`（未完成来源）、`elapsed_ms`、`cached`、`running`、`login`、`message`。

缓存规则：

- 缓存文件带声明指纹，声明或用户覆盖文件一变就失效；
- `ready` 命中时每次都会校验 exe 是否仍存在，被卸载/移动会立即重新探测；
- `not_installed` 缓存 10 分钟，`unknown` 缓存 2 分钟，避免装了软件后一直显示旧结果；
- `runtime/` 不可写时写入失败被吞掉，探测结果照常返回。

## 5. 实测结果（本机，2026-11-07）

命令：`python scripts/verify_app_registry.py`

| 软件 | 冷探测 | 热探测（缓存） | 命中来源 | exe |
| --- | --- | --- | --- | --- |
| 豆包 | ready / 1812 ms | 16 ms | 常见安装路径 | `%USERPROFILE%\AppData\Local\Doubao\Application\Doubao.exe` |
| WorkBuddy | ready / 16 ms | 0.0 ms | 常见安装路径 | `%USERPROFILE%\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe` |
| JoyCode | ready / 15 ms | 0.0 ms | 常见安装路径 | `D:\JoyCode\JoyCode.exe`（非默认盘） |

> 首次冷探测包含一次性的 `psutil` 进程枚举开销（约 1.8 秒）；后续冷探测都在 20 ms 内。
> 启动时用 `warmup()` 在后台线程预热，用户派单时走缓存；实测热命中 0–16 ms 拿到 exe。

模拟场景（脚本自建夹具，跑完即清理）：

| 场景 | 结果 | 说明 |
| --- | --- | --- |
| 未安装 | `not_installed` | 所有来源都检查成功、未命中 |
| 异盘安装 | `ready` / `common_path` | 夹具放在 `D:\rengongzhineng\.guga_app_registry_sim` |
| 绿色版解压目录 | `ready` / `portable` | 仅靠受限目录扫描命中（扫描 3 个目录） |
| 用户手工指定路径 | `ready` / `user_override` | `set_override` 写入后直接命中 |
| 缓存目录不可写 | `ready` | 缓存写入失败被吞掉，探测结果不受影响 |
| 环境变量失效 | `unknown` / `env_invalid` | 不会误报为未安装 |
| 注册表拒绝访问 | `unknown` / `registry_denied` | 故障注入模拟普通用户/组策略限制 |

启动链路实测：

| 场景 | 结果 |
| --- | --- |
| 记事本（真实 Popen → 窗口 → 关闭，共 2 次） | 第 1 次发现 `SW_SHOWMINNOACTIVE` 会把窗口最小化（160×28）；改为 `SW_SHOWNOACTIVATE` 后复测为 `ready`，375 ms，窗口 1440×686，均已关闭 |
| JoyCode（当前窗口最小化） | `running_minimized`，16 ms，未重复拉起，提示用户恢复窗口 |

> 两个记事本实例均已关闭；豆包/WorkBuddy/JoyCode 没有被新起实例。

未验证项（不要当成通过）：

- 豆包/WorkBuddy 的真实启动没有执行（两者当前都只有托盘/后台进程，避免打扰用户）；
  启动链路是用系统记事本验证的。
- 登录页 UIA 文本识别没有在真实登录页上跑过，声明里的 `login.signals` 只是判据。
- `input_anchor.must_exist=true` 当前三个声明都没开，UIA 输入框校验未实测。
- 打包后的 `_internal/core/adapters/apps` 路径只做了 spec 配置，未重新打包验证。

## 6. 接入现有路由（建议改动点）

原则：只做加法，不改 `core/tool_router.py` 和 `core/local_tools.py` 的现有逻辑；
`ui/first_run.py`、`ui/sprite_animator.py`、`ui/avatar_renderer.py` 不要动。
`core/adapters/joycode_adapter.py`、`core/adapters/joycode_ui.py` 归另一并行会话，
本节只给交接建议，不直接编辑；落地时由该会话按下面的片段收口。

### 6.1 `core/local_tools.py::_find_exe`（最高收益，4 行）

在函数最前面查注册表；命中就直接返回，未命中继续走原来的 glob + 快捷方式。

```python
def _find_exe(spec):
    try:
        from core.adapters import app_registry
        hit = app_registry.resolve(spec.get('id'))
        if hit.get('status') == 'ready' and hit.get('exe'):
            return Path(hit['exe'])
    except Exception:
        pass
    for pattern in spec['exe_globs']:
        ...
```

这样 `local_tools.probe`、`local_tools.scan(launch_probe=False)`、`tool_advice.installed_ids()`
都会自动受益；JoyCode 的 `C:\JoyCode` 写死路径问题会被注册表的 `D:\JoyCode` 结果纠正。

### 6.2 `ui/agent_runtime.py` 的 `_local_tools_execute`（probe/scan 动作）

在调用 `local_tools.probe/scan` 前先尝试 `app_registry.probe(id)`；
`ready` 时直接返回，`unknown` 时把 `errors` 原样带回去，避免上层把“读不到注册表”当成未安装。

### 6.3 `core/workbuddy_bridge.py::_launch`

```python
def _launch(timeout=45):
    try:
        from core.adapters import app_registry
        result = app_registry.launch('workbuddy', verify=True, timeout=timeout)
        if result.get('hwnd'):
            return {'hwnd': result['hwnd'], 'title': result.get('window_title', '')}
    except Exception:
        pass
    # 原逻辑保持不变：EXE_CANDIDATES + Popen
```

注意：如果返回 `running_minimized`，不要直接抛错继续重试；应把提示交给用户恢复窗口。

### 6.4 `core/adapters/joycode_adapter.py::_default_launcher`（交接给另一会话）

该文件由并行会话负责，这里只给建议片段：保持 `GUGA_JOYCODE_LAUNCHER` 优先级不变，
仅把兜底路径改为：

```python
def _default_launcher(self):
    try:
        from core.adapters import app_registry
        exe = app_registry.exe_path('joycode')
        if exe:
            return exe
    except Exception:
        pass
    for candidate in (Path(r'D:\JoyCode\JoyCode.exe'), Path(r'D:\JoyCode\bin\joycode.cmd')):
        ...
```

### 6.5 `core/tool_advice.py::installed_ids`

可选：把 `app_registry` 中 `ready` 的 id 并进 `installed` 集合，只做并集，不替换原
`local_tools` 清单；这样“软件装了但 local_tools 的 glob 写错”不会再误报缺失。

### 6.6 启动预热

在 `comp_main.py` / `launcher.py` 启动流程里加一行（后台线程，不阻塞界面）：

```python
from core.adapters import app_registry
app_registry.warmup()
```

不要在 PyQt 主线程同步 import + 探测；`warmup()` 内部是守护线程，异常已兜底。

### 6.7 MCP 派单接入点（新增文件，不改受保护文件）

派单前先查通道，再决定“接口派单”还是“界面操作”：

```python
from core.adapters import mcp_channels

status = mcp_channels.channel_status('joycode')      # 通道、配置位置、是否已接入
if status['direction'] == 'guga_server' and status['added']:
    # 走 MCP：任务写 .guga/inbox，软件侧通过 get_task 领取
    ...
elif status['registration'] == 'ui' or not status['added']:
    # MCP 不可用：按声明 anchors 走界面自动化，并在界面标注“界面操作”
    ...
```

首次接入教程（在 `ui/first_run.py` 完成首次配置后调用，或放到设置页入口）：

```python
from ui.mcp_onboarding_dialog import show_mcp_onboarding
show_mcp_onboarding(parent)      # 列出已装软件、片段、配置位置、已接入状态
```

`ui/first_run.py`、`core/tool_router.py`、`core/local_tools.py`、
`ui/sprite_animator.py`、`ui/avatar_renderer.py` 均未修改。

## 7. 如何新增一个软件（剪映、WPS 等）

1. 复制 `core/adapters/apps/_template.json` 为 `<id>.json`；
2. 改 `id`（与 `local_tools.APPS` 对齐）、`name`、`capabilities`、`process_names`；
3. 按真实安装方式填 `common_paths` / `registry.uninstall` / `start_menu.aliases`；
4. 填 `ready.window` 与 `anchors`（不要写绝对像素坐标）；
5. 如果软件是绿色版或装在特殊目录，不改声明，直接写用户覆盖：

```python
from core.adapters import app_registry
app_registry.set_override('your-app-id', r'E:\Green\YourApp\YourApp.exe', note='绿色版')
```

用户覆盖文件示例：

```json
{
  "your-app-id": {"exe": "E:\\Green\\YourApp\\YourApp.exe", "note": "绿色版"}
}
```

## 8. 打包

`GUGA-Desktop.spec` 的 `datas` 已增加：

```python
(os.path.join(ROOT, 'core', 'adapters', 'apps'), 'core/adapters/apps'),
```

`hiddenimports` 补齐了 MCP 运行依赖（不能用 `collect_submodules('mcp')`，
否则会拉进依赖 typer 的 `mcp.cli` 导致构建失败）：

```python
hiddenimports += [
    'mcp', 'mcp.types', 'mcp.server', 'mcp.server.mcpserver',
    'mcp.client', 'mcp.client.stdio',
]
```

PyInstaller 的 onedir 产物会在 `_internal/core/adapters/apps/` 下带着声明；
`app_registry.declaration_dirs()` 同时兼容源码、frozen、`GUGA_APP_ADAPTERS` 与
`<配置目录>/app_adapters` 四种位置。

打包入口新增两个验收分支（`tools/comp_entry.py`）：

- `--guga-mcp`：stdio MCP server，不初始化 Qt，供三家软件作为 client 拉起；
- `--mcp-onboarding` / `--mcp-onboarding-json`：接入教程窗口 / 无界面状态导出。

冻结态下 MCP 条目直接指向 exe 自身（`sys.executable` + `--guga-mcp`），
不再依赖目标机器安装 Python。构建产物校验要求包含
`_internal/mcp/...` 与 30 项关键 DLL/目录；`build_guga_exe.py` 的完整性检查
不通过会删除半成品目录，避免把缺文件的包交给评委。

## 9. 运行期诊断

```python
from core.adapters import app_registry

app_registry.app_ids()                 # 已加载的声明
app_registry.declarations()            # 合并默认值后的声明
app_registry.declaration_errors()      # 不合法的声明与原因
app_registry.probe('joycode')          # 只读探测（默认走缓存）
app_registry.probe('joycode', force=True)  # 强制重新只读探测
app_registry.diagnose()                # 全量结果 + 汇总
app_registry.launch('joycode')         # 显式启动/复用；不抢前台
```

验证脚本：

```bash
python scripts/verify_app_registry.py                  # 只读，不启动任何软件
python scripts/verify_app_registry.py --json           # 完整 JSON
python scripts/verify_app_registry.py --launch-mechanism  # 记事本启动一次并关闭
python scripts/verify_app_registry.py --launch-real --ids joycode  # 已有窗口时只返回状态
```

## 10. MCP 通道结论（2026-11-07 实测）

### 10.1 方向表

三家工具都是 MCP **客户端**，所以主线统一是“咕嘎做 server、软件连过来”，
不存在“咕嘎去连它们的 server”的情况。

| 软件 | 通道 | 方向 | 注册方式 | 配置位置与格式 | 本机结论 |
| --- | --- | --- | --- | --- | --- |
| WorkBuddy | mcp | 咕嘎 server → WorkBuddy client | file | `%USERPROFILE%\.workbuddy\mcp.json`，顶层 `mcpServers`，条目 `command/args/env/disabled` | 已写入并握手成功；需重启 WorkBuddy 才加载新条目 |
| JoyCode | mcp | 咕嘎 server → JoyCode client | file | 工作区 `.joycode/mcp.json` 优先；用户级 `%USERPROFILE%\.joycode\joycode-mcp.json`，schema 同上（支持 stdio/SSE/streamableHttp） | 用户级条目“已接入”被识别；项目级已写入；握手成功 |
| 豆包 | mcp（UI 管理） | 咕嘎 server → 豆包 client | ui | 无本地文件；登录后在“连接器 / 个人 MCP”新建，字段 `name/transport/command/params/env`，云端接口 `AGWManageCreatePersonalConnector` | **卡在必须登录 + 界面新增**；服务端握手可通，软件侧未完成注册 |

UI 自动化三家都保留为兜底（`fallback=ui-auto`）：只有 MCP 未接入、端点不通、
版本不支持或未登录时才用，且界面必须标注“界面操作，不是接口调用”。

### 10.2 生成的配置片段（两种形态）

片段由 `mcp_channels.server_command()` 按运行形态自动生成，**不写死 Python 路径**：

| 形态 | 判定 | 条目 |
| --- | --- | --- |
| 打包（frozen） | `sys.frozen` 为真，或测试时 `GUGA_MCP_FORCE_FROZEN=1` | `command = sys.executable`（咕嘎 exe 自身），`args = ["--guga-mcp"]` |
| 源码 | 非 frozen | `command = 找到 mcp 包的解释器`，`args = ["<绝对路径>/core/adapters/guga_mcp_server.py"]` |

冻结态示例（评委机器不需要装 Python）：

```json
{
  "mcpServers": {
    "guga": {
      "command": "D:\\YourPath\\GUGA-Desktop\\GUGA-Desktop.exe",
      "args": ["--guga-mcp"],
      "env": {"GUGA_WORKSPACE": "D:\\rengongzhineng", "PYTHONIOENCODING": "utf-8",
              "GUGA_CLIENT_ID": "workbuddy"},
      "disabled": false
    }
  }
}
```

打包入口 `tools/comp_entry.py` 里的 `--guga-mcp` 分支直接调用
`core.adapters.guga_mcp_server.main()`，不初始化 Qt；`--dsh-tools` 旧通道仍保留。
`mcp_channels.frozen_exe()` 默认找 `dist/GUGA-Desktop/GUGA-Desktop.exe`；
测试时可用 `GUGA_MCP_EXE` 指向任意解压副本，真实用户机器上不需要设置。

### 10.3 真实调用证据

命令：`python scripts/verify_mcp_channels.py`（源码态）
`python scripts/verify_frozen_channel.py`（冻结态，报告 `build/frozen_channel_evidence.json`）

| 检查项 | 结果 |
| --- | --- |
| WorkBuddy 写入 `mcp.json` | `status=added`，备份后原子写；自动补 `mcp-approvals.json` 信任项 |
| JoyCode 用户级 + 项目级 | 两处都写入 frozen 条目；用户级同名 `guga` 与项目级一致，不再竞争 |
| MCP 握手（三家各自条目） | `initialize + list_tools` 均成功；工具为 `get_task / report_progress / submit_artifact / ask_guga` |
| 冻结态握手（打包 exe） | 三家的 `command` 都是 `GUGA-Desktop.exe`、`args=["--guga-mcp"]`；三家握手均返回 4 个工具；连接见证 `mode=frozen` |
| 任务闭环（临时工作区） | `get_task` 领到任务 → `report_progress` 记事件 → `ask_guga` 轮询回答 → `submit_artifact` 写出回执 |

WorkBuddy 的信任机制：`%USERPROFILE%\.workbuddy\mcp-approvals.json` 的 key 是
`sha256(trustMaterial)::serverName`，`trustMaterial = command|args排序|env键排序|cwd`。
`mcp_channels.apply()` 写入配置后会同步写这一项（与用户在界面点“允许”等效），
否则 WorkBuddy 不会启动未信任的本地 server。

### 10.4 重启后的工具清单证据（2026-11-07 23:57–23:58）

实际关闭并重启两家软件（脚本 `scripts/verify_restart_refresh.py`，报告
`build/restart_refresh_evidence.json`，快照 `build/final_evidence.json`）：

| 软件 | 重启方式 | 软件侧证据 | 时间戳 | 结论 |
| --- | --- | --- | --- | --- |
| WorkBuddy | 关闭 7 个进程（20 秒内未退出，强制结束）→ `explorer.exe` 拉起 3 个进程 | `%USERPROFILE%\.workbuddy\mcp-tool-list.json` 出现 guga 条目，含 `get_task / report_progress / submit_artifact / ask_guga`；连接见证 `pid=32796, mode=frozen` | 工具清单 `2026-11-07T23:57:46`；见证 `23:57:46` | **已加载 4 个工具** |
| JoyCode | 正常关闭 → 拉起 4 个进程 | `MCP Servers Host.log` 处理 `user::guga` 与 `project::guga`；`MCP guga.log` 记录 `Connection established for guga`；连接见证 `pid=19588, mode=frozen` | 日志 `23:58:00`–`23:58:02`；见证 `23:58:02` | **连接建立** |

WorkBuddy 只在启动时短暂拉起 stdio server 拉取工具清单，随后子进程退出，
所以状态判断不能只看“连接进程是否存活”，还要看工具清单是否在配置写入之后刷新。

### 10.5 豆包连接器引导与轮询

豆包没有本地 `mcpServers` 文件，只能在界面新建“个人 MCP 连接器”。接入教程卡片给出
可直接照填的字段（名称 `guga`、传输 `stdio`、命令 = exe 绝对路径、参数 `--guga-mcp`、
环境变量 `GUGA_WORKSPACE/GUGA_CLIENT_ID/PYTHONIOENCODING`），并说明保存后窗口会自动检测。

轮询：对话框每 3 秒调用 `mcp_channels.onboarding()`；服务端启动时写
`.guga/mcp-connections/<GUGA_CLIENT_ID>.json`（客户端 ID、pid、启动时间、argv、frozen/source），
状态从 `ui_manage` 变为 `connected` 时卡片自动换成“已接入”。

本机实测（`build/doubao_connect_evidence.json`）：用与豆包连接器相同的
`name/transport/command/params/env` 拉起冻结态 exe，服务端收到 `GUGA_CLIENT_ID=doubao`
的连接请求（见证 `pid=29744, mode=frozen`），`list_tools` 返回 4 个工具，
1 秒内状态轮询即变为 `connected`。

**未完成项（如实说明）**：没有在豆包登录后的界面里真正点击“新建连接器”，因为需要账号登录；
上面的证据是“服务端能收到豆包格式的连接请求 + 状态轮询会自动翻转”，不是“豆包云端已创建连接器”。

未验证项（不要当成通过）：

- 豆包云端连接器创建需要登录，本机未做登录操作。
- WorkBuddy 重启采用强制结束 7 个进程；若用户有未保存内容，强制结束有风险，
  脚本会先尝试 WM_CLOSE，超时才强杀。

## 11. 首次接入教程

`ui/mcp_onboarding_dialog.py`（新增文件）依赖 `mcp_channels.onboarding()`，逐项显示：

- 软件是否已安装；未安装显示 `download.hint` 与“打开下载页”；
- 通道说明：“MCP 接口派单（咕嘎 server → 软件 client，stdio）”或“界面操作”；
- 本机 server 形态（frozen/source）、命令与参数（冻结态显示 exe 自身 + `--guga-mcp`）；
- 配置位置、可复制的片段；
- 三种状态徽章：**已接入** / **已写配置，待重启** / **未接入**（豆包为“需在豆包界面添加”）；
- 动作：复制配置、打开配置目录、写入配置（带备份）、测试连接；豆包显示逐项字段与步骤；
- 每 3 秒轮询一次，状态变化时自动重建卡片；豆包卡片提示“填完保存后本窗口会自动检测”。

状态判定（`mcp_channels.channel_status()`）：

| 状态 | 判定 |
| --- | --- |
| `connected` | 连接见证进程存活；或连接见证时间晚于配置写入；或 WorkBuddy 工具清单晚于配置写入且含 4 个工具 |
| `restart_required` | 配置条目已存在且一致，但上述连接证据都不存在 → “已写配置，待重启” |
| `not_configured` | 配置里没有 guga 条目 → “未接入” |
| `ui_manage` | 豆包等只能在界面注册、且最近没有连接见证 → “需在豆包界面添加” |

打包版入口（`tools/comp_entry.py`）：

```bash
GUGA-Desktop.exe --mcp-onboarding                 # 打开接入教程窗口
GUGA-Desktop.exe --mcp-onboarding-json out.json   # 不开界面，输出三家的状态与片段
```

接入点（不改 `ui/first_run.py`）：首次配置完成后调用
`show_mcp_onboarding(parent)`，或把入口放到设置页。检测到已接入时显示“已接入”，
不重复催促；所有动作都返回结构化结果，失败会说明原因（目录不存在、配置 JSON 损坏、
找不到能 `import mcp` 的 Python、同名条目参数冲突等）。

三态实测（用打包 exe 跑 `--mcp-onboarding-json`，报告 `build/three_states_evidence.json`）：

| 场景 | 隔离方式 | 结果 |
| --- | --- | --- |
| 已接入 | 真实工作区 + 真实用户目录 | WorkBuddy / JoyCode / 豆包 均为 `connected` |
| 未接入 | 空工作区 + 临时 `USERPROFILE`（不碰真实配置） | WorkBuddy / JoyCode 均为 `not_configured`；豆包 `ui_manage` |
| 已写配置待重启 | 临时工作区写入 JoyCode 条目 + 临时 `USERPROFILE` | JoyCode 为 `restart_required`（没有连接见证） |

软件侧技能模板：

- WorkBuddy：把 `integrations/workbuddy/guga-worker/` 复制到
  `%USERPROFILE%\.workbuddy\skills\guga-worker\`，重启 WorkBuddy。
- 豆包：在“技能”界面把 `integrations/doubao/guga-worker/SKILL.md` 上传为技能
  （或打包成 zip，zip 内为 `guga-worker/SKILL.md`）。
- JoyCode：工作区已有 `.joycode/commands/guga-run.md` 与 `.joycode/skills/guga-worker/SKILL.md`，
  是本方案的范本，无需重复安装。
