# 咕嘎云端接口契约（客户端 / 本体对接说明）

- 服务地址：`http://39.107.48.60:3000`（线上单机，systemd `guga.service` 托管）
- 服务版本：`package.json` 1.0.0 / `server.js`（2026-11-07 状态机修复版）
- 适用对象：桌面端 exe（用户身份）与本机执行方「咕嘎本体」（设备身份）
- 数据落盘：`/root/guga-server/data/*.json`；任务台账每账号保留最近 30 单

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 用户鉴权 | 请求头 `Authorization: Bearer <token>`（登录获得，7 天有效） |
| 本体鉴权 | 请求头 `x-agent-token: <token>`（配对获得，长期有效，30 天无心跳回收） |
| 请求体 | `application/json`；普通接口上限 64kb，视觉/证据接口上限 3mb |
| 时间字段 | 全部为毫秒时间戳（number） |
| 成功响应 | HTTP 200 + JSON；失败为 4xx，且尽量带 `error` 中文可读原因 |
| 限流 | 派单 4s、生成配对码 1.5s、暂停/继续 1.5s、配对接口每 IP 1.2s（连错 8 次锁 10 分钟）、视觉 1.2s |
| 配对码 | 6 位数字，10 分钟有效，一次性消费 |

## 2. 桌面端（用户身份）实际调用的接口

### 2.1 登录 `POST /api/login`

请求：`{ "username": "888", "password": "...", "device": "Windows-PC" }`（`device` 可空，最多 40 字）

响应：`{ "token": "...", "username": "888" }`

失败：`401 {"error":"账号或密码不正确"}`

> 当前没有 `/api/register`：账号由服务端 `data/users.json` 预置，客户端不调用注册接口。

### 2.2 任务台账读取 `GET /api/state`

响应：

```json
{
  "serverTime": 1794063864461,
  "tasks": [ /* 当前账号最近 30 单，新→旧 */ ]
}
```

`tasks[]` 字段见第 5 节。桌面端轮询此接口刷新台账/状态播报。

### 2.3 派单 `POST /api/tasks`

请求：

```json
{
  "goal": "用豆包写一篇 200 字作文",
  "space": "通用",
  "executor": "local",
  "device": "a1b2c3d4",
  "requiredTools": ["豆包"]
}
```

- `executor`：`local` = 交给本机执行方；缺省 = 云端工人/演示剧本
- `device`：设备选择器里的稳定设备 id（`GET /api/agent/devices` 或 `GET /api/devices/inventory` 响应里的 **`id`**，即 `agents.json` 的 `agent.id`），兼容旧客户端直接传设备名；**不接受** `device_id`（机器稳定标识只用于清单归账与查询过滤，不参与派单匹配）；不传 = 账号下任一本体
- `requiredTools`：可选，仅当同时传 `device` 时才校验（最多 10 项，按 `name` / `launch` / `aliases` 模糊匹配；也兼容 snake_case `required_tools`）

响应：`{ "task": {...}, "mode": "real" | "demo" }`

失败（HTTP 400）：

| `code` | 含义 |
|---|---|
| `DEVICE_OFFLINE` | 点名设备本体不在线 |
| `NO_INVENTORY` | 点名设备在线但尚未上报软件清单 |
| `TOOL_MISSING` | 点名设备清单里没有所需软件（附 `missing[]`） |

错误体示例：

```json
{"error":"所选设备「DESKTOP-A」上没有：豆包——换一台设备，或先在那边装好再派","code":"TOOL_MISSING","deviceId":"a1b2c3d4","deviceName":"DESKTOP-A","missing":["豆包"]}
```

三类错误必须分别处理，不要统一显示成“失败”。

## 3. 咕嘎本体（设备身份）实际调用的接口

### 3.1 生成配对码 `POST /api/pair/create`（用户 token）

请求：`{}` → 响应：`{ "code": "123456", "expiresIn": 600 }`

### 3.2 配对 `POST /api/agent/pair`（无鉴权，凭配对码）

请求：

```json
{
  "code": "123456",
  "device": "DESKTOP-A",
  "path": "C:/guga",
  "device_id": "可选稳定机器标识",
  "caps": {"pyver":"3.12","platform":"windows","agent":"v2","deps_ok":true}
}
```

