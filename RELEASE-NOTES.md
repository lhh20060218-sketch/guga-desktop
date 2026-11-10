# RELEASE-NOTES

## 2026-11-09 上一步正文不再被模板顶掉、粘贴后通读校验（20261110t）

本包 **20261110t** 在 `20261110s4` 之后构建；桌面已有的
`20261109j`、`20261109k`、`20261109o`、`20261110k`~`s`、`20261110s3`、`20261110s4`
均未覆盖。

### 本批修复

1. **上一步正文不再被固定模板顶掉**：新增 `core/handoff_prompt.py`，
   豆包/WorkBuddy/JoyCode 及所有走 `core/adapter_chain.py` 的派单统一调用
   `compose()`；固定指令只做前缀/后缀，正文必须与本步要求同段；
   空正文/过短交接中止并报 `handoff_missing` / `handoff_too_short`，
   组装后回读断言正文首尾各 40 字，缺失报 `handoff_not_embedded`。
2. **输入后必须通读校验**：新增 `core/paste_verify.py`，统一执行
   「清空 → 粘贴 → 回读 → 最多 3 次重试 → 恢复剪贴板」；整体归一化比对，
   不一致报 `input_verify_failed`（附期望/实际长度与首尾差异），
   剪贴板被第三方改动报 `clipboard_conflict`，绝不带错内容继续提交。
3. **暂停/中止闸门接入粘贴链路**：`paste_verify` 在每次清空/粘贴/回读前
   调用 `input_guard.assert_active()`；暂停时一个事件都不发，中止时抛 `Stopped`。
4. **`core/input_guard.py` 恢复**：按事故前冻结包（`build/guga-exe` 与
   `20261109j` 包内 PYZ，两处字节码 SHA256 一致）逐函数还原，
   27 个 code object 逐项 0 差异。
5. **自检版本**：`CHECK_VERSION` 升为 `t-1`（项数仍 27），构建闸门校验包内一致。

## 2026-11-09 取正文滚到底、复制锚点三级兜底（20261110s4）

本包 **20261110s4** 在 `20261110s3` 之后构建；桌面已有的
`20261109j`、`20261109k`、`20261109o`、`20261110k`~`r`、`20261110s`、`20261110s3`
均未覆盖。`20261110s2` 仅用于内部验证，未作为交付包发布。

### 本批修复（s3 e2e 暴露的两道坎）

1. **滚动到底（不再固定 10 格）**：`_scroll_to_bottom` 改为有界循环，
   每轮滚 6 格后判“回到底部”箭头消失或帧指纹+文本连续两轮不变，
   硬上限 12 轮 / 35 秒；每轮截图存证 `09_scroll_NN.png`。
2. **复制锚点三级兜底**：UIA 结构里的回答区「复制 / 更多」按钮优先，
   OCR 锚点（免 / 今 HH:MM）只作补充，最后在消息容器内 Ctrl+A/Ctrl+C；
   实际走通的路径写入 `result.json` 的 `copied_from` / `copy_paths`。
3. **`capture_empty` 说清缺什么**：气泡“缺什么”填具体缺失项
   （UIA 未找到复制按钮 / OCR 词表无锚点 / Ctrl+A 未取到文字，或
   已复制但与页面 OCR 重合率不足），不再把失败码当缺失项；
   修掉外层模板与以句号结尾的 hint 拼成「。。」的问题。
4. **自检版本**：`CHECK_VERSION` 升为 `s4-1`（项数仍 27），构建闸门校验包内一致。

## 2026-11-09 失败码分层、注入异常结构化、诊断包强制带上失败时段（20261110s3）

本包 **20261110s3** 在 `20261110s` 之后构建；桌面已有的
`20261109j`、`20261109k`、`20261109o`、`20261110k`~`r`、`20261110s` 均未覆盖。
`20261110s2` 仅用于内部验证，未作为交付包发布。

**自检通过 ≠ 派单可用**：自检里的 `windows_ocr` 通过、
`SendInput` 自检“通过”只说明组件能加载；现场已证实 q 包的注入路径仍然必坏
（签名被污染后 `SendInput` 自检本身不受影响）。判断能不能用只看端到端两步是否真跑通、
第 2 步是否有真实 PPT 产物，任何“自检通过”都不能替代这条。

### 本批修复

1. **真实停因不再被改写成 OCR 不可用**
   - `OCR_DEPENDENT_CODES` 移除 `send_not_confirmed`：字符已注入、composer 已清空但
     没有新回合时，回执保持 `send_not_confirmed`，文案提示“先重启豆包再派单”，
     不再误导用户去装中文 OCR 语言包。
   - `ask()` 收尾只对“确实因 OCR 读不到”的码补缺什么/去哪补；真实停因的
     `hint / missing / where / next_action` 原样透出。
2. **`ocr_empty` 独立码**
   - `ocr_engine.run_on_image()` 识别成功但 0 行 / 0 字时返回 `kind='empty_text'`，
     不再落 `recognition_failed`；上层据此报 `ocr_empty`（等待产物阶段），
     与 `adapter_exception`、`window_blank` 分开。
   - `probe()` 对自检图的空结果归一为引擎不可用（`probe_empty`），避免
     “空文本=OCR 正常”的误判。
3. **目标窗口异常专门码 `target_window_abnormal`**
   - 触发信号：抓帧白屏/渲染异常；窗口与虚拟屏幕交集 < 60%；UIA 页面地址命中
     `/skills`、`/setting`、`/plugin`、`/discover`、`/mall` 等非对话页。
   - 文案带实测证据（页面地址、窗口 rect、屏幕尺寸、可见比例），明确告诉用户
     “重启豆包后重新派单”，不再只说“发送未确认”。
   - `failure_report` 增加该码的阶段与下一步；`send_not_confirmed` 文案补上
     “页面字数停在 N、发送前基线 M”，指向更具体。
4. **配置缺失不再只剩白框**
   - 启动自检窗口在 `__init__` 同步计算配置状态条（先于任何线程显示）：
     缺 `ai_config.json`、Key 为空、Key 含空白/不可用、配置 JSON 损坏、
     配置目录不可写时，直接显示“缺哪项 / 去哪补 / 不补的后果”。
   - 新增 45 秒看门狗：自检线程一条结果都没回来时，摘要改为可照做的提示
     （退出重开 / 导出诊断），不再挂空白窗口。
5. **`ctypes.ArgumentError` 归为 `injection_failed / stage=inject`**
   - 现场：`ArgumentError: argument 2: TypeError: expected LP_INPUT instance
     instead of INPUT_Array_122`（61 字符 × 2 次按键 = 122 元素数组）。
   - `failure_report.classify_exception()` 统一识别 `ctypes.ArgumentError` 与
     `expected LP_*` 签名不匹配；`self_agent` 在内层/外层异常处都写
     `last_tool_failure`（code / stage / raw / next_action / exception_type），
     气泡走四段式：失败码 `injection_failed`、阶段 `inject`、原始异常完整文本、
     下一步“检查输入框焦点 → 目标窗口切前台 → 重试注入 → 仍失败重启该软件”。
   - 不再出现“未归类异常”这类对用户无效的措辞。
6. **诊断包强制带上失败任务时段**
   - 导出器先用任务台账/证据 `result.json` 的 mtime 算出最近一次任务起跑时刻，
     把日志窗口从固定 30 分钟扩到该时刻；`adapter_chain.log` 里失败时段的停因
     不会再被漏掉。
   - 同一时间窗内的 `result.json` 强制打包到 `task-results/<来源>/`，
     manifest 增加 `task_results` 与 `logs.window_extended_to_task`。
   - 同步更新 UI 文案与说明文档。

### 回归

- `tools/test_doubao_rect.py`：11 例（rect 归一 6 + 失败码 5）全 PASS。
- `tools/test_injection_failure.py`：4 例（ArgumentError / TypeError 签名 / 无关异常 / 完整 explain_failure 链路）全 PASS。
- `tools/test_diagnostic_window.py`：2 例（任务 result.json 强制入包 / 日志窗口扩到任务起点）全 PASS。


## 2026-11-09 修复豆包 UIA rect 字典形态导致第 1 步 KeyError（20261110s）

本包 **20261110s** 在 `20261110r` 之后构建；桌面已有的 `20261109j`、`20261109k`、
`20261109o`、`20261110k`、`20261110l`、`20261110m`、`20261110n`、`20261110p`、
`20261110q`、`20261110r` 均未覆盖。

### 相对 r 修复（s 批次）

1. **豆包适配器 UIA 降级时 `_uia_input_anchor` 把字典 rect 当序列索引**
   - 现场（r 包，第 1/2 步豆包约 2.8 秒失败）：
     `第 1/2 步（豆包）失败：KeyError: 2。缺什么：adapter_exception。`
   - 栈：
     `core\adapters\doubao_adapter.py, line 672, in _ui_attempt`
     `core\adapters\doubao_adapter.py, line 1031, in _uia_input_anchor`
   - 根因：`uia_service.snapshot()` 返回的元素 rect 是字典
     `{"left":131.0,"top":0.0,"right":1337.0,"bottom":720.0}`；
     `len(dict) == 4` 让 `len(rect) != 4` 检查失效，随后 `rect[2]` 抛 `KeyError: 2`。
   - 修法：新增 `_rect_box()` 统一归一化 dict / list / tuple，字段缺失、非数字、
     尺寸为 0 一律返回 None 并按原逻辑跳过；不吞异常，不改变 UIA 降级路径。
   - 全仓同类写法排查：`joycode_ui.py:300`、`app_registry.py:1053`、
     `screen_share.py`、`computer_control.py` 使用的都是
     `win32gui.GetWindowRect` / `window_inventory` 的 list/tuple，
     不是 UIA 字典 rect，无同类隐患。
   - 新增回归：`tools/test_doubao_rect.py`（6 例：dict / list / tuple / None / 空 /
     尺寸为 0 / 字典 rect 定位不抛异常 / 无效 rect 跳过）。
