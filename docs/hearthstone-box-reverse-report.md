# 炉石盒子静态逆向报告：日志、胜率与咕嘎接管

分析日期：2026-10-19。目标：网易炉石盒子 Windows 4.0.4.486。本轮是安装包与模块静态分析，未启动盒子、未附加游戏进程、未抓取用户网络流量。结论分为已观察事实、推断和待验证事项。

## 结论

已下载并运行官方 REA 6.7.0 CLI，安装 `reverse-engineer-anything` 技能；已提取盒子安装包并定位辅助程序的命名管道调用、Qt/CEF 模块关系、匹配服务导出和受保护的主体模块。**尚未复原盒子的战斗胜率算法、日志解析器或 AI 决策接口，也未证明盒子具备可供第三方直接调用的自动操作接口。**

对咕嘎可立即采用的设计是：Power.log 事件还原局面 → 同版本战斗引擎计算概率 → 模型从合法动作中选择 → 视觉定位与桌面输入 → 日志确认动作与状态变化。这是结合现有项目提出的实现方案，不冒充已逆出的盒子架构。

| 重点 | 本轮盒子证据 | 对咕嘎的意义 | 未解决项 |
|---|---|---|---|
| 场上随从与日志 | 盒子主程序含 Qt、CEF、辅助模块；已证实辅助程序静态包含 IPC 调用 | 数据采集、局面状态、显示层宜分开；优先用现有日志采集器 | 盒子的局面结构、管道名/协议、日志与其他采集渠道的分工 |
| 胜率 | 盒子胜率入口尚未定位；另对本机 HDT 的 BobsBuddy 做了独立托管元数据检查 | 战斗计算应交给可验证规则引擎；记录引擎版本与覆盖率 | 盒子模拟次数、随机数、卡牌效果覆盖、是否有远端计算 |
| AI 接管 | 匹配服务 SDK 有 gameStart/gameEnd/requestMatch 等导出；没有证据证明这些是 AI 下棋接口 | 咕嘎已有候选动作、模型选择、输入与回执基础，优先完成自己的闭环 | 盒子是否具备自动代操作、AI 建议算法和可复用的接口 |

## 来源与复现身份

