# 剧本：gemini-ask

- **剧本ID**：gemini-ask
- **软件**：Google Gemini（网页版 gemini.google.com，本机未装客户端）
- **动作目标**：少爷打开网页、登录、发出第一个问题，拿到一段完整回答。

## 前置条件

1. 有可用 Google 账号，能完成登录。
2. 网络可访问 Google 服务：Gemini 官方未对中国大陆开放，国内直连会被地区拦截，需自备可访问支持地区的网络通道（生效与否待真机核对）。
3. 浏览器用 Chrome/Edge；界面语言随账号设置，下文按钮名以英文官方界面为准，确切中文文案待真机核对。

## 步骤序列

1. **打开网页**
   - 元素特征：浏览器地址栏。
   - 动作：输入 `gemini.google.com` 回车。
   - 等待判据：跳转到登录页或直接进入主界面；主界面左上角可见“New chat（新对话）”。
2. **登录 Google 账号**
   - 元素特征：账号选择卡片与“下一步/Next”按钮。
   - 动作：选少爷的账号，输密码、过二次验证。
   - 等待判据：左上角出现“New chat”与最近会话列表。
3. **（可选）选模型档位**
   - 元素特征：输入框附近的模型名下拉，常见有 “2.5 Flash”“2.5 Pro”；**网页版当前具体档位名待真机核对**。
   - 动作：一般提问保持默认；要更严谨就点开选 Pro。
   - 等待判据：下拉收起，档位名常驻显示。
4. **输入问题**
   - 元素特征：页面底部多行输入框，占位提示约为 “Ask Gemini…”（原文待真机核对）。
   - 动作：点输入框，键入问题。
   - 等待判据：字出现在框内，右侧发送按钮由灰转亮。
5. **发送**
   - 元素特征：输入框右侧纸飞机/箭头图标。
   - 动作：点图标，或回车（Shift+回车换行）。
   - 等待判据：提问以用户气泡出现，下方开始流式输出。
6. **等回答完成**
   - 元素特征：回答正文区。
   - 动作：静置不重发。
   - 等待判据：流式光标停止，回答下方出现复制/赞踩/重生成操作栏。

## 成功判据

对话区同时显示提问气泡与一段不再变化的完整回答，下方操作栏出现。

## 异常处理

- 网页卡住或提示“该地区不支持”，少爷先检查网络通道是否切到支持地区，切好刷新；仍不行就把报错截图给管家，待真机核对。
- 登录后只有权限申请页，多半是单位 Workspace 账号被管理员拦了，管家建议少爷换个人 Google 账号。
- 回答中途不动，少爷别重问，点回答下方“重新生成”即可。

## Sources

| 来源 | URL | 可信度 |
|---|---|---|
| Gemini 官方入口 | https://gemini.google.com | 高 |
| 官方适用地区说明 | https://ai.google.dev/gemini-api/docs/available-regions?hl=zh-cn | 高 |
| 官方论坛：大陆地区不可用的官方回复 | https://discuss.ai.google.dev/t/a-request-for-help-from-chinese-mainland/178323 | 高 |
| 密歇根大学 IT：New chat 左上角布局 | https://its.umich.edu/communication/collaboration/google/update/delete-and-start-temporary-chats-google-gemini | 中 |
| 模型命名（2.5 Flash/Pro） | https://ai.google.dev/gemini-api/docs/models?hl=zh-cn | 中（API 文档，网页档位待真机核对） |