响应：`{ "token": "...", "user": "888" }`

### 3.3 心跳 + 领单 `POST /api/agent/beat`（本体 token，每 4 秒）

请求：`{ "path": "C:/guga", "caps": {...}, "busy": false, "selfcheck": {...} }`

- `busy:true` 为干活期间的保活心跳：只刷新在线状态，不派新单

响应（有单）：

```json
{
  "job": {
    "taskId": "tmw6hwf5w", "stId": "st0", "name": "打开豆包并生成",
    "goal": "用豆包写一篇作文", "acceptance": "交付物完整可用",
    "feedback": "上一轮打回意见", "attempt": 2,
    "app": "豆包", "resume": "暂停前进度", "attachText": "上一步产物全文"
  }
}
```

响应（无单）：`{ "job": null, "serverTime": 1794063864461 }`

### 3.4 交付回执 `POST /api/agent/result`（本体 token）

请求：

```json
{"taskId":"tmw6hwf5w","stId":"st0","ok":true,"content":"交付正文","note":"","aborted":false}
```

- `ok:false` 时 `content` 可为空，用 `note` 说明原因
- **新增可选字段 `aborted: true`**：用户主动中止。服务端按“中止”收尾，不再自动重派（旧客户端不传时，若 `note` 以「已中止」「用户终止」「Stopped」开头也会被识别为中止）

响应：

| 场景 | 响应 |
|---|---|
| 验收通过 / 达到上限 | `{"ok":true,"accepted":"done","pass":true/false}` |
| 打回重做（第 1~2 次失败） | `{"ok":true,"accepted":"retry"}` |
| 连续 3 次失败 | `{"ok":true,"accepted":"failed"}` |
| 用户中止 | `{"ok":true,"accepted":"aborted"}` |

`404 {"error":"任务不存在"}` / `404 {"error":"子任务不存在"}` 表示 taskId/stId 不匹配（本体必须使用 beat 返回的原值）。

### 3.5 暂停指令轮询 `POST /api/agent/ctl`（本体 token）

请求：`{ "taskId": "...", "stId": "可选；新客户端建议带上" }`

响应：`{ "action": "pause" | "go", "stId": "命中的子任务 id" }`

> 只传 `taskId` 时，服务端会优先命中“正在执行 / 已暂停”的本机子任务，不再盲取第一个（修复多子任务下暂停永远返回 go 的问题）。

### 3.6 确认暂停 `POST /api/agent/paused`（本体 token）

请求：`{"taskId":"...","stId":"...","ctx":"当前进度说明（≤400 字）"}` → 响应：`{"ok":true}`

服务端保留 15 分钟，期间可“继续”并带上 `ctx` 无缝接续；超时自动清理为异常。

### 3.7 请示 `POST /api/agent/consult`（本体 token）

请求：`{taskId,stId,goal,name,acceptance,app,reply}` → 响应：`{"type":"deliverable"}` 或 `{"type":"followup","text":"下一句话"}`

### 3.8 视觉请示 `POST /api/agent/vision`（本体 token，上限 3mb）

请求：`{"image":"base64（可带 data:image 前缀）","question":"..."}`

响应：`{"ok":true,"text":"...","model":"..."}`；未配置视觉模型时 `{"ok":false,"error":"视觉模型未配置"}`

### 3.9 取证截图 `POST /api/agent/evidence`（本体 token，上限 3mb）

请求：`{"taskId":"...","stId":"...","tag":"step","image":"base64"}`

响应：`{"ok":true,"file":"evd_<taskId>_<stId>_<ts>_<tag>.jpg"}`（每子任务只保留最近 10 张）

### 3.10 软件清单上报 `POST /api/agent/inventory`（本体 token）

请求：

```json
{"items":[{"name":"WorkBuddy","launch":"WorkBuddy.exe","version":"1.0","path":"C:/...","summary":"PPT 生成","aliases":["workbuddy"],"updatedAt":1794000000000}]}
```

响应：`{"ok":true,"deviceId":"a1b2c3d4","device":"DESKTOP-A","count":1,"updatedAt":...}`