- REA 官方源码：[morluto/rea](https://github.com/morluto/rea)，本地源码提交 `69aa5465cd77c5cf9ff435e7a5a322d90c1db12c`。CLI 包 `rea-agents@6.7.0`，本地安装并禁用 npm 安装脚本。尚未注册 REA MCP，当前通过 CLI 使用。
- 盒子官方下载入口：[炉石盒子官网](https://lushi.163.com/)。已保存官网 main.js；其默认渠道 `pchz9`，下载地址为 `https://hs-api.lushi.163.com/setup/pchz9/hsa_setup.exe`。不保留 CDN 临时鉴权参数。
- 安装包：221,757,152 bytes，SHA256 `88f0601ba9ef0c56447469f41160cad3c5ba89e8d279ce5ec800aeb45af7273c`。Authenticode 检查 `Valid`，签名主体 `NetEase (Hangzhou) Network Co., Ltd`，文件版本 4.0.4.486。
- 未在有界限的本机安装目录和卸载项检索中找到已安装盒子；本报告针对上述官方发版安装包，不代表用户曾安装的其他版本。
- NSIS 包静态列出 277 个路径记录，选择提取 67 个文件；没有运行安装器。工具和证据位于本地 REA 证据目录，不随仓库分发。

## 已确认的模块证据

### 1. 主程序与保护边界

`HSAng.exe` SHA256 `503b87f04d5205e91f50abe90e12634048eb0e31ef6364943ccaaae6696128c1`，59,428,344 bytes，原生 x86 PE，无 CLI 目录。导入 Qt5Core、Qt5Quick、Qt5Qml、Qt5Widgets、QtCefWebView、libcef、overlaycef、NeteaseHSMatch 等 DLL。

`.text` 等段的磁盘原始大小为零而虚拟大小非零；磁盘段 `.O\\M` 熵约 7.9988，约 59.3 MB。**推断**存在压缩/加密/保护加载安排；没有识别保护器名称，也没有解包。不能因静态看不到字符串就断言某项业务逻辑不存在。

REA 资源证据 `ev_e7aadcf11f325b08557b9c0a14c97e36a5e4796c06a9f1c3f461cb76a7810dbb` 完整列出了资源目录，但版本/清单载荷本身没有被 REA 解释为业务逻辑。文件：`rea-hsang-resources.json`、`pe-structure-evidence.json`。

### 2. 辅助程序 IPC：从字串到指令候选

`HSAExternal.exe` 的导入表、错误字串与 x86 可执行段中存在以下 IAT 间接调用指令候选。偏移均为十六进制，复核脚本为 `analyze_pe.py`。

| 导入函数 | 文件偏移 | RVA | 指令字节 |
|---|---|---|---|
| CreateNamedPipeA | 0x6d97 | 0x7997 | ff15c4f04600 |
| ConnectNamedPipe | 0x69a8 | 0x75a8 | ff15b8f04600 |
| PeekNamedPipe | 0x507e | 0x5c7e | ff15b0f04600 |

相邻相关字串包括 `TPipeServer CreateNamedPipe failed`（文件偏移 0x72328）。这些静态证据支持该辅助程序包含命名管道代码；没有执行可达性证明、消息格式、管道端点身份或外部访问许可证明，不能直接拿来调用，也不能据此说传输内容就是场上随从。

`heart_helper.exe` 中另有 WriteProcessMemory IAT 调用候选（文件偏移 0x8cc1，RVA 0x98c1）；`heart_overlay.dll` 导出 `_hookmsgproc@12`，含 `.detourc/.detourd` 段。这只是辅助/钩子机制的线索，不证明其用途、运行行为或为 AI 接管服务。本轮未执行这些模块。

### 3. 匹配服务并非已证实的下棋决策接口

`NeteaseHSMatch.dll` SHA256 `fca270c62a33a38c33f3b3557e970ac86fcaaf72d609c361b211aa964c31b991`。REA 判定 `not-managed`：没有 CLI 数据目录，不能走 C# 托管反编译路线。证据 `ev_718a5d066b72aee9b6423da7c358ba57dbdc8d615514f3e36583e24c0e4d7ccb`。

导入 Qt5WebSockets/Qt5Network；导出 C++ `MatchServiceSDK_createService`、`requestMatch`、`playerReady`、`gameStart`、`gameEnd`、`statusReceived` 等符号。文件偏移 0x75eb0 的构建路径包含 `match_service_sdk` 与 Protobuf 头文件位置。

**推断**它与匹配/赛事服务通信有关；尚无消息 schema 和调用上下文，不能把 requestMatch 当成“帮我打一局”，也不能把 Protobuf 字串当成已还原游戏协议。

### 4. 录像模块仍受保护

`NeteaseHSRecord.dll` 有 `.vmp0/.vmp1` 段，后者熵约 7.9067；常规代码段原始大小为零。支持存在保护机制的判断，但未进行动态解包，录像、日志采集和胜率计算的关系未知。

### 5. 独立对照：本机 HDT 的 BobsBuddy

这不是炉石盒子的组件。本机 `Desktop/游戏/HDT/BobsBuddy.dll` 的 REA 元数据检查得到程序集 `BobsBuddy` 版本 `1.59.3.0`、托管 CIL/AnyCPU；SHA256 `197393e18af2838e4b5153adace5ac2a318cc228e95e56142d3b00756252e9dd`。已保存类型、方法、调用关系与字段元数据，未加载程序集或执行模拟。

证据文件 `rea-bobsbuddy-classification.json`、`rea-bobsbuddy-members.json`；后者证据 ID `ev_f04f0e894e51c88cea8b1ebd2df2e41edfecd75da79a2d0d3b9eec258bdb5680`。这为下一阶段定位其局面输入、模拟入口、结果结构提供基础，**不证明当前版本卡牌覆盖完整，亦未完成跨语言接入**。HDT 的公开源码入口见 [HearthSim/Hearthstone-Deck-Tracker](https://github.com/HearthSim/Hearthstone-Deck-Tracker)。

已进一步定位 `BobsBuddy.Simulation.Simulator.SimulateForInput`：公开实例方法 token `0x0600043e`、文件偏移 `0xb104`，输入签名为 Input 与两个 Int32，返回 Output；它的 CIL 调用锚点指向重载 `0x0600043f`（文件偏移 `0xb134`）。后者包含对 `SetupSimulation`（token `0x06000436`）及 `SimulateFight`（token `0x06000443`、文件偏移 `0xb5ac`）的调用锚点。两个整数参数的含义仍须核对参数表/调用者，不能直接假定为次数与时间预算。

Input 类型 token `0x02000131` 含 Player、Opponent、双方队友的属性后备字段，以及 Anomaly、isDuos、DamageCap、turn、availableRaces；Output 类型 token `0x02000132` 存在 damageResults 字段。更完整入口索引保存在 `bobsbuddy-entrypoints.json`。这些是实际元数据与 IL 锚点证据；完整控制流、字段语义及兼容性仍待验证。

## 三个功能如何在咕嘎配合

以下是方案与本地代码核对，不是盒子已复原实现。

### 场上随从：先得到可信的局面

现有 `core/bg_log_capture.py` 按 PowerTaskList 主流去重，并捕获客户端选项和 SendOption；`core/bg_observation.py` 负责字段归一化。不能只取卡名、攻击、生命：实体 ID、所属控制器、区域、站位、伤害、附魔、关键词、变形、英雄能力、酒馆等级和当前阶段都影响模拟。

建议统一快照字段：`game_id / client_build / log_offset / revision / phase / turn / controller / boards / hand / shop / resources / legal_options / unknown_fields`。事件推进 revision；日志轮转、断档和未完成的事件块不得悄悄当成空场。商店、本方战场、对手上次见到的战场须区分来源与时效；对手历史阵容不是其当前已知阵容。

验收：选三段固定日志（正常招募、三连/发现、断档重连）重放，逐实体核对区域与站位；同一事件重复读取不改变状态；缺失字段保留 unknown。暂不需要实时运行游戏。

### 胜率：给定局面的战斗概率和买牌价值分开计算

`core/bg_combat_review.py` 可读 HDT 文本记录并区分模拟概率/实际战果，但缺少可靠局 ID 与时间对齐，尚不能自动把记录贴到当前局。`core/battle_sim.py` 是简化引擎，不能包装为真实 HDT/盒子精度。

建议提供 `simulate(snapshot, seed, simulations, time_budget)` 接口，返回胜/平/负、伤害分布、引擎版本、卡牌效果覆盖、有效模拟次数和失败原因。固定双方真实局面后运行多次随机战斗；抽样误差与规则遗漏分别披露。二项比例标准误差约为 `sqrt(p*(1-p)/N)`；N=20000、p≈0.5 时，95%抽样区间约 ±0.69 个百分点，**不包含规则错误、未知对手阵容等系统误差**。

“买这张牌后胜率增加多少”还需要合法地推演购买、卖出、出牌、站位、触发效果，再调用战斗引擎；升本、刷新也涉及未来收益，不能仅凭当前战斗胜率贪心。模型负责战略候选和解释，完整规则/搜索器计算候选价值；没有引擎支持的效果返回 unsupported，而非编造概率。

### AI 接管：使用咕嘎自己的执行闭环

已有 `core/bg_live.py` 的 LiveReader、candidates、model_pick、ground_action、acknowledged，以及 `core/bg_live_windows.py` 的窗口定位与执行后端。决策模型读取结构化局面，从客户端合法候选 ID 中选择；视觉模型仅负责阶段核对与坐标定位。输入前检查局面 fingerprint 未过期，输入后须同时看到候选选择回执与相应状态变化；超时、发现弹窗、低置信度就停。

**当前边界**：尚无管理员实例一次真实操作成功回执。此前普通权限桌宠无法向管理员炉石输入，用户表示会手动以管理员身份启动并测试；不能将代码存在当作已能自动下棋。本轮没有更改权限，也没有继续实机输入。

建议动作样本记录：`state_revision / candidate_id / model_reason / execution_status / option_ack / state_delta / combat_prediction / actual_result`。把观察、决策、执行、结果对齐，才可用于模仿学习或离线八智能体训练。只观察屏幕或只有整局胜负，不能直接得到每一步动作标签。

## 后续两个有界阶段

1. **先核对输入输出结构**：从已定位 BobsBuddy 模拟入口继续核对参数含义、Player/Entity 和结果字段，再与 HDT 源码及现有样例对应；确认许可证与目标版本后做纯离线适配。另在盒子实际运行的用户授权场景中，仅观察它自己的日志/配置/管道端点，验证是否有导出局面的现成途径。当前不得假定管道协议已知。
2. **再接入咕嘎**：先完成一段日志重放到局面、一个固定战斗的概率校验、一个真实动作的双回执三项验收，再扩展候选动作比较。逐步决策胜率、当前版本完整规则和全自动整局均未在本轮完成。

## 复核与保存

`analyze_pe.py` 仅读取目标，使用本目录 `python-tools` 中的 pefile/capstone 输出 `pe-structure-evidence.json`。REA CLI 的具体安装位置由分析环境决定；运行 `node <rea.mjs> inspect-pe-resources <HSAng.exe路径> --json` 或 `inspect-managed-members <BobsBuddy.dll路径> --json` 可复核相应证据。CLI、源码、技能分别安装；没有修改 Codex MCP 配置。

官网 REA 分析证据 `ev_6a800aab82b29b5d435044c97d698b52513ba68680c4ad5a04dd834ed5a38754` 只用于下载来源与网站结构，不能作为客户端胜率算法的证据。二进制偏移须绑定对应文件 SHA256，更新后重新分析，不沿用旧偏移。

本轮仅新增下载、提取、分析文件和技能引用；未修改炉石/盒子安装、普通 Edge TTS、模型 Key、自动充值或游戏安全设置；没有上传用户日志，也没有把二进制安装包发布到项目仓库。

## 2026-10-19 补证：官网 AI 策略宣传

官网 `https://lushi.163.com/` 的 `css/main.css` 将 `.home-swiper-item.third` 指向 [智能辅助宣传图](https://lushi.163.com/img/d49451382b.png)。实际下载并查看该图，明确出现 AI 策略引擎说明、游戏右侧推荐打法与顶部战斗概率示例。这是官方曾宣传此功能的直接证据；不等于本机当前发版已能使用、当前卡牌效果覆盖已验证，或存在第三方开放接口。图中文案没有算法、权重或消息协议。

证据本地文件：`output/hsbox-research-20261019/website/official-smart-assistance.png`；SHA256 `cae06ca906dc3251a0944a005a0e59338ebdb0f42e4e9a898ae0ca82448d6e35`。本轮仍未运行盒子安装器或实测其登录后推荐功能。故不能说盒子 AI 已并入咕嘎。