2. **OCR 空文本与适配器异常分开报码**
   - 真实豆包窗口 OCR 返回 `{"lines":[],"text":""}` 时，新增失败码 `ocr_empty`
     （阶段「等待产物」），不再和 `adapter_exception` / `window_blank` 混在一起；
     气泡提示与 `result.json`、`adapter_chain.log` 均能看到 `ocr_empty`。
3. **自检版本**：`CHECK_VERSION` 升为 `s-1`（项数仍 27），构建闸门校验包内一致。

## 2026-11-09 自检不再污染派单键盘输入（20261110r）

本包 **20261110r** 在 `20261110q` 之后构建；桌面已有的 `20261109j`、`20261109k`、
`20261109o`、`20261110k`、`20261110l`、`20261110m`、`20261110n`、`20261110p`、
`20261110q` 均未覆盖。

### 相对 q 修复（r 批次）

1. **启动自检给 SendInput 设全局签名，派单按键时类型冲突**
   - 现场（q 包测试机，14:30:55，elapsed_ms=10477）：
     `第 1/2 步（豆包）失败：ArgumentError: argument 2: TypeError:
      expected LP_INPUT instance instead of pointer to _INPUT。缺什么：adapter_exception。`
   - 根因：`core/env_check.py` 的 `_sendinput_check` 直接改
     `ctypes.windll.user32.SendInput.argtypes`（进程级缓存对象），用的是自检里临时定义的
     `INPUT`；测完不还原。`core/computer_control.py` 的 `_send_keys`（快捷键）与文字批量输入
     用的是另一个 `_INPUT`，把 `byref(_INPUT)` 传给已绑定 `POINTER(INPUT)` 的函数，
     ctypes 抛 `ArgumentError`。启动闸门在本进程内跑自检（`ui/startup_gate.py`），
     所以“打开软件”正常（本地快捷指令不按键）而复合任务第一步就断。
   - 修法：
     - 自检改用私有 `ctypes.WinDLL('user32', use_last_error=True)`，**不碰全局签名**；
     - 派单侧用私有实例，并在每个 `SendInput` 调用点显式绑定自己的结构签名（幂等）：
       `_send_keys` 绑定 `POINTER(_INPUT)`，文字批量输入绑定 `POINTER(INPUT)`。
   - 新增回归：`tools/test_sendinput_signature.py` —— 同一进程先跑自检 sendinput，
     再 `computer_control._send_keys([65])`。修复前实测复现上述 `ArgumentError`；
     修复后 `selfcheck_state=pass value=1`、`send_keys_ok=true`、退出码 0。
   - 新增冻结包自测入口：`GUGA-Desktop.exe --sendinput-selftest-json <out.json>`，
     在同一冻结进程里先跑自检再真实按键，结果写 JSON。
2. **自检版本**：`CHECK_VERSION` 升为 `r-1`（项数仍 27），构建闸门校验包内一致。
3. **401 未改逻辑**：现场凭据指纹 `长度 49 · 前四 a161 · 后四 XGR0 · 来源 main`，
   不符合 `sk-` 形态；这是服务端拒绝凭据，不是代码 bug。q 已提供
   「验证 Key（直连/系统代理）」与两组状态码/耗时/打码片段，r 保持该行为。

### 本轮本机验证

- `python tools/test_sendinput_signature.py`：修复前 `ArgumentError: argument 2:
  TypeError: expected LP_INPUT instance instead of pointer to _INPUT`；修复后
  `selfcheck_state=pass level=ok value=1` / `send_keys_ok=true keys=[65]` / `EXIT=0`。
- `py_compile`：`core/env_check.py`、`core/computer_control.py`、`tools/comp_entry.py`、
  `tools/test_sendinput_signature.py` 全部 exit 0。
- 冻结包内实测与构建闸门结果见本次构建回报。

### 仍未验证（不得写成通过）

- 测试机真实豆包适配器第一步未在本机复跑（本机无该测试条件），只用同一 `SendInput`
  调用链的冻结包自测替代。
- 测试机 401 的 Key 是否可在服务商侧恢复（需在服务商控制台核对，不在代码内）。

## 2026-11-09 模型凭据排障与云端入口（20261110q）

本包 **20261110q** 在 `20261109o` 之后构建，并已包含此前 `20261110p` 的全部改动
（405 剩余产生路径、`app_not_found` / `access_disabled` 四段失败文案、探针统一走
`model_endpoint.post()` 等）。桌面已有的 `20261109j`、`20261109k`、`20261109o`、
`20261110k`、`20261110l`、`20261110m`、`20261110n`、`20261110p` 均未覆盖。

### 相对 o 新增 / 修复（q 批次）

1. **Key 清洗（读、写、legacy 迁移三条路径）**
   - 新增 `clean_api_key()`：去 BOM、零宽字符、首尾空白；Key 中间仍有空格/换行时
     直接报“中间含有空白或换行（清理后长度 N）”，**不发出请求**。
   - `read_config` / `write_config` / `remember_config` / `adopt_legacy` 全部经统一
     清洗入口；坏 Key 写入抛 `ApiKeyError`，不会把坏 Key 落盘。
   - `SelfAgent._request()` 使用前再兜底洗一次，覆盖手工改文件、旧配置、云端下发。
2. **401/403 三类区分**
   - `exception_evidence` 现在读取上游响应体，**先脱敏再截断 240 字**作为 detail；
     `http_failure` 按 `invalid/unauthorized`、`permission/model_not_found`、
     `quota/balance/insufficient` 三类给不同标题与下一步；无法归类时显示打码原文。
   - 脱敏连 `Authorization:` 头名一起抹掉；诊断 URL 去掉 userinfo/query。
3. **设置页「验证 Key（直连/系统代理）」**
   - 探测逻辑抽成 `model_endpoint.probe(config)`，`tools/comp_entry.py --model-probe-json`
     与设置页共用同一份实现；界面只显示模式、状态码、耗时、打码片段。
   - 401 文案明确指向该按钮；直连与系统代理结果不同时提示代理可能是失败来源。
4. **错误文案带凭据指纹**
   - 失败文案追加：`本次凭据：长度 N · 前四 XXXX … 后四 XXXX · 来源 main/fallback/legacy`。
   - 用户可据此和上一份能通的配置逐项对比；四项一致仍 401，说明不是换 Key。
5. **云端账号入口常驻**
   - 桌宠右键新增「☁ 云端账号（可选）…」，不依赖 `_cloud.enabled`；复用首启向导的
     服务地址/账号/密码/「测试登录」，空配置时写明“不影响本地任务，只影响派单/跨设备”。
   - `ButlerCloud.reload()`：保存后重新登录并重建菜单；原“检查 ai_config.json 的 cloud 段”
     文案全部换成可照做的菜单路径。

### 本轮本机验证

- 11 个改动源码文件（含本轮 `env_check.py` 自检版本号）`py_compile` 全部通过。
- 自测脚本：Key 清洗四例（BOM+零宽、中间换行、中间空格、正常）、写/读/legacy 迁移、
  401/403 三类标题与下一步、detail ≤240 字、Authorization 不出现、probe 两模式、
  main/legacy/fallback 指纹来源，全部通过。
- `comp_entry.py --model-probe-json` 真实网络：直连 200 / 系统代理 200，指纹
  `长度 115 · 前四 sk-w · 后四 xNxw · 来源 main`，与用户“昨晚用的也是这个”一致。
- `tools/test_voice_assistant.py` 16/19 通过；剩余 3 条是上一轮遗留的过期断言
  （一条 fixture 未填 model，在 `model_config_error` 处失败；两条仍期待“工具N次”旧文案），
  与本次改动无关。

### 仍未验证（不得写成通过）

- 测试机真实 401 响应体的三类归类：只做了桩响应，未拿到该机实际 body。
- 云端账号弹窗真实登录：本机无云端账号，仅验证构造/按钮/静态取值。
- 保存云端账号后的桌宠菜单即时刷新：仅静态与构造检查，未在真实桌宠进程点开验证。

## 2026-11-09 测试机五类未收口问题复核与修复（20261110p）

在 20261109o / 20261110n 基础上继续只做增量复核；本轮**出了新包 20261110p**，
桌面已有的 `20261109j`、`20261109k`、`20261109o`、`20261110k`、`20261110l`、
`20261110m`、`20261110n` 均未覆盖。