- 设备标识由配对信息派生，无需客户端传
- 最多 200 条；清单 30 天过期
- 旧版不调用此接口时，跨设备工具校验自动跳过，行为不变

## 4. 只读辅助接口（用户 token）

| 接口 | 响应要点 |
|---|---|
| `GET /api/agent/status` | `{online, device, path, aiFound, devices[], agents[]}` |
| `GET /api/agent/devices` | `{devices:[{id,device,path,ai[],aiFound,pyver,agent,outdated,depsOk,lastSeen}]}` |
| `GET /api/devices/inventory?device_id=&id=&device=` | `{devices:[{...deviceView, device_id, hasInventory, inventoryAt, toolsCount, tools[]}], total, online, withInventory}`；`id` = 派单可用的 agent id，`device_id` = 客户端上报的机器稳定标识（仅归账/过滤用） |
| `GET /api/spaces` | `{spaces:[...]}` |
| `POST /api/task-pause` | `{taskId,stId,action:"pause"|"resume"}` → `{ok:true}`；网页端按钮使用 |

## 5. 任务台账数据结构

### 5.1 task

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 任务 id（`t`+时间戳 36 进制） |
| `userId` | string | 归属账号 |
| `goal` | string | 总目标（≤120 字） |
| `space` | string | 工作空间（≤16 字） |
| `createdAt` | number | 下发时间 |
| `finishedAt` | number | 收尾时间；`0` = 未结束 |
| `demo` | boolean | 是否演示剧本（未配置模型） |
| `execDevice` / `execDeviceId` | string | 本机执行时锁定的设备名 / 稳定 id |
| `targetApp` | string | 本机执行目标软件 |
| `finalReviewing` | boolean | 终检进行中 |
| `subtasks` | array | 子任务（最多 4 个） |
| `log` | array | 轨迹：`[{ts, kind:"info"|"good"|"warn", text}]` |

### 5.2 subtask

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `st0`…`st3` |
| `name` | string | 子任务名（≤24 字） |
| `executor` | string | `本机执行` / 云端执行器名 |
| `worker` | string | 云端工人角色（本机执行时无意义） |
| `acceptance` | string | 验收标准（≤80 字） |
| `status` | enum | **`pending` / `running` / `review` / `returned` / `paused` / `done` / `error`** |
| `progress` | number | 0–100 |
| `attempts` | number | 已执行次数（上限 3） |
| `startedAt` | number | 本轮开始时间 |
| `finishedAt` | number | **新增**：落定（done/error）时间；重派时清零 |
| `feedback` | string | 打回/返工意见 |
| `checkResult` | string | 验收结论 |
| `artifact` | object\|null | `{attempt,chars,file,executor}` |
| `evidence` | array | `[{tag,file,ts}]` 最近 10 张 |
| `localClaimed` | boolean | 本体是否已领单（防同机重复领）；派单（`startLocalJob`）与各终态都会重置为 `false` |
| `claimedBy` | string | **新增**：领走这单的执行方设备 id（`agents.json` 的 `id`），终态清空 |
| `lastAliveAt` | number | **新增**：最后一次 `busy:true` 心跳时间（判死基准），领单时初始化为领单时间 |
| `pauseRequested` / `pausedAt` / `pauseCtx` | — | 暂停相关 |
| `rerunAt` | number | 返工等待时间 |

> **状态值口径统一为 `error`（不是 `failed`）**。服务端只输出 `error`，不会输出 `failed`；客户端把“失败”展示映射到 `error` 即可（该映射由客户端侧修改，服务端不为迁就客户端改字段名）。

## 6. 一次任务的完整轨迹（排查口径）

1. `POST /api/tasks` → `task.createdAt`、`log[0]`
2. `startLocalJob` → 子任务 `startedAt`、`log` 出现「已派给本机执行方」
3. `POST /api/agent/beat` 领单 → `localClaimed=true`、`claimedBy=<设备 id>`、`lastAliveAt=<领单时间>`
4. 干活期间每 4 秒 `POST /api/agent/beat` 带 `busy:true` → 刷新 `lastAliveAt`
5. `POST /api/agent/result` → `review` → 验收 → `done`/`returned`/`error` + `finishedAt`（终态清空 `claimedBy`）
6. 全部子任务落定 → `🔍 各子任务均已落定…` → `finishedAt` + 收尾日志

