# 安装与部署

咕嘎有两种用法：**直接用发行包**（推荐，免装 Python）和**从源码运行**（改代码 / 二次开发）。两种都只支持 **Windows 10 1809+ / Windows 11 x64**。

---

## A. 直接用发行包（推荐）

发行包不打进 Git 仓库，放在 GitHub Releases：

```
https://github.com/<你的账号>/<仓库名>/releases
```

下载 `GUGA-Desktop-win64.zip`（约 347 MB，解压后约 610 MB）后：

1. **解压到任意目录**。中文、空格、非 C 盘、桌面、`D:\软件\咕嘎` 都可以。
   - 只读目录（例如 `C:\Program Files`）也能运行：配置、缓存、交付物、日志都会自动写到 `%LOCALAPPDATA%\GUGA`。
   - 但安装目录本身必须保留 `GUGA-Desktop.exe` 与 `_internal\` 同级；**不要只把 exe 单独拷出来**。
2. 双击 `GUGA-Desktop.exe`。
   - 首次运行会被 SmartScreen 拦一次：点「更多信息 → 仍要运行」。
   - 程序未签名，这是正常现象，不是报毒；如被杀毒软件拦截，把整个解压目录加入白名单。
3. 按启动自检 → 首次配置向导走完（选平台 → 填 API Key → 点「测试连接」→ 保存）。
4. 企鹅出现在桌面，即可右键派任务 / 对话 / 语音。

### 首次配置需要什么

| 项目 | 是否必填 | 说明 |
|---|---|---|
| 对话 API（`api_key` / `base_url` / `model`） | **必填** | 任意 OpenAI 兼容接口；向导里可选智谱、DeepSeek、通义等。不填也能进桌宠，但只能使用本地功能 |
| 云端大脑（`cloud`） | 选填 | 填了才有「派个任务 / 任务台账 / 跨设备监工」。不填不影响桌宠本体 |
| 实时语音（`realtime_voice`） | 选填 | 不填则「按住说话」走离线 vosk + edge-tts，仍可用 |
| 目标 AI 软件（豆包 / WorkBuddy / JoyCode） | 选填 | 装上并登录后，相应派单能力才可用；未装时界面会明确提示缺什么，不会崩溃 |

### 目标 AI 软件是怎么被发现的

咕嘎不把安装路径写死。发现顺序是：

1. **用户手动指定**（设置里选过的路径 / `GUGA_APP_REGISTRY_USER`）；
2. **软件自报**（通过咕嘎 MCP server 调 `report_app`，上报 exe 绝对路径、版本、能力，落盘 `%LOCALAPPDATA%\GUGA\app_reports.json`）；
3. **声明清单 + 自动探测兜底**（常见目录、注册表、开始菜单、PATH、运行进程、绿色版扫描）。

自报路径失效时只记录原因并继续探测，不会因为一条脏记录让软件再也起不来。  
**MCP 只负责发现，不负责指挥**：派活仍由界面自动化（视觉 + UIA）在本机执行。完整机制、实测耗时与已知不一致见 [docs/软件识别机制.md](docs/软件识别机制.md)。

### 数据保存在哪

- 配置：`%LOCALAPPDATA%\GUGA\ai_config.json`
- 运行数据 / 缓存 / 证据 / 交付物：`%LOCALAPPDATA%\GUGA\`
- 启动日志：`%USERPROFILE%\.guga\logs\startup.log`
- 覆盖升级、换机器登录同一账户时，配置不会丢；旧版放在安装目录里的配置会在首次启动时自动复制过来（只复制不删除）。

**重置配置**：删除 `%LOCALAPPDATA%\GUGA\ai_config.json`，下次启动会重新弹向导。

### 不需要额外安装的东西

| 依赖 | 说明 |
|---|---|
| Python | 发行包已内置，不需要 |
| VC++ 运行库 | 已随包内置 `VCRUNTIME140.dll` / `MSVCP140.dll`，裸机无需装 VC++ Redist |
| ffmpeg | 已内置（`imageio-ffmpeg`），视频兜底与字幕合成不需要另装 |
| Office / WPS | **不需要**。PPTX 由 `python-pptx` 生成；没有 Office 也能产出可打开的 .pptx |
| 管理员权限 | **不需要**。只有「一键拔线」这类系统级功能会提示提权，拒绝 UAC 也能继续用其他功能 |
| 网络 | 启动与本地功能不需要；调用模型、云端派单、下载离线语音模型时需要 |

---

## B. 从源码运行

```powershell
# 1) 建议 Python 3.12（3.10+ 均可），确认 64 位
python --version

# 2) 安装依赖（在仓库根目录）
pip install -r requirements.txt

# 3) 生成配置：两种方式任选
copy ai_config.example.json ai_config.json   # 方式一：手工填 JSON
# 方式二：直接启动，让首次配置向导帮你写

# 4) 启动
python comp_main.py     # 参赛版（管家形态，推荐）
python launcher.py      # 开发版（完整能力）
```

- 源码运行同样会把配置与运行数据写到 `%LOCALAPPDATA%\GUGA`，不会写进仓库目录。
- 若依赖装不全：程序会在启动自检里标为「降级 / 致命」，并给出缺哪个模块；不会静默崩溃。
- 自定义数据目录：设置环境变量 `GUGA_HOME` 指向一个可写目录即可。

### 可选：云端大脑

```powershell
cd cloud
copy .env.example .env      # 填 LLM_API_KEY；不设 JUDGE_PASS 会启动时随机生成
npm install
npm start                  # 默认 3000 端口
```

启动后在桌宠 `ai_config.json` 的 `cloud` 段填 `base_url` / `username` / `password`，重启桌宠即可看到「派个任务」「任务台账」。

> 端口 3000 不要裸暴露公网；生产环境请用 nginx / 安全组限制来源。

### 可选：把另一台电脑当执行机

```powershell
cd agent
pip install -r requirements.txt
python preflight.py          # 18 项本机体检，0 FAIL 才适合真机执行
python guga_agent.py <配对码>
```

通常不需要：桌宠进程内已内置执行方，登录云端账号后自动配对。

---

## C. 常见安装问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 双击没反应 / 一闪而过 | 只拷了 exe，没带 `_internal` | 重新解压完整目录 |
| 自检「运行库」致命 | 解压不完整或被杀毒拦截 | 重新解压，并加白名单 |
| 自检「内置依赖」致命 | 同上 | 同上 |
| 配置保存失败（Permission denied） | 用户目录不可写（少见，如受限账户 / 漫游配置异常） | 设置 `GUGA_HOME` 到可写目录后重启 |
| 测试连接 401 / 模型不存在 / 额度不足 | Key 或模型名不对 | 按提示换 Key / 换模型；向导会区分网络、Key、模型、额度、超时 |
| 派单提示「没有真实工具调用回执」 | 目标软件没装 / 没登录 | 装好并登录后再派；咕嘎不会用模型代写冒充工具产出 |
| 在线体验端打不开 | 演示服务器不保证长期在线 | 以本机发行包为准；云端可自建 |