1. **405 的剩余产生路径与诊断分叉**
   - 全仓复查 POST 链路后，只剩 `core/bg_agent.py` 仍把 `base_url` 原样拼接
     `'/chat/completions'`：用户把完整端点粘进 `base_url` 时会变成双段路径，
     服务端回 404/405。现在与主链路共用 `model_endpoint.normalize_base_url()`，
     非法地址统一返回 `invalid_endpoint`，不再崩成未归类异常。
   - `normalize_base_url()` / `base_of()` 是全部模型调用的公共入口，旧版遇到
     `https://[invalid` 这类手填地址会直接抛 `ValueError`。现在返回可照改的
     `error`，不会让整条任务以“未归类异常”中断。
   - `tools/comp_entry.py --model-probe-json` 的探针改用与主链路相同的
     `model_endpoint.post()`：重定向后仍用 POST，并把重定向链写进 JSON。
     旧探针用 `requests.Session` 自动跟随重定向，301/302 后方法被改成 GET，
     会把“探针自己造成的 405”误报成网关/账号问题，与真实请求结论不一致。
2. **软件名查不到 / 完整访问未开启的失败信息**
   - 测试机复合任务中，模型猜了“Google Chrome”但本机未授权，失败被格式化成
     “未归类：未知异常类型”，下一步还建议“重启目标软件”，完全误导。
     现在 `app_not_found`、`access_disabled` 进入统一失败码表：
     四段文案明确“改准确名称 / 到「接入面板 → 新增软件」填路径 / 到「软件权限」
     勾选完整访问”，不再出现未归类占位。
   - `applications.open` 在工具边界捕获 `AppResolutionError`，保留 code /
     stage / 原始异常 / 下一步，不把裸异常交给模型自由解释。
3. **复核对 4 轮上限、视觉模型、豆包状态的结论**
   - 轮数上限定义在 `SelfAgent._step_limit()`：例行任务 12 轮、非例行 80 轮，
     命中后 `paused` 并保存检查点，可回复“继续”。源码已不是 4 轮；测试机若仍
     提示 4 轮，说明跑的是旧包（j 及更早）。
   - `qwen3-vl-plus` 单模型可同时覆盖对话/拆解/截图理解；也支持单独配置
     `vision_base_url / vision_model / vision_api_key`，两者都走同一套归一化。
   - 豆包 HTTP `initialize + tools/list` 握手后 `channel_status('doubao')`
     与自检、接入面板同源为 `connected`，不再出现“握手成功但面板未接入”。

### 本轮本机验证

- `tools/verify_model_compat.py`：**32 项全部通过**（新增 app_not_found 四段、
  access_disabled 四段两项）。
- `test_bg_agent`（29 项）、`test_desktop_access`（7 项）、`test_task_router`（7 项）
  全部通过。
- `tools/comp_entry.py --model-probe-json`：直连/系统代理两条链路均
  `POST 200`，`redirects=[]`，模型 `qwen3-vl-plus`，证明探针与主链路一致。
- `tools/verify_doubao_handshake.py`：真实 MCP 握手后状态为 `connected`。

### 仍未验证（不得写成通过）

- 测试机 Win11 上真实企业代理/安全软件导致的 405 未复现（本机无该环境）。
- 真实 qwen3-vl-plus 流式分片与 `finish_reason` 形态仍需测试机确认。
- 豆包“工作”模式下的人工点击接入全流程未在本轮重新实测。

## 2026-11-10 五类问题后续收口（20261110n）

在 20261110m 基础上继续只做增量修复；本轮**出了新包 20261110n**，
桌面已有的 `20261109j`、`20261110k`、`20261110l`、`20261110m` 均未覆盖。

1. **视觉模型单独配置的地址归一化**
   - `normalize_config()` 之前只归一化 `base_url`，`vision_base_url` 保留原样。
     用户把视觉端点粘贴成 `.../chat/completions` 时，「重新探测档位」会拼成
     `.../chat/completions/chat/completions`，面板误报 404/405，而真实截图链路
     因 `screen_visual` 自己归一化反而能用——结论与真实能力分叉。
     现在 `base_url` / `vision_base_url` 走同一套归一化。
   - `model_capability._post()` 改为和 `SelfAgent._request()` 共用
     `model_endpoint.base_of()`，能力探测和主链路保证打到同一地址。
2. **未归类异常的无信息失败文案**
   - 执行器抛出 `Exception` 且异常文本为空时，旧版会落到
     “执行器没有提供明确原因”，违反“失败必须带异常类型与首行消息”的约定。
     现在输出“未归类异常 <类型>：<首行消息或无异常文本>”。
3. **回归测试与实现漂移**
   - `test_execution_contract` 完成门用例按“输入后自动复查”补回执；
     `test_agent_council`、`test_companion_modes` 的模型配置补 `model` 字段，
     避免 `require_model_config` 先抛错导致用例假失败。

### 本轮本机验证

- `tools/verify_model_compat.py`：**30 项全部通过**，在 m 版 25 项基础上新增：
  `vision_base_url` 归一化、独立视觉目标归一化、能力探测与主链路同一地址、
  代理对 POST 回 405 时自动绕代理重发成功、空异常文本仍带异常类型。
- `test_execution_contract`（8 项）、`test_agent_council`（3 项）、
  `test_companion_modes`（22 项）全部通过。
- `tools/verify_doubao_handshake.py`：真实 MCP `initialize + tools.list` 后
  `channel_status('doubao') == connected`（对话状态、自检、接入面板同源）。
- 自检版本 `n-1`，项数仍为 27；构建闸门会校验包内自检版本/项数与源码一致。

### 仍未验证（不得写成通过）

- 真实企业代理环境下的 405：本机用临时 HTTP 代理模拟“代理回 405”，
  自动绕代理重发已验证；真实公司代理策略仍未在测试机上实测。
- 真实 qwen3-vl-plus 网关的流式分片形态：本机用模拟网关复现 SSE 分片、
  `reasoning_content`、`finish_reason=tool_calls`；真实网关仍需在测试机上确认。
- 视觉模型单独配置时，真实视觉模型对截图的识别质量未实测（仅验证路由与地址）。

## 2026-11-10 测试机未收口项继续收口（20261110m）

在 20261110l 基础上继续排查五类已知问题；本轮**出了新包 20261110m**，
桌面已有的 `20261109j`、`20261110k`、`20261110l` 均未覆盖。

1. **405 剩余代码路径**
   - `agent/guga_agent.py` 的云端 `api()` 仍直接用 `urllib.request.urlopen` POST：
     301/302/303 后 urllib 会把 POST 改成 GET，云端 http→https 或补斜杠跳转时可能回 405。
     现改为 `model_endpoint.urlopen_post()`，保留方法、请求体和请求头。
   - `model_endpoint.base_of()` 新增回归：`.../v1/?foo=1`、`.../v1/chat/completions?x=1`
     都能还原成 `.../v1`，不再拼出双段路径或带查询串的怪地址。
   - 模型、视觉、云端大脑、后台任务、首次配置页的 POST 已全部走
     `model_endpoint.post/urlopen_post`；405 且检测到代理时会自动 `trust_env=False` 重试。
2. **“达到 4 轮上限”的真正残余：20 秒总预算**
   - 源码轮数虽已改为 12，但简单指令仍沿用旧的 `budget=min(budget,20)`：
     真实网关单次 2 秒左右时，第 10 轮就被“长任务预算”截断，看起来仍像“4 轮上限”。
     现改为 `routine_budget_seconds`（默认 90 秒，30–600），12 轮能完整跑完；
     到上限仍只暂停并保存检查点，可回复“继续”。
   - 流式/非流式混用再补两处：网关每个分片重复完整工具名时不再拼成
     `computercomputer`；标准 JSON 的 `content` 为分片数组时摊平成字符串，
     避免下一轮请求带非法结构反复失败。
3. **豆包握手状态与自检口径一致**
   - 之前自检只认 `state=connected`；若豆包只完成 `initialize`、还没 `tools/list`，
     面板已显示“已握手、暂不判定已接入”，自检却仍写“缺少 豆包”。
     现在自检把 `client_handshake_no_tools` 单列为“已握手，未枚举工具”，
     不再并入“缺少/未接入”，也不冒充“已接入”。
4. **视觉模型单独配置后的能力评估**
   - 主模型是纯文本、但已配置 `vision_model` / `vision_base_url` / `vision_api_key` 时，
     能力评估仍拿主模型去判视觉，界面会误报“看不了截图”。
     现在 `_vision_static` / 视觉探测都改测单独配置的视觉目标，评估与真实链路一致。
5. **无 Key 的“打开软件”边界**
   - 首次启动无 Key 提示补充明确清单：打开/关闭软件、打开网页、窗口切换、音量等本地指令
     无需 Key；只有对话、任务拆解、截图理解需要 Key。“打开软件”没说是哪个时仍只追问，
     不猜目标、不走派单。

### 本轮本机验证

- `tools/verify_model_compat.py`：**25 项全部通过**，覆盖：
  旧 405 根因复现、`post()` / `urlopen_post()` / 云端 `api()` 重定向后仍为 POST、
  qianwen 兼容端点归一化（含查询串/结尾斜杠）、405 自救文案、SSE 分片合并、
  `reasoning_content` 空轮纠偏、重复工具名与分片 `content`、单模型/独立视觉、
  12 轮上限、20 秒后仍跑满 12 轮（实测 21.7 秒）、无 Key 打开指令、握手-only 自检口径。
- `tools/verify_doubao_handshake.py`：真实 MCP `initialize + tools/list` 后
  `channel_status('doubao') == connected`。
- 自检版本保持 `m-1`，项数仍为 27；构建闸门会校验包内自检版本/项数与源码一致。

### 仍未验证（不得写成通过）