> 2026-11-07 修复后：连续失败、心跳中断超时、设备离线、暂停超时这四类“异常终止”都会触发收尾，不再出现“子任务已失败但整单永远停在执行中”。

### 6.1 本机执行判死口径（2026-11-07 起）

| 场景 | 判定 |
|---|---|
| 本体持续发 `busy:true` 心跳 | **绝不判死**，`running` 可以持续任意时长（WorkBuddy 出 PPT 实测 13 分钟属正常） |
| 心跳中断（本体退出/失联/断网） | 从**最后一次 `busy` 心跳**（`lastAliveAt`）起算，满 **20 分钟**判 `error` 并触发整单收尾 |
| 心跳尚未建立（刚派单、本体还没领单） | 从 `startedAt` 起算；设备离线 60 秒未领单另由看门狗处理（改派或快速失败） |
| 90 秒提示 | 仅写一条 `⏰` 提醒日志，不改变状态 |

补充：`lastAliveAt` 只由 `claimedBy` 对应设备的 `busy` 心跳刷新（不会出现“别的电脑心跳把这一单保活”）。本体心跳间隔应为 4 秒；若客户端心跳已停但仍被判死，看 `lastAliveAt` 与 `checkResult`（`本机执行方 20 分钟无心跳且未交付`）。

## 7. 本次契约变更（向后兼容）

| 变更 | 影响 |
|---|---|
| `POST /api/agent/result` 新增可选 `aborted` | 旧客户端不传也兼容（按 note 前缀识别中止） |
| `POST /api/agent/ctl` 新增可选 `stId` | 旧客户端只传 taskId 仍然可用，命中逻辑已修正 |
| 子任务新增 `finishedAt` | 纯新增字段，旧客户端忽略即可 |
| `accepted` 新增取值 `aborted` | 客户端按需处理，未处理时与 `failed` 同样视为终止 |
| 子任务新增 `claimedBy` / `lastAliveAt` | 纯新增字段，旧客户端忽略即可 |
| 本机执行超时策略改为「心跳存活不判死 / 心跳中断满 20 分钟判死」 | 长任务不再被 7 分钟误杀；客户端无需改动，`busy:true` 心跳行为保持不变 |

## 8. 客户端已知待改（已移交客户端侧；服务端保持 `error` 语义不变）

> 服务端状态值固定为 `error`（永不输出 `failed`）。以下为客户端的映射问题，由客户端侧修改，**服务端不改字段名、不迁就客户端**。

1. `core/butler_cloud.py`：`task_overall()` 判断了 `failed`，服务端实际是 `error` → 桌面端聚合状态永远不会显示失败。
2. `ui/comp_window.py`：失败播报/动画判断 `status == 'failed'` → 服务端 `error` 不触发。
3. `agent/guga_agent.py`：用户中止时建议补 `"aborted": true`，语义更明确（当前靠 note 前缀兜底）。

## 9. 与客户端最新包（`GUGA-Desktop-20261107-完整性修复版.zip`，构建于 2026-11-07 23:55）的调用对照

已核对包内 `core/butler_cloud.py`、`core/local_tools.py`、`core/local_agent.py`、`agent/guga_agent.py` 的调用形状（包内业务代码经 armor 加固，无法直接反查源码；以上模块源文件均早于包构建时间，按同版本对照）。字段层面**三条错误码、清单上报、领单/回执全部一致**，差异只在“谁真的会传参数”：

