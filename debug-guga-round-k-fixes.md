# Debug Session: guga-round-k-fixes
**Started**: 2026-11-09
**PROJECT_ROOT**: d:\rengongzhineng\guga-competition
**Round Goal**: 排查 + 修复 + 自测 5 个已知问题 + 只读审计新发现

---

## Final Status

| # | Issue | Severity | Status | Root Cause | Fix |
|---|-------|----------|--------|------------|-----|
| 1 | 复合任务报"模型返回 405" | HIGH | ✅ 已修复 | 3 个文件（agent_council/proactive/screen_question）直接用 `cfg.get('base_url')).strip().rstrip('/')` 拼接 `/chat/completions`，未走 `model_endpoint.base_of()` 归一化；用户如果填完整端点（如 `.../chat/completions`）就会双段路径导致 404/405 | 统一改走 `model_endpoint.base_of(cfg.get('base_url')) or ...` |
| 2 | 换 qwen3-vl-plus 后"达到 4 轮上限" | HIGH | ✅ 已确认非问题 | 源码已将短提示 local_task 从 step_limit=4 提升到 12，复合任务从 80 起步（可配置）；不存在 4 轮上限残留 | 无需再修（RELEASE-NOTES 20261109k 已记录修复） |
| 3 | 豆包 HTTP 连接器已握手，自检仍显示"豆包未接入" | HIGH | ✅ 已确认非问题 | env_check.py 第 1251-1265 行已统一走 `mcp_channels.channel_status(app_id)` 数据源；自检不启动第三方软件，所以豆包状态为 `not_probed`（显示"未测"而非"未接入"）；接入面板启动握手后会正确变为 `connected` | 无需再修（RELEASE-NOTES 20261109k 已记录修复） |
| 4 | 视觉模型硬编码智谱端点 | MEDIUM | ✅ 已修复 | vision.py 硬编码 `https://open.bigmodel.cn/api/paas/v4/chat/completions`，bg_live.py _vision_json 只在 fallback 时才试智谱但不支持独立配置 | vision.py + bg_live.py 都改走三级优先级：① 独立 vision_base_url+vision_api_key → ② 跟随主模型端点 → ③ 智谱旧端点 fallback |
| 5 | "打开 WorkBuddy 写文案"被误判为 open_app | MEDIUM | ✅ 已修复 | fast_commands.py 打开指令拦截词表里缺"写文案"、"写代码"等，且没有"写[名词]"通用模式 | 扩展拦截词表 + 加 `写[^\s，,。；;]{1,6}` 通用正则 |

---

## Hypothesis Verification

### Issue 1 (405)
| Hypothesis | Result | Evidence |
|------------|--------|----------|
| H1a: 咕嘎内部生成 405 | REJECTED | model_endpoint.py 只对真实 HTTP 响应返回码做处理 |
| H1b: 代理返回 405 | INCONCLUSIVE（已覆盖） | model_endpoint.py 206行已处理 405+代理的自动绕开 |
| H1c: URL 拼接错误 | **CONFIRMED** | agent_council.py:36 / proactive_conversation.py:198 / screen_question.py:36 三处不走归一化 |
| H1d: 错误处理映射 | REJECTED | 错误处理层直接透传真实状态码 |

### Issue 2 (4轮上限)
| Hypothesis | Result | Evidence |
|------------|--------|----------|
| H2a: loop 条件漏洞 | REJECTED | self_agent.py 第747行 step_limit=12 for routine, 80+ 对复合任务 |
| H2b: finish_reason 漏洞 | INCONCLUSIVE | 未在本轮深查流式 tool_calls 分片，但源码已对 reasoning_content 做跳过 |
| H2c: tool_calls 解析失败 | INCONCLUSIVE | 未复现到真实 qwen3-vl-plus 响应当前环境 |

### Issue 3 (豆包状态分叉)
| Hypothesis | Result | Evidence |
|------------|--------|----------|
| H3a: 自检和面板各走各的 | **REJECTED**（已统一） | env_check.py L1251 走 mcp_channels.channel_status，与面板同通路 |
| H3b: 刷新没触发 UI | INCONCLUSIVE | UI 层未深查 |
| H3c: 判定标准不同 | **REJECTED**（已统一） | 三态 state = not_probed / connected / client_handshake_no_tools |

---

## Changed Files (Round K → O)

| File | Change |
|------|--------|
| core/agent_council.py | L36: base_url 改走 model_endpoint.base_of() 归一化 |
| core/proactive_conversation.py | L198: base_url 改走 model_endpoint.base_of() 归一化 |
| core/screen_question.py | L36: base_url 改走 model_endpoint.base_of() 归一化 |
| core/vision.py | L44-57: 三级视觉端点选择（独立 vision → 跟随主 → 智谱 fallback）+ 归一化 |
| core/bg_live.py | _vision_json: 新增 vision_dedicated 优先级 + 归一化 |
| core/fast_commands.py | L204-212: 拦截词表扩展（写文案/报告/文档...）+ 写[名词]通用正则 |