- 测试机 Win11 上的真实代理/重定向 405：本机只做了桩复现与请求方法断言，未拿到该机代理日志。
- 真实 `qwen3-vl-plus` Key 的联调：仓库无可用 Key，本轮全部用本地桩。
- 真实豆包桌面端的握手：本轮用 MCP SDK 客户端模拟真实 initialize + tools/list，
  未在豆包界面上复测。

## 2026-11-10 测试机未收口项出包（20261110l）

在 20261110k 基础上继续处理测试机未收口项；本轮**出了新包 20261110l**，
桌面已有的 `GUGA-Desktop-win64-20261109j.zip` 与 `20261110k` 均未覆盖：

1. **405 剩余代码路径**
   - `screen_visual._call_zhipu`、`core/vision.py` 原来直接 `requests.post`，302 后会被
     requests 改成 GET，只接受 POST 的视觉端点返回 405；现已统一走
     `model_endpoint.post()`。
   - `bg_live._vision_json` 原来直接拼 `config['base_url']`，用户粘贴完整
     `/chat/completions` 时会得到双段路径；现已先 `base_of()` 归一化。
   - 首次配置页的对话/云端测试原来用 `urllib.request` POST，urllib 在 301/302/303 后
     会改 GET；现已统一走 `model_endpoint.post()`。
   - `model_endpoint.post()` 新增：405 且检测到系统/环境代理时，自动 `trust_env=False`
     再发一次，响应带 `guga_proxy_bypass` 标记。这样“代理改写 POST 导致 405”的机器
     不必手工配 NO_PROXY。
   - 云端 JSON POST（`butler_cloud._call`、`agent/guga_executor._api`）改用
     `model_endpoint.urlopen_post()`：urllib 在 301/302/303 后同样会改 GET，云端
     http→https 或补斜杠跳转时可能被回 405；现在保留方法、请求体和请求头。
2. **轮次上限与新模型返回形态**
   - 短提示 routine 预算 8 → 12（`core/self_agent.py` 的 `step_limit`），复合任务仍为
     `agent_step_limit` 默认 80；上限文案现在说明“简单指令默认12轮 / agent_step_limit=N”
     以及如何继续或调高。
   - `_request` 新增 SSE/`delta`/tool_calls 分片合并，兼容网关在 `stream=False` 时仍返回
     流式分片的情况。
   - `reasoning_content` 只有推理、或 `finish_reason=tool_calls` 却没有调用时，不再直接
     判死：同一执行轮内自动关闭 thinking 并追加系统纠偏，重发一次；仍为空才报明确错误。
3. **豆包握手状态与面板一致**
   - 真实 HTTP 客户端 `clientInfo.name` 不在别名表时（如 `Coze` / `MCP Client`），
     仍写 `doubao.json` 证据并标记 `client_unidentified`；面板/自检显示
     “已接入（客户端名称未识别）”，不再显示“未接入”。
   - `tools/list` 证据拆成 `client_tools_listed_at`（真实客户端）和 `tools_listed_at`
     （自检），避免自检的工具枚举替豆包凑“已接入”的第三个条件。
   - `tools/verify_doubao_handshake.py` 新增 `--client-name`，可回归未识别名称场景。
4. **无 Key 的“打开软件”边界**
   - `打开软件/打开应用/打开程序` 不再报“没找到‘软件’”，改为明确追问要打开哪个软件；
     该失败码 `target_ambiguous` 不触发模型派单、不需要 Key。
   - `tools/comp_entry.py --fast-command-json` 的 `key_required` 只在本地未命中时为真，
     与界面实际行为一致。
5. **本轮（l 出包前）追加**
   - 冻结的 k 包实测复现了“豆包握手成功但面板/自检显示未接入”：k 包构建时间早于
     服务端 `initialize/tools-list` 证据修复。l 包重新打包后，用
     `tools/verify_doubao_handshake.py --exe` 对包内 exe 实测，状态为 `connected`。
   - 达到检查点/轮数上限时原来报“已暂停”却把任务记为 failed，界面不给“继续”；
     现统一抛 `TaskPaused`，结果 `paused=True`，与提示文案和“继续”恢复链路一致。
   - 新增 `tools/verify_model_compat.py`：本机起临时网关，真实调用
     `model_endpoint.post` / `SelfAgent._request` / `fast_commands` 共 14 项断言，
     覆盖 405 重定向复现与修复、base_url 归一化、SSE 分片/推理空轮、视觉单模型、
     12 轮上限、无 Key 打开软件边界。
   - `tools/test_local_perception.py` 两个旧桩（仍 patch `self_agent.requests.post`、
     仍断言 8 轮）已更新到当前真实入口与 12 轮；全部通过。
   - 自检「外部软件」细节不再出现“未发现 无”这种占位文案：无缺失时显示
     “没有发现缺失项”，有缺失时逐项列出名称。

### 本轮本机验证

- 405 桩：旧 `requests.post` 复现 `POST→GET→405`；新入口 `POST→POST→200`；
  代理分支单测为 `trust_env=True(405) → trust_env=False(200)`，并通过。
- 云端 urllib：本地 302 跳转后目标端点收到的仍是 `POST` 且请求体 `{"a":1}` 未被改写。
- 首次配置页：构造 `requests.HTTPError(405)`，`describe_error` 能显示 HTTP 405、
  实际 URL、模型名、服务端原文与下一步，不再因 `requests.HTTPError` 没有 `.code`
  而退化成“网络不通”。
- SelfAgent：桩网关第一次只回 `reasoning_content`、第二次回正文 → 自动纠偏返回正文；
  桩网关返回两条 SSE `tool_calls` 分片 → 合并为 `{"action":"windows"}`。
- 视觉：只配 `qwen3-vl-plus` 时 `_accepts_images=True`、`vision_ready=chat`、截图请求确实
  带图片且使用同一模型；另配 `vision_model=qwen-vl-max` 时 `vision_ready=dedicated`。
- 豆包：`--client-name 豆包` 与 `--client-name Coze` 均 PASS（状态 `connected`，
  未识别名称有明确提示与证据文件）。
- 打开软件：`打开软件` → `target_ambiguous`、`key_required=false`；`打开计算器` →
  本地启动、`key_required=false`。
- 自检（源码模式，隔离 GUGA_HOME）：27 项，`pass=18 / degraded=2 / untested=7 / fail=0`，
  计数自洽；两个 degraded 为本机 125% DPI 与 307 字符长路径，与本次改动无关。

### 仍未验证（不得写成通过）

- 测试机 Win11 上的真实代理/重定向 405：本机只做了桩复现，未拿到测试机代理日志。
- 真实 `qwen3-vl-plus` Key 的联调：仓库内无可用 Key，本轮全部用本地桩。
- 真实豆包桌面端的握手：本轮用 MCP SDK 客户端模拟真实 initialize + tools/list，
  未在豆包界面上复测。

## 2026-11-10 405 代码级根因 / 视觉单独配置 / 打开指令边界（20261110k）

在 20261109k 基础上继续收口测试机反馈，本轮新增结论：

1. **405 多了一条代码级根因：重定向把 POST 改成了 GET**
   - 复现：本机桩服务对 `POST /v1/chat/completions` 返回 `302 → /v2/chat/completions`，
     `requests` 默认会自动跟随并在 301/302/303 后把 POST 改成 GET；最终地址只接受 POST，
     于是返回 **405**。独立用 POST 验证网关时永远看不到这个 405，与测试机现象一致。
   - 修复：新增 `core.model_endpoint.post()`，显式 `allow_redirects=False`，按 `Location`
     **保留 POST 重发**（最多 2 跳），跳转记录挂在 `response.guga_redirects` 供诊断。
     对话、任务拆解、截图理解、设置页测试连接、主动搭话、议会、后台任务全部换用该入口。
   - 405 现在会触发备用模型回落（有 fallback 时），文案补充“重定向/代理”两条与 Key 无关的原因。
   - 实测：同一桩服务，旧方式 `POST → GET → 405`，新方式 `POST → POST → 200`。
2. **单一模型字段能否覆盖对话 + 拆解 + 截图理解**
   - 能：只配 `api_key/base_url/model`（模型本身支持视觉，如 `qwen3-vl-plus`）时，
     三条链路都走同一目标，截图理解走 chat 后备链路。
   - 不能时现在可分开配：新增可选字段 `vision_base_url` / `vision_api_key` / `vision_model`，
     留空则跟随主模型；设置页新增「视觉模型（可选）」三项，首次配置页给出入口提示。
   - 同时修掉两个真实缺陷：
     - `SelfAgent` 调 `observe_frame(..., timeout=...)` 但函数没有该参数，异常被静默吞掉，
       独立视觉模型一直没被真正调用；
     - 旧逻辑把 `vision_model` 一律发给智谱端点，填 `qwen3-vl-plus` + 残留 `zhipu_api_key`
       时会把千问模型名发到智谱。现在按 provider 判定，不再混发。
3. **“达到 4 轮上限”**
   - 本地 `SelfAgent` 源码已是 routine 8 步 / 非 routine 80 步（k 包仍是 4，本轮会把源码一起打进包）。
   - 远程派单执行器 `agent/guga_agent.py` 的 `while rounds < 4` 是另一处硬编码，改为
     `GUGA_AGENT_ROUNDS`（2–12，默认 6），失败文案按实际上限输出。
   - `reasoning_content` 只推理不给正文时，明确报“只返回了内部推理”，不会空转；
     `finish_reason=length` 的流式回答会追加“被截断”的提示。