| 项 | 服务端 | 桌面包（最新包） | 一致性 |
|---|---|---|---|
| 清单上报体 | `POST /api/agent/inventory`，`{items:[{name,launch,version,path,summary,aliases,updatedAt}]}` | `core/local_tools.py` 同结构、同字段 | ✅ 一致 |
| 派单字段 | `device`（≤60，取设备 `id`）、`requiredTools`（≤10，camelCase，也认 `required_tools`） | `butler_cloud.dispatch()` 封装 `device`（≤60）+ `requiredTools`（≤10，未传时用 `tool_router.required_tools()` 按能力自动推导） | ✅ 字段一致 |
| 错误码识别 | `DEVICE_OFFLINE` / `NO_INVENTORY` / `TOOL_MISSING` | `butler_cloud.py` 三个 code 都有对应中文文案 | ✅ 一致 |
| **谁传 `device`** | 仅在请求带 `device` 时做定向路由 | **桌面 UI 没有任何设备选择器**：`ui/comp_window.py` 两处派单都是 `self._cloud.dispatch(text)`，从不传 `device` | ⚠️ 桌面包当前**走不到**跨设备三条分支 |
| **谁传 `requiredTools`** | 仅当 `device` + `requiredTools` 同时存在才校验清单 | 网页 `public/app.js`：点名设备时按任务推导 `requiredTools` 随单上报（先认点名的软件，否则按能力推载体，最多 2 个）；桌面端由 `tool_router.required_tools()` 推导 | ✅ 两端都会传，三条错误码网页端已可触发（沙箱实测见 §9.1） |
| 配对机器标识 | 接受 `device_id`，缺省按本体路径派生 `path:<sha1>` | `guga_agent.pair()` 只传 `code/device/selfcheck/path/caps`，不传 `device_id` | ✅ 可用（不同安装路径 = 不同设备） |
| 设备列表用哪个 id | 派单匹配只认 `agent.id` 或设备名，不认 `device_id` | 网页选择器用 `/api/agent/devices` 的 `id`；桌面无选择器 | ✅ 无冲突（但若未来改用 `/api/devices/inventory` 的 `device_id` 派单会报 `DEVICE_OFFLINE`，已在 §2.3 写明） |
| 进度/过程 | 服务端无 `steps` 字段；过程轨迹 = `task.log` + 子任务 `evidence[]`（`tag` 为步骤名） | 步骤明细只写在客户端本地台账 `TaskLedger`（`steps` 不上传服务端） | ⚠️ **字段差异：`steps` 仅客户端本地有，服务端台账查不到**；跨设备排查请看 `task.log` + `evidence` |

结论：接口契约不需要改字段。桌面包要能跑跨设备三分支，客户端侧还需补设备选择器并在派单时传 `device`；网页端已补齐 `requiredTools`，三条错误码在沙箱里从网页真实点选均可触发（见 §9.1）。

### 9.1 网页端三条错误码实测（2026-11-08，沙箱 3996）

前置：4 台自造设备（A `PC-A-有WorkBuddy`［WorkBuddy、豆包］、B `PC-B-只有豆包`［豆包］、D `PC-D-未报清单`［无清单］、E `PC-E-有WorkBuddy`［WorkBuddy］），任务均为「用 WorkBuddy 做一份项目汇报PPT」，网页派单按点名软件推出 `requiredTools=["WorkBuddy"]`。三次均未落单（`data/tasks.json` 未生成）。

1. `DEVICE_OFFLINE`（选 A 后让其心跳停跳 30 秒）
   ```
   ⚠ ［DEVICE_OFFLINE］所选设备「PC-A-有WorkBuddy」的本体已离线，这单没有悄悄改派。
   当前在线：PC-E-有WorkBuddy、PC-D-未报清单、PC-B-只有豆包。
   本单需要：WorkBuddy → 可换到 PC-E-有WorkBuddy（WorkBuddy），或去「PC-A-有WorkBuddy」重新启动咕嘎本体。
   ```
2. `NO_INVENTORY`（选 D）
   ```
   ⚠ ［NO_INVENTORY］所选设备「PC-D-未报清单」还没上报软件清单，无法确认它装了什么。
   本单需要：WorkBuddy → 已具备的在：PC-E-有WorkBuddy（WorkBuddy）。
   让「PC-D-未报清单」的本体启动一次即可自动上报清单。
   ```
3. `TOOL_MISSING`（选 B）
   ```
   ⚠ ［TOOL_MISSING］所选设备「PC-B-只有豆包」上缺：WorkBuddy。
   具备WorkBuddy的在：PC-E-有WorkBuddy（WorkBuddy） → 换到那台派单，或先在「PC-B-只有豆包」装好再派。
   ```

配套前端行为：点名设备掉线后，选择器不再悄悄清空/改派，而是保留该项并标注「已离线」，派单时由服务端如实回 `DEVICE_OFFLINE`。