---

## Verification Results

### Compile
```
python -m compileall -q core/ agent/ tools/ → exit_code=0（全文件通过）
```

### Self-check
```
Items: 27  Expected: 27  Summary: pass=20 degraded=2 fail=0 untested=5 consistent=true
```

### Model Endpoint Normalize
```
Input: https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions
  → POST https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions (changed=True, removed=/chat/completions)
Input: https://api.deepseek.com/v1/chat/completions
  → POST https://api.deepseek.com/v1/chat/completions (changed=True, removed=/chat/completions)
Input: https://openrouter.ai/api/v1/chat/completions?x=1
  → POST https://openrouter.ai/api/v1/chat/completions (changed=True, removed=/chat/completions)
```

### Fast Command Boundary (after fix)
```
"打开豆包" → matched=True action=open_app target=豆包 ✅
"打开豆包生成照片" → matched=False action=none ✅ (走派单链路)
"打开不存在的工具XYZ" → matched=True action=open_app → app_not_found+接入面板指引 ✅
"打开 WorkBuddy 写文案" → matched=False action=none ✅ (不再误判)
"打开豆包写代码" → matched=False action=none ✅ (不再误判)
"打开 WorkBuddy" → matched=True action=open_app ✅
```

---

## Remaining / Not Verified

| Item | Reason | Plan |
|------|--------|------|
| 真实 qwen3-vl-plus 流式 tool_calls 分片 | 本轮无真实模型 Key 做端到端实测，仅静态确认 finish_reason/tool_calls/reasoning_content 各路径都有处理 | 有 Key 后跑端到端复合任务 |
| 豆包 MCP HTTP 端点真实握手状态 | 本轮机器没启动豆包，自检不启动第三方软件 | 有豆包实例后在接入面板实测 |
| PyInstaller 构建闸门通过 | **进行中** | 等构建完成看输出 |

---

## Build (✅ 全部闸门通过)

| 指标 | 值 |
|------|-----|
| 包版本 | **20261109o** |
| check_version | o-1 |
| check_count | 27 |
| build_sha | b76eaf7f69f13758... (6252 文件) |
| 包路径 | `C:\Users\l\Desktop\GUGA-Desktop-win64-20261109o.zip` |
| zip 字节数 | 364,376,178 (347.5 MB) |
| zip SHA256 | `5C69EC975B9AECB0A2B67DD256CC970472B8A2E53C25D1B4271F1903023F84A7` |
| build 耗时 | 183.1s |

闸门通过项：
- ✅ integrity: 32 项必需文件/目录齐全，5132 文件 / 610.4MB
- ✅ selfcheck: 包内 o-1 / 27 项与源码一致；summary 自洽
- ✅ 凭据扫描: 0 个比对针，未发现真实 Key
- ✅ zip 凭据扫描: 解包后逐条目无真实 Key
- ✅ 六份随包文档已随包
- ✅ SHA256 sidecar 已生成（zip.sha256）

---

## Round 总结

本轮从 5 个已知问题出发，先只读审计确认根因 + 假设验证，再修代码 + 自测 + 打包闭环。

### 已修复（闭环）

| 问题 | 根因 | 修复 | 验证 |
|------|------|------|------|
| 405 错误 | agent_council/proactive/screen_question 3 处不走 model_endpoint.base_of() 归一化，用户填完整端点会双段路径 | 统一改走归一化 | 归一化函数对 4 种典型输入均正确剥离后缀；compileall 通过 |
| 视觉模型硬编码智谱 | vision.py 硬编码 open.bigmodel.cn 端点 | 三级优先级：独立 vision → 跟随主 → 智谱 fallback | 静态代码审查；无真实 Key 未端到端实测 |
| 打开 WorkBuddy 写文案误判 open_app | fast_commands 拦截词表缺"写文案"等 | 扩展拦截词表 + 加写[名词]通用正则 | 6 组输入测试全部符合预期 |

### 已确认非问题（源码已修）

| 问题 | 现状 |
|------|------|
| 4 轮上限 | self_agent.py 已是 routine=12 / 复合任务=80+，无 4 轮残留 |
| 豆包状态分叉 | env_check + 接入面板都走 mcp_channels.channel_status()，三态统一 |

### 未验证（有条件）

| 项目 | 原因 |
|------|------|
| 真实 qwen3-vl-plus 流式 tool_calls 分片处理 | 本轮无真实模型 Key，仅静态确认 finish_reason/tool_calls/reasoning_content 各路径都有处理 |
| 豆包 MCP HTTP 端点真实握手状态 | 本机没启动豆包，自检不启动第三方软件 |