4. **“打开软件”边界**
   - `打开WorkBuddy生成照片` 之前被快速通道当成 `open_app`（目标变成“WorkBuddy 生成照片”），
     无 Key 时只会报“没找到这个软件”。现在“生成/创作/制作/设计/翻译/总结/整理/分析…”等
     复合动作一律交给派单链路；单纯“打开豆包 / 打开微信”仍不调模型、无 Key 可用。
5. `CHECK_VERSION` 保持 `k-1`（自检项数未变，27 项）。

### 本机验证（2026-11-09/10，隔离 GUGA_HOME）

- 405：桩服务复现 `POST→GET→405`，修复后 `POST→POST→200`；`SelfAgent` 405 + 备用模型
  实测自动切换并成功（`_fallback_reason=HTTP 405`）；无备用模型时报错带 405 自救文案。
- 视觉：只配多模态主模型 → `vision_ready=chat` 且截图理解 200；单独视觉配置 →
  `vision_ready=dedicated`、走独立端点、失败不重复请求；`zhipu_api_key` + 非 glm 模型
  不再发往智谱。
- 打开指令：`打开WorkBuddy生成照片`、`打开豆包然后写文案` 均 `matched=False`（走派单）；
  `打开豆包`、`打开不存在的工具XYZ` 仍为本地 `open_app`。
- 自检（源码模式）：27 项，`pass=18 / degraded=2 / untested=7 / fail=0`，计数自洽。
- 豆包 HTTP 握手回归：真实 `initialize` 后 `channel_status('doubao')` 为 `connected`。

## 2026-11-09 接入状态/405 自救/打开软件/4 轮预算（20261109k）

针对测试机（Win11 裸机，j 包）反馈的两类问题 + 一项新需求：

1. **豆包“握手成功却显示未接入”**
   - 根因：接入状态按 stdio 配置文件/陈旧 `unknown.json` 判定；豆包是 HTTP 连接器
     （客户端主动连 `127.0.0.1:<port>/mcp`），没有本地 JSON，且旧服务端只在启动时写
     自己的进程，从不记录客户端 `initialize`。
   - 修复：服务端在真实 `initialize` 时记录 `clientInfo.name`/版本/进程，写入接入面板读取的
     **同一目录**（`<workspace>/.guga/mcp-connections/<app_id>.json`）；咕嘎自检用
     `guga-selfcheck` 自报身份，不冒充豆包；面板新增三态：
     `通道已就绪，等待软件首次握手` / `曾连接过，当前未验证` / `已连接（真实握手）`。
2. **复合任务报 405（模型换 `qwen3-vl-plus` 后出现）**
   - 实测结论：该网关对错误路径返回 404、错误方法返回 400，**从不返回 405**；用
     `SelfAgent._request` 原样 payload（`temperature/max_tokens/thinking/reasoning_effort/
     tools/tool_choice`）打 `https://maas.qianwenaiapi.com/compatible-mode/v1` + `qwen3-vl-plus`
     → **200**，工具调用正常解析。405 来自配置/环境层（非 OpenAI 兼容地址、fallback 地址、代理）。
   - 修复：`base_url` 统一归一化（剥掉 `/chat/completions` 等后缀、按已知域名补路径），
     405 文案改为可自救：实际方法/地址 + “检查 base_url 是否形如 https://.../v1” +
     三个本机实测 200 的示例 + 代理排查；设置页显示“已自动校正地址”。
3. **“达到 4 轮上限”**
   - 根因：短提示（<100 字）被当成 `local_task` 闲聊，`step_limit=4`；但 prompt 点名了软件、
     有真实执行要求（`tool_mandate` / `requires_execution` 为真），observe→UIA→输入→核对
     根本走不完。
   - 修复：`_routine_request` 增加 `not mandate and not requires_execution` 判据；步数/操作
     预算改为可配置 `agent_step_limit`（默认 80，边界 4–200）/`agent_operation_limit`
     （默认 160，边界 6–500），routine 仍为 4/6。
4. **“打开软件”简单指令（新增）**
   - “打开豆包/WorkBuddy/JoyCode/已登记软件”走本地意图匹配，不调模型 → **无 Key 可用**；
     路径复用 `app_registry.launch_exe()`（自报路径优先）；已运行只切前台不起第二实例；
     未安装/路径失效给“接入面板 → 新增软件”的可照做提示，不静默失败。
   - 与派单严格区分：`打开豆包然后写文案` 仍走派单链路。
5. `CHECK_VERSION`：`j-1` → `k-1`。

### 本机验证（2026-11-09）

- 豆包三态（隔离 `GUGA_HOME`，真实 HTTP 服务 + 真实 MCP 客户端）：
  `未验证 → 通道已就绪（自检 5 工具）→ 已连接（客户端「豆包」，握手 1 次）`。
- 模型：`qwen3-vl-plus` 文本 200、强制工具调用返回 `tool_calls`、截图理解返回“红色”；
  405 桩（本机返回 405）触发自救文案，实测输出包含实际地址与三个已验证示例。
- 打开软件：`打开豆包` → 已运行（未起第二实例）；`打开不存在的工具 XYZ` →
  `app_not_found` + 接入面板指引。

### 可复现验证入口（k 包内）

- `GUGA-Desktop.exe --selfcheck-json D:\selfcheck.json`：包体检。
- `GUGA-Desktop.exe --model-probe-json D:\probe.json`：模型地址/方法/代理/状态码，
  不会输出 Key。
- `GUGA-Desktop.exe --fast-command-json "打开豆包" D:\open.json`：本地打开指令（无需 Key）。
- `python tools/verify_doubao_handshake.py --exe "D:\GUGA\GUGA-Desktop\GUGA-Desktop.exe"`：
  隔离环境跑豆包 HTTP 三态（未验证 → 通道就绪 → 已连接）。

## 2026-11-09 语音模型国内镜像加速（20261109j）

只解决 i 版遗留的“下载成功路径因打包机境外网络未验证”问题，其余能力不变（自检仍 27 项）。

- `--download-vosk-model` 改为**多源按序回退**：
  1. HuggingFace 国内镜像 `hf-mirror.com`（本机实测 43.9MB / 7.8 秒 / 5.6MB/s）；
  2. Vosk 官方源 `alphacephei.com`（境外，兜底）。
- 镜像 zip **固定 SHA256**（`2b34e3c3…434a`，2026-11-09 实测记录）：下载后校验，
  不通过自动换下一个源，绝不装来路不明的内容；官方源无固定值，靠解压后
  `am/`+`conf/` 结构校验 + 自检真实加载兜底。
- 每个源独立 30 秒读超时（i 版 `urlretrieve` 无超时、卡死永挂的缺陷一并修掉）。
- 本机端到端实测：镜像下载 → 解压 → `vosk.Model` 真加载 → `KaldiRecognizer` 出结果，
  自检第 9 项从「未测」变「通过」。
- `CHECK_VERSION`：`i-1` → `j-1`。

## 2026-11-08 独立复验整改（20261108i）

针对独立复验 h 包的 9 项结论（6 通过 / 2 未验证 / 1 未通过），逐条整改，不把问题解释成“不影响使用”。

### 一、必须修

1. **诊断包版本与 SHA 不再是“未知”**
   - 打包时写包内固定位置 `_internal/build-info.json`：`version=20261108i`、`check_version=i-1`、
     `build_sha`（源码快照摘要）、`package_content_sha256`（解压后可复算的内容摘要）、
     文件数/字节数/构建时间。
   - 诊断导出优先读它；同时在桌面/下载/安装包同级找原始 zip，**实测 zip SHA256**，
     并核对同名 `.sha256` sidecar。zip 内不可能包含自身哈希，因此 zip 实际 SHA 由 sidecar 记录，
     导出结果里的 `package_sha256` 与 `package_content_sha256` 来源分别标注，找不到就如实写“未找到”，不瞎填。
2. **自检 summary 计数自洽**
   - `summarize()` 只按 items 的 `state` 聚合（pass/degraded/fail/untested），level 计数移到独立
     `levels` 子字典，不再两套混加。
   - `--selfcheck-json` 断言 `state_total == items == check_count`，不成立时 **exit 3** 并写
     `summary_error`；构建闸门同时校验 `summary_consistent`，不成立直接拒绝产出。
3. **vosk 中文模型如实处理（选择方案 b：不随包）**
   - 自检不再拿开发机 `C:\Users\l\.zcode\tools\vosk-model-cn` 判通过，只认包内/用户数据目录；
     没有模型时标 **untested**，写明“首次使用需联网下载约 40MB”与下载入口。
   - 新增真实下载入口：`GUGA-Desktop.exe --download-vosk-model`（落点
     `%GUGA_HOME%\models\vosk-model-cn`），也可手动下载官方 zip 解压到该目录。
   - 说明书与作品介绍已删除“离线语音开箱可用”的承诺。

### 二、可信度/噪声

4. **`check_version` 与包版本对齐**：由 `g-2` 改为 **`i-1`**；构建闸门校验
   `build-info.version=20261108i` ↔ `check_version` 前缀 `i-` ↔ 包内 `--selfcheck-json` 三项一致。
5. **OCR 自检去噪**：`value.execution_policy` 只放可读执行策略；
   `Get-ExecutionPolicy` 的原始 stderr 移到独立字段 `value.execution_policy_error`。
