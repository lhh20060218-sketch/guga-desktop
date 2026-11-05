# 剧本：gemini-export

- **剧本ID**：gemini-export
- **软件**：Google Gemini（网页版 gemini.google.com，本机未装客户端）
- **动作目标**：少爷把 Gemini 的回答取出来——用官方复制按钮搬正文，或用分享生成公开链接，再粘到指定应用。

## 前置条件

1. 已登录，目标回答已生成完毕、下方操作栏出现。
2. 少爷知道要粘到哪：飞书文档、微信、邮件、记事本均可。
3. Workspace 账号可能被管理员默认关闭链接分享，开关文案待真机核对。

## 步骤序列

### 路线 A：复制单条回答正文

1. **定位复制按钮**
   - 元素特征：目标回答正下方一排小图标，其中 Copy 为两张重叠纸片形状；**确切图标与是否带文字待真机核对**。
   - 动作：悬停到该回答下方，点 Copy 图标。
   - 等待判据：按钮短暂变勾选态（toast 文案待真机核对），正文进入系统剪贴板。

### 路线 B：生成整段会话分享链接

2. **打开分享入口**
   - 元素特征：会话级 Share 入口，多在回答下方操作栏或右上角菜单。
   - 动作：点 Share。
   - 等待判据：弹出分享面板，提示可创建公开链接。
3. **创建链接**
   - 元素特征：面板内“Create link（创建链接）”——Google Cloud 官方文档说明点击后链接自动复制进剪贴板。
   - 动作：点 Create link。
   - 等待判据：面板出现形如 `g.co/gemini/share/...` 的公开链接并提示已复制。
4. **发人前先自检**
   - 元素特征：刚生成的链接。
   - 动作：少爷自己在新标签页打开，确认外人看到的就是这段对话。
   - 等待判据：未登录 Google 的窗口也能打开，即链接公开可用。

### 汇合：粘到目标应用

5. **粘贴**
   - 元素特征：目标应用输入框（飞书/聊天/邮件正文）。
   - 动作：切过去按 `Ctrl+V`（Mac 为 `Cmd+V`）。
   - 等待判据：正文逐字一致（路线 A），或粘入一条可点开的 `g.co/gemini/share/...` 链接（路线 B）。

## 成功判据

目标应用里出现 Gemini 原文，或出现一条他人可正常打开的 `g.co/gemini/share/...` 链接，无需手抄。

## 异常处理

- 点 Copy 却粘出空白，管家请少爷确认焦点已点进目标框、剪贴板没被顶掉，重点一次 Copy 再粘。
- 面板里没有 Share 按钮，多半是 Workspace 账号被管理员关了分享；管家建议少爷换个人 Google 账号，或退用路线 A 复制正文。
- 分享链接别人打不开，少爷先自己在无痕窗口验一眼；仍打不开，待真机核对是否被账号地区策略限制。

## Sources

| 来源 | URL | 可信度 |
|---|---|---|
| Google Cloud 官方文档：Share→Create link 自动复制到剪贴板 | https://docs.cloud.google.cn/gemini/enterprise/docs/share-conversations | 高 |
| Gemini 官方入口 | https://gemini.google.com | 高 |
| 第三方实测：Workspace 默认关分享、个人账号 Share 在回答下方 | https://aitoolsguidebook.com/en/articles/gemini-export-share-issue/ | 中 |
| 复制按钮图标样式、toast 文案、g.co/gemini/share 样例 | —— | 待真机核对 |