6. **日志受 `GUGA_HOME` 控制**：`app_log.log_dir()` 改为 `guga_paths.BASE/logs`，
   默认 `%LOCALAPPDATA%\GUGA\logs`，设 `GUGA_HOME` 时写入 `%GUGA_HOME%\logs`；
   `--paths-probe-json` 增加 `log_dir_controlled_by_base` / `log_in_base` / `guga_home`。

### 三、不依赖真实模型 Key 的复验入口

- `GUGA-Desktop.exe --simulate-adapter-failure ocr_degraded --simulate-out D:\降级.json`
  用桩适配器跑**真实 `adapter_chain`**：第一步 OCR 不可用记为 degraded，第二步继续执行；
  结果 `assertions` 校验 `first_degraded / second_done / continued_after_ocr_failure`。
- `GUGA-Desktop.exe --simulate-adapter-failure adapter_exception --simulate-out D:\四段.json`
  输出失败码四段（失败码/阶段/原始异常/下一步），并校验无“（错误）”占位。
- 桩适配器不联网、不读 Key，复验方无需配置任何真实模型。

## 2026-11-08 WorkBuddy MCP 口径修订（20261108h）

只改文档与接入面板文案，能力/自检项数不变（仍 27 项，闸门 `包内 g-2 / 27 项 == 源码`）。

- **路径确认**：`%USERPROFILE%\.workbuddy\mcp.json` 为官方路径（官方文档写明，
  `app.asar` 的 `getMcpConfigPath()` 返回同一路径；真机点界面三重验证）。
- **生效方式**：外部直接改文件后必须**完全退出 WorkBuddy（托盘退出；关窗口无效）**再重启才刷新列表。
- **首次信任**：必须在「MCP 服务管理 → 我的 MCP」点**「信任」**，否则条目灰色、工具不启用；
  改 `command` / `args` / `env` 会让信任记录失效，需要**重新信任**。
- **V5.9.3 界面入口**：侧边栏「专家·技能·连接器」→ 连接器页右上角**铅笔图标** →
  「MCP 服务管理」→「＋添加 MCP」。它打开的仍是同一个 `mcp.json`，界面保存**立即生效、无需重启**。
- **固定目录告警**：`command` 不得指向 `%TEMP%` 解压目录（临时目录被清后失效，
  路径变化还会让信任作废）；先把咕嘎解压到固定目录（如 `D:\GUGA`）再生成配置。
- 接入面板 WorkBuddy 卡片改为读取声明里的 `ui_steps` / `restart_note`，
  写配置后的提示从“重启目标软件”改为“完全退出（托盘退出）后重启 + 首次需点信任”。

## 2026-11-08 裸机可信版（20261108g）

### 一、事故根因（已实测复现，不再推断）

- f 包内是旧的 13 项自检（dist 20:36），新 19 项自检在源码 21:43 写好但没打进包。
- 旧 OCR 自检只 `TryCreateFromUserProfileLanguages()` 建引擎就算“就绪”；
  真实派单走 `powershell -File windows_ocr.ps1`。
  在 `-ExecutionPolicy Restricted` 下：`-Command` 建引擎 203ms 通过，
  `-File` 返回 rc=1「在此系统上禁止运行脚本」。这就是“自检全绿、派单报 Windows OCR 不可用”。
- `adapter_chain` 里 `except Exception → step_failed → return` 中断整单；
  仓库 `except OcrUnavailableError` 0 处；`doubao_adapter` 第二次 `_ocr_words` 裸露在 try 外。
- 本机模拟 `$engine=$null` 与强制造识别抛错，均真实复现：
  新探测统一转为 `ocr_unavailable` 并保留 PowerShell 原文。

### 二、自检：27 项全部真实调用，禁止“只看文件/注册表”

- 每项真调用一次被检能力，拿真实返回值或真实异常才算测过；
  做不到实测标「未测」，不显示「通过」。
- 四态：实测通过 / 未测 / 降级 / 失败；降级与失败写清“缺什么 + 去哪补 + 补完是否重启”。
- 实测项包括：OCR（`-File` + 中文图 + 重合率 ≥90% + 显示执行策略）、
  UIA `FromPoint` 读真实控件、UIA 读目标软件、剪贴板 Unicode 回环、
  整屏截图非黑、`PrintWindow` 真像素、`EnumWindows`、窗口定位与前台归属、
  `SendInput`、`%TEMP%`、长路径、pywin32 真实 import（`_MEIPASS` 校验）、
  MCP 握手 5 工具、模型端点 DNS/TCP 轻探测、配置写入回环（中文+空格路径）、
  中文字体真渲染、麦克风真开流、vosk 真加载、ffmpeg 真执行、PPT 真生成。
- 自检窗四态样式 + 行内「重试」，失败项可单独重测。
- 打包闸门：`--selfcheck-json` 的项数/版本必须等于源码，不一致直接构建失败
  （防止再出现“源码改了、包里还是旧自检”）。

### 三、豆包去 OCR 硬依赖

- 读界面文本顺序：UIA（`ValuePattern` / `TextPattern`）→ 剪贴板回读 → OCR 兜底。
- OCR 不可用时降级继续：回执/证据标 `ocr_unavailable`，不抛 `RuntimeError` 打断复合任务。
- 失败码从 `adapter_exception` 改为 `ocr_unavailable`；
  「缺什么」写清 Windows OCR 语言包/WinRT 组件，「去哪装」给
  「设置 → 应用 → 可选功能 → 添加“中文(简体) 光学字符识别”」，「下一步」给“装好重启咕嘎后重派”。
- 复合任务（豆包→WorkBuddy）在 OCR 不可用机器上：
  要么降级跑通并标“OCR 不可用，已降级”，要么第一步给出可照做提示；
  不再出现 `adapter_exception` 这种无信息文案。

### 四、豆包 HTTP MCP 端点（本机直连，实测通过）

- 咕嘎本体新增 streamable HTTP 传输：默认只绑 `127.0.0.1`，路径 `/mcp`，
  工具集与 stdio 完全一致（5 个：`report_app` / `get_task` / `report_progress` /
  `submit_artifact` / `ask_guga`），**不绑 0.0.0.0**。
- 端口从 18760 起，被占用就 +1（最多试 20 个）；实际端口写进
  `%LOCALAPPDATA%\GUGA\runtime\mcp_http.json`，并显示在接入面板豆包卡片上。
- 主程序启动时自动拉起端点（可在 `ai_config.json` 设 `mcp_http_enabled=false`
  或环境变量 `GUGA_MCP_HTTP=0` 关闭）；独立排查参数 `--guga-mcp-http`；
  stdio 模式 `--guga-mcp` 原样保留，WorkBuddy / JoyCode 继续用 stdio。
- 豆包教程与复制内容改为 HTTP 优先：服务器名称 `guga`、传输类型 `HTTP`、
  服务器 URL `http://127.0.0.1:<实际端口>/mcp`、Headers 留空；
  同时保留 STDIO 作为备选写法。
- 接入面板显示端点状态（监听中/未启动/端口冲突/启动失败）与
  「豆包需在‘工作’模式下才会调用该连接器；对话模式、/ 和 @ 搜不到」。
- 真实验收（`build/verify_mcp_http_g.py`）：真实起服务 + `mcp` 客户端
  `initialize` → `list_tools` 拿到 5 个工具 → `tools/call get_task` 成功；
  再占住 18760 验证自动回退到 18761 并同样握手成功。
  **豆包客户端界面这一步无法在打包机上复现，固定标「未验证」。**

### 五、MCP 按官方口径，不再写猜测路径

- 豆包：入口「插件·技能·伙伴 → 插件 → 右上角 + 添加 → 新建自定义连接器」；
  传输只有 HTTP / STDIO（官方无 SSE）；HTTP 优先，STDIO 备选；
  该连接器只在豆包「工作」模式生效，对话模式和 `/`、`@` 都搜不到；
  官方未要求重启；没有独立“连通状态/工具清单”页（只能看「插件 → 管理」）；
  门槛：登录 + 个人订阅或团队/企业额度。
- JoyCode：官方只有「MCP市场 → 全局配置文件 → +MCP配置」，未公布文件路径；
  **停用默认写 `{workspace}/.joycode/mcp.json`**，改为生成可粘贴 JSON
  （`type` 必填 `"stdio"`）+ 引导走官方界面；生效看右下角「添加成功，正在更新」，
  官方未要求重启。
- 状态统一三态：已检测到配置 / 界面已显示 guga / 未验证；
  只有真实握手拿到 5 个工具才显示“已连接”，其余不写“已接入”。

### 六、失败文案四段 + 一键导出诊断

- 豆包/WorkBuddy/JoyCode 失败固定输出：
  失败码（`launcher_not_found` / `workspace_not_found` / `panel_not_open` /
  `typed_in_editor` / `not_submitted` / `artifact_incomplete` / `artifact_stale` /
  `login_required` / `window_blank` / `ocr_unavailable` 等）
  + 阶段（启动/定位工作区/提交指令/等待产物/校验交付）
  + 原始异常或 stderr 摘要（≤200 字、脱敏）
  + 用户下一步动作（具体到按钮或环境变量）。
  找不到码写「未归类：<异常类型>: <首行消息>」，禁止「（错误）」占位。
- 新增「🩺 导出诊断（发给我们）」：右键菜单 + 模型设置页。
  导出 `咕嘎诊断_年月日_时分秒.zip` 到桌面，含版本号/构建 SHA、自检逐项真实结果、
  最近 30 分钟日志、任务台账摘要、失败码与证据目录清单；
  API Key / Authorization / Bearer / sk-* / 长十六进制串脱敏，`ai_config.json` 原文不打包。

### 七、随包文档

- 安装说明、评委安装与使用说明、作品介绍、豆包连接器配置教程、
  本 RELEASE-NOTES 全部同步写清：
  OCR 依赖与缺中文语言包怎么装、PowerShell 脚本被拦怎么放开、
  豆包 HTTP 优先（端口回退/工作模式/STDIO 备选）、JoyCode 官方入口与三态、
  出问题怎么导出诊断。
- 验收表与“改前静态 vs 改后实测”对照表见
  `g版验收与自检实测对照-20261108.md`（只写通过/未通过/未验证，不写“应该”）。

## 2026-11-08 窗口缩放自适应修复（20261108f）

### 本版改动

- 新增 `ui/dialog_fit.py`：窗口尺寸统一按
  `QApplication.primaryScreen().availableGeometry()` 收口，
  左右留 24px、上下留 40px 并扣掉标题栏；不再写死窗口高度。
- 以下窗口全部改为自适应 + `QScrollArea`，按钮区固定在滚动区外：
  接入状态面板、豆包连接器教程、复制失败兜底框、“已记录”结果框、
  新增软件对话框、软件接入提醒、首次配置向导、启动自检窗、建议安装弹窗。
- 首次配置向导由 `setFixedSize(560, 620)` 改为内容区滚动 + 固定底栏
  「保存并启动咕嘎」；接入提醒同样把「稍后 / 现在接入」固定在底栏。
- 三档缩放实测（本机 1920×1080，可用区物理高 1040）：

| 缩放 | 可用高(逻辑) | 接入面板高(逻辑) | 接入面板高(物理) | 滚动条 | 底部三按钮 |
|---|---|---|---|---|---|
| 125% | 832 | 724 | 937.5 | 否 | 刷新状态 / 新增软件 / 关闭 均在可用区内 |
| 150% | 693 | 585 | 910.5 | 否（塞满卡片时出现） | 同上 |
| 175% | 594 | 486 | 883.8 | 是 | 同上 |

  首次配置向导、启动自检窗、软件接入提醒、新增软件、豆包教程、
  复制兜底框在 125% / 150% / 175% 下均未超出可用区，底栏按钮全部可点。
  脚本：`build/verify_scale.py`；截图：`build/evidence_scale/`。

## 2026-11-08 可信接入版（20261108e）

### 一、模型 Key：不再有任何含糊

- **去掉隐式默认端点（F-05）**：之前缺 `base_url` 时请求会静默发往
  `api.deepseek.com`，等于把用户的 Key 发给他没选的服务商。本版所有模型调用
  （对话、拆任务、写回执、云端派单前置校验）统一走 `require_model_config()`：
  缺 Key / 缺服务商 / 缺模型名分别给出明确中文原因，缺服务商就报「未选择服务商」，
  不再有任何默认端点或默认模型名。
- **界面看得见**：设置页「当前生效」显示服务商 · 端点 · 模型 · Key 来源 · 打码 Key；
  桌宠右上角常驻「未配置模型」红色按钮，点击给「去配置模型 / 先用本地功能」两个动作；
  失败气泡改为常驻提示，不再 8 秒消失。
- **MCP ≠ 模型可用**：接入只解决“软件装在哪”，模型 Key 必须用户本机自填；
  界面上把这两件事分开写。
- **无内置凭据**：发行包内没有任何内置/试用/赠送 Key 或端点；
  桌面端与执行器的云端服务地址也改为由用户 `cloud` 配置下发，
  没配就不发请求（UI 不再预填地址，示例文件留空）；
  `tools/release_guard.py` 在构建期扫描文本、`.pyc`、exe 内嵌 PYZ 与 zip 条目，
  命中 `sk-` 等形态、或出现非示例 `ai_config*.json` 就删除产物并中止构建。

### 二、旧配置迁移改为“显式确认，默认不沿用”（P0）

- `guga_paths.migrate_legacy()` 不再 `copy2`：只检测安装目录旧配置，
  返回 `pending_confirm`，用户目录不写入任何 Key。
- 启动时弹窗打码显示来源、服务商、端点、模型与 Key 后四位；
  默认按钮「重新填写（推荐）」，只有明确点「沿用这份配置」才复制，
  并标记 `key_source=legacy_inherited`。
- 设置页显示 Key 来源：本机填写 / 从旧配置继承 / 云端下发；
  改造后正常只应出现「本机填写」。
- `ai_config.example.json` 永远不参与迁移；打包时删除 `_internal/ai_config.json`，
  并把“包内禁止运行期配置”加入 `verify_bundle()`。
- 云端权益错误码 `CLOUD_NOT_ENTITLED` / `CLOUD_QUOTA_EXCEEDED` 翻译为
  「需购买云端服务」，不拿运营 Key 兜底。
- 新增 `ADMIN_ONLY`（仅管理员可用）与 `BASEURL_REQUIRES_NEW_KEY`
  （换服务商后旧 Key 失效）两条中文提示；四类 403 都按业务拒绝处理，
  不重试、不当网络波动。
- `/api/agent/vision`、`/api/agent/consult` 按服务端精确规则降级：
  **HTTP 403 且 `body.degraded === true`** 才跳过，不重试、不判任务失败。
  `helper=vision` → 跳过本步截图理解，走本地启发式；
  `helper=consult` → 等价 `{"type":"deliverable"}`，当前回复继续交付。
  提示只用文案（未开通 / 额度用完 → “已用本地模式继续”），
  code 不写进任务状态或失败原因；日志记 helper / code / 时间。
- 本地没填自己的 Key 时，本地 AI 明确不可用；云端只在购买云端账号后可用，
  两端互不顶替，代码里没有任何云端兜底路径。

### 三、连接器 / 接入状态面板（新增）

- 入口三处：自检窗、桌宠右键、桌宠右上角「接入」按钮，随时可进。
- 每款软件一行：未安装 / 已安装未接入 / 已接入；已接入区分
  “只检测到配置”与“真的连上了”。
- 「验证连接」按配置真实拉起 `GUGA-Desktop.exe --guga-mcp`，
  `list_tools` 校验 5 个工具（含 `report_app`），显示最近一次自报路径与时间，
  失败给具体原因（配置路径不对 / exe 不存在 / 超时 / 工具清单不符）。
- 「新增软件」：填名称 + exe 路径（可浏览），生成配置可一键复制，
  同时写入 `app_reports.json`。
- 面板异步扫描 + 可刷新，按钮「检测中… / 验证中…（最长 25 秒）」置灰，
  不再冻结 UI。

### 四、豆包单独提醒

- 自检提醒与接入面板里，豆包独立成卡片，标题「豆包：用连接器接入，不是粘贴 JSON」，
  不与 WorkBuddy / JoyCode 的贴 JSON 提示混排。
- 两个动作：「查看豆包连接器教程」打开包内教程；「复制连接器字段」复制成
  “字段：值”文本（非 JSON）并读回校验。
- 状态单独文案：连接器未创建 / 已创建待验证 / 已连接。
- 没装豆包时不显示这块。

### 五、首启审计修复

- **F-01** 自检返回值被主程序检查，`fatal` 不再放行，点退出真的退出。
- **F-02** 向导点 X 改为三选一（稍后配置 / 最小化到托盘 / 退出），有下一步说明。
- **F-03 / F-13 / F-14** 保存、测试连接、接入扫描全部异步，不再卡 UI。
- **F-07** 接入教程不再只弹一次，右键菜单 + 主界面按钮 + 自检按钮都是永久入口。
- **F-08** 新增 `config_exe_missing` 状态：配置里的 exe 不存在时引导重新复制配置。
- 未修条目（F-06 / F-09 / F-10 / F-11 / F-12 / F-15 / F-16 / F-17 / F-18~F-23）
  见交付说明，均有原因，不用“已优化”含糊带过。

### 六、验证

- `build/verify_e.py`：源码模式 26/26、发行目录模式全部通过；
  覆盖 F-05 四种配置、P0 迁移默认不写 Key、打码与来源标记、真实握手成功/失败、
  接入面板后台扫描、新增软件写入 `app_reports.json`。
- `verify_bundle()` / `verify_release_zip()` / `release_guard` 全闸门通过。

## 2026-11-08 换机可跑版（20261108d）

### 本版改动（修 c 版换机器必挂的问题）

- **复制配置改为随安装位置自适应**：打包运行时 `command` 取 `sys.executable`
  （即当前解压出来的 `GUGA-Desktop.exe`），参数固定 `--guga-mcp`；
  不再出现开发机的 Python 解释器路径或源码脚本路径。
- **不再把工作区写进配置**：`GUGA_WORKSPACE` 从复制片段里移除，由 MCP server
  启动时自己解析；用户仍可用环境变量显式覆盖。配置里只剩命令、参数、
  `PYTHONIOENCODING` 与软件标识。
- **开发机痕迹守卫**：生成/写入配置前扫描开发机工作区名、源码目录名、
  Python 解释器名与 Python 绝对路径；命中就拒绝复制/写入并给出原因，
  避免源码环境的配置再漏到别的电脑。
- **豆包连接器教程同步**：命令示例改为「你解压目录下的 `GUGA-Desktop.exe`」，
  参数 `--guga-mcp`，写明不要填解释器或开发目录、不需要装 Python。
- **随包文档同步**：`使用说明` 8.5、`安装说明` 第六节、`作品介绍` 的配置示例与
  Key 说明改成 exe 口径；`RELEASE-NOTES.md` 记录本版变更。

### 验收

- 把发行包解到 `%TEMP%\guga-mcp-verify\`（不含项目路径），从**冻结 exe** 执行
  `--mcp-snippet-json` 生成三家配置；原文中开发机工作区、Python 版本目录、
  解释器名、`sk-` 均为 0 命中，`command` 指向该临时目录里的
  `GUGA-Desktop.exe`，`args` 为 `--guga-mcp`。
- 用这段配置真实拉起一次 MCP server，`list_tools` 读到 5 个工具，包含 `report_app`。
- `verify_bundle()`、`verify_release_zip()` 全闸门通过；前三枚 zip 均保留未覆盖。

## 2026-11-08 接入引导版（20261108c）

### 本版改动

- **自检后主动提醒**：启动自检通过后，若检测到软件“已安装但没接入咕嘎 MCP”，
  主动弹「咕嘎 · 软件接入提醒」，讲清“不配只能猜路径 + 纯视觉”“配了就能记住路径”，
  可直接点「现在接入」；同一天同一批软件只提醒一次（`runtime/mcp_onboarding_nudge.json`）。
  三种状态分开显示：已安装未接入（含待重启）/ 已接入 / 未安装。
- **一键复制 + 读回校验**：接入窗口每款软件都有「复制配置」，
  写入剪贴板后立刻读回比对；成功时按钮变「已复制」，旁边写明“粘贴到：哪里”；
  失败则弹出已全选的文本框供手动复制。
- **配置绝不含模型 Key**：复制片段只含本地命令、参数、工作区路径；
  生成前会扫描 `ai_config.json` 里的凭据值和 `sk-...` 形态，命中则拒绝显示。
  模型 Key 仍由用户在本机首次配置里自己填，不随包分发、不内置。
- **豆包单独教程**：新增 `豆包连接器配置教程.txt`，按「设置 → 连接器 →
  新建自定义连接器」的真实表单写步骤，不再套用 WorkBuddy 的 JSON 说法；
  接入窗口内有「打开豆包连接器教程」按钮。若版本只有 HTTP/SSE，明确说明不要硬填本地路径。
- **其他软件以 WorkBuddy 为示范**：文案统一为“在软件自己的设置里添加 MCP”，
  写明菜单入口随版本变化，找不到就用复制按钮拿文本，不硬编码某一版菜单路径。
- **随包文档同步**：`使用说明` 8.5 节、`安装说明` 第六节、`作品介绍`
  已更新为上述口径；`verify_release_zip()` 文档闸门扩到 6 份（新增豆包教程）。

### 验收

- 复制按钮实测：真实写入系统剪贴板并读回，按钮变「已复制」；模拟失败时弹兜底文本框。
- 复制原文扫描：不含模型 Key（`sk-` 与 `ai_config.json` 凭据值均为 0 命中）。
- `scripts/verify_mcp_discovery.py`、`scripts/verify_app_registry.py` 回归通过。

## 2026-11-08 MCP 发现版

### 本版改动

- **MCP 定位收敛为“只发现、不指挥”**：MCP 只负责让被适配软件自报安装路径；
  派单（点哪里、发什么、读什么）仍走界面自动化（UIA + 视觉 + 键鼠），
  没有把任何派单改成 MCP 通道。
- **新增 MCP 注册工具 `report_app`**：软件连上 `--guga-mcp` 后可自报
  软件标识、名称、可执行文件绝对路径、版本、能力；写入
  `%LOCALAPPDATA%\GUGA\app_reports.json`（`guga_paths` 原子写 + 回读校验）。
  工具清单从 4 个变为 5 个：`report_app / get_task / report_progress / submit_artifact / ask_guga`。
- **启动路径优先级**：用户手动指定 > MCP 自报（`mcp_report`） >
  声明清单的常见目录 / 注册表 / 开始菜单 / PATH / 运行进程 / 绿色版扫描。
  该优先级已接进三家真实拉起路径：`workbuddy_bridge._resolved_exe()`、
  `doubao_adapter._resolve_exe()`、`joycode_adapter._default_launcher()`
  都先调 `app_registry.launch_exe()`，失败再走各自兜底。
- **工具职责说清**：`report_app` 是发现通道；`get_task / report_progress /
  submit_artifact / ask_guga` 保留为旧 worker 的兼容任务总线，咕嘎派单不调用它们，
  代码注释、工具描述与随包文档统一为“发现靠 MCP 自报、指挥靠界面自动化”。
- **脏记录回退**：自报路径做绝对路径 + 存在性 + `.exe` + 非空校验；
  失效时只记一条 `warnings`（界面提示「已忽略 N 条失效自报路径」）并继续回退探测，
  不会因为一条脏记录导致软件再也启动不了；缓存签名含 `app_reports.signature()`，记录变化即失效。
- **接入教程与技能文档同步**：MCP 接入弹窗、`mcp_channels`、WorkBuddy / 豆包 SKILL
  均补充 `report_app` 用法与“一次连接记住路径，以后不用再猜”，并明确 MCP 不承担派单。
- **随包文档口径同步**：`使用说明` 新增 8.5 节「软件路径不用猜」；
  `安装说明` 新增第六节「让软件自报安装路径（MCP）」；
  `作品介绍` 明确“发现 / 指挥”两件事分开；本文件记录本版变更。

### 验收

- `scripts/verify_mcp_discovery.py`：工具列表 5 个；`report_app` 落盘
  `C:\Users\l\AppData\Local\GUGA\app_reports.json`；自报路径覆盖声明清单里的错误路径
  （`source=mcp_report`）；手改记录指向不存在路径后回退 `env` 并记「自报路径已失效」；
  删除记录后 `not_installed`，恢复 `env` 后 `ready`。
- `scripts/verify_app_registry.py`：退出码 0；豆包 / WorkBuddy / JoyCode 均 `ready`；
  模拟未安装 / 异盘 / 绿色版 / 用户指定 / 缓存只读 / `unknown` / `registry_denied` 结果正常。
- 打包闸门：`dist/.build.lock` 单实例、`verify_bundle()`、`verify_release_zip()`（5 份文档各 >1KB）。

### 已知限制

- 豆包没有本地 MCP 配置文件，自报路径需登录后在「个人 MCP 连接器」手动新建。
- 自报路径依赖软件主动调用 `report_app`；不调用时仍按原有探测回退，行为与旧版一致。

## 2026-11-08 最终版

### 本版改动

- **随包文档**：zip 根目录新增 `使用说明.html`、`使用说明.txt`、`安装说明.txt`、`作品介绍.txt`、`RELEASE-NOTES.md`；
  构建流程自动从 `docs/评委安装与使用说明.md` 生成前两份，并校验五份文档都在根目录且非空。
- **配置与写入修复**：配置、运行数据、交付物、日志、声纹、对局历史等写入 `%LOCALAPPDATA%\GUGA`；
  安装目录只读时也能保存并进入桌宠；旧配置自动迁移。
- **首次配置**：无 Key 点“仍要保存”不再退出，进入桌宠后提示“配置未完成”。
- **真实 DPI**：`--selfcheck-json` 与自检窗读取主显示器真实 DPI（125% 报 120）。
- **外部工具链路**：
  - WorkBuddy：UIA 定位编辑器、哨兵校验、页面归属校验（`page_mismatch`）；
    反问卡片自动应答（按“推荐 → 第一项 → 跳过”连续处理追问，实测连续两问通过）。
  - JoyCode：统一 `Adapter` 入口；安装路径发现支持注册表 / 开始菜单 / 常见目录，
    找不到时提示设置 `GUGA_JOYCODE_LAUNCHER`；`resolve_workspace()` 从 JoyCode 配置读当前工程，
    失败时弹窗选择；幂等键、重复派单拦截、回执后回收任务文件、悬空回执归档；
    回车无效时改点发送按钮，双条件断言。
  - 豆包：`not_installed` / `launch_failed` 明确失败码。
- **交付闸**：同一目标重复派单提示；无真实工具成功回执不交付、不代写冒充；
  气泡文案前置承诺句并截断原因，避免关键信息被截掉。

### 验收

- core 17/17、readonly 9/9、noai 13/13、install-writes 9/9（0716 包实测）。
- 本最终包另行完成：zip 根目录五份文档、干净目录解压、exe 启动、
  `--selfcheck-json`、包内无 Key。

### 已知限制

- 真机派单未在验收矩阵覆盖（测试环境未安装豆包/WorkBuddy/JoyCode）；
  现场演示需提前安装并登录，JoyCode 需先打开目标工程和右侧 AI 面板。
- 复合任务串联、模型入口仍在收尾；本包以当前可用链路为准。
- 2560×1440 分辨率本机未适配，结论为“不适用”。
- 窗口尺寸已按屏幕可用区自适应：125% / 150% / 175% 下接入面板、向导、自检、
  接入提醒等底栏按钮均可见可点（f 版实测）；但界面自动化点击定位仍建议演示前设为 100%。
- 安装包未做代码签名，首次运行可能出现 SmartScreen 提示（更多信息 → 仍要运行）。
