# 从观察人类对局到咕嘎代打

2026-10-19，本阶段是用户正在下棋时的只读观察和采集实现。没有游戏输入、API 请求或在线训练；普通语音和现有聊天配置未修改。

## 本机证据

已找到正在更新的 `Power.log`，日志记录客户端 BuildNumber 为 254477、模式为 `GT_BATTLEGROUNDS`。经限定时长采样和同局历史回放，最终采样点关联了 **31 条 SendOption 选择与各自的候选表**。一次拖动可能包含多个客户端选择，因此这不是“31 个完整战略动作”，也不等于已有 31 条合格训练数据。

可核对的三段本局证据（本地日志时间）：

- 17:41:59.288：选择 `TB_BaconShop_DragBuy`，目标实体 369；随后资源已用值由 0→3，实体控制器 9→1、区域 PLAY→HAND，构成买入的状态回执。
- 17:41:59.971：选择手牌中的同一实体；随后区域 HAND→PLAY、位置变为 1，构成出牌回执。
- 17:42:54.734：选择 `TB_BaconShopTechUp02_Button`；随后资源已用值 0→4、玩家酒馆等级 1→2，构成升本回执。

这验证了“操作选择—实体—后续结果”的关联思路。尚未确认的身份、费用字段、阶段、目标和最终名次仍须核对；缺少标签不自动填零，未解析的标签会单独计数。

原 `core/log_reader.py` 是简化场面摘要，不具备完整操作回放和可信候选接口。本次新增独立模块，不替换正在运行的读取器。

## 查阅的开源实现与结论

| 资料 | 本次核查的用途 | 对咕嘎的实现含义 |
|---|---|---|
| [HDT PowerHandler](https://github.com/HearthSim/Hearthstone-Deck-Tracker/blob/master/Hearthstone%20Deck%20Tracker/LogReader/Handlers/PowerHandler.cs) | 创建/更新实体、具名玩家标签、事件块 | 数字实体身份优先，具名玩家只在 RAM 中解析并转换成控制器，不持久化账号名 |
| [HDT TagChangeHandler](https://github.com/HearthSim/Hearthstone-Deck-Tracker/blob/master/Hearthstone%20Deck%20Tracker/LogReader/Handlers/TagChangeHandler.cs) | 旧值/新值和创建阶段的延后处理 | 保留变化前后状态，不能每行当成已稳定局面 |
| [Open Battlegrounds Overlay parser](https://github.com/Oliviu-nbx/open-battlegrounds-overlay/blob/main/parser.py) | 本人/Bob、商店标记、战斗快照、资源 | 招募与战斗状态分开，商店不能只按控制器划分；只在确认结果后结算名次 |
| [python-hearthstone](https://github.com/HearthSim/python-hearthstone)、[hsdata](https://github.com/HearthSim/hsdata) | 枚举、卡牌定义和版本元数据 | 将观测到的 CardID 与版本匹配的数据联结；新数值标签先保留，不猜含义 |
| [AutoHearthStone](https://github.com/Joooook/AutoHearthStone) | 视觉定位和界面输入的工程参考 | 可以研究识别/交互思路；项目已于 2025-05-20 归档，不能据此声称当前战棋可用 |

两套 `GameState.DebugPrintPower` 与 `PowerTaskList.DebugPrintPower` 会重复描述变化。采集器只以已处理的 PowerTaskList 流作为实体变化源，同时保留 GameState 的候选表和选择记录。`SendOption` 是日志证据，不是已经提供给 Python 调用的游戏 API。

## 实现和运行

新增 `core/bg_log_capture.py`、`tools/observe_bg_logs.py`：仅输出白名单结构化事件，不输出原始日志行、昵称、GameAccountId 或账号字段。新数字标签保留原编号，不赋予未经核实的语义。具名玩家与数字实体的映射只在进程 RAM 中存在。

`tools/build_bg_demonstrations.py` 按事件顺序重建每次选择之前的匿名上下文、候选表、实体、目标与位置。样本固定标注 `training_ready=false`，避免把采集成功等同于训练样本合格。

```powershell
python tools/observe_bg_logs.py --seconds 180 --output 'new-observation'
python tools/build_bg_demonstrations.py 'new-observation/events.jsonl' --local-controller 1 --output 'new-demonstrations.jsonl'
python -m pytest tools/test_bg_log_capture.py -q
```

控制器 1 是本机这次日志中的观察值，其他对局不能照抄。正常入口有有限时长和独立工作进程，数据放在调用方指定的新目录。本轮日志采样已结束，后续可重跑有限采集；没有留下常驻后台观察器。

## 完整代打架构

1. **读取**：日志构建有版本和来源的实体状态、候选表，识别商店/手牌/棋盘、阶段、发现/目标、剩余时间和状态是否稳定。视觉只补充按钮位置、遮挡、弹窗等日志之外的界面信息。
2. **决策**：本地规则/搜索先筛选；DeepSeek 选择有身份的合法动作，并给出少量战略理由。策略模型可以处理高频选择，大模型不必对每帧或每个战斗动画发请求。
3. **执行规划**：将动作映射成界面点击/拖动及目标/位置。模型只输出实体/候选标识，界面适配器根据实际画面计算位置，避免模型猜坐标。
4. **状态校验**：执行前重查 game/revision/option_set、阶段、费用和目标。用户继续操作或候选表更新即丢弃旧建议；不执行整条过时操作序列。
5. **结果确认**：一次操作后等待金币、区域、控制器、等级等实际回执。回执缺失或不符合预期时重新观察，不能盲目重复购买或升本。

现有桌宠单步决策工作台、离线模拟器和本次日志采集是三个不同入口，尚未自动连成实服代打。本阶段没有控制鼠标或替用户下棋。

## 人类示范如何训练

这些资料首先用于建立真实客户端回放和验证模拟器。随后将身份、有效费用、目标、阶段和回执齐全的决策筛成 `(可见局面, 合法候选, 人类选择, 结果)`；保留最终名次/对手/版本与失败分支，并以对局为单位划分训练与测试，防止同局相邻片段泄漏。

人类的选择不自动视为最优，可与搜索、规则策略和复盘比较。用筛选后的样本预热本地策略，再进行离线自博弈和独立评测；不在用户下棋时自动更新权重或把未经审核的数据直接灌入模型。

## 操作、阵容、插件胜率与实际结果复盘

本机 HDT 安装目录的 `对战记录/YYYY年M月D日.txt` 包含回合、双方英雄、双方有序随从名称/攻血、模拟次数、胜/平/负及双方淘汰概率、实际伤害/输赢和最终名次。该来源不同于桌宠 `core/battle_sim.py` 的近似计算；两者不能混称为插件实测胜率。

`core/bg_combat_review.py` 与 `tools/review_bg_combat.py` 增加独立的只读解析和 Markdown/JSON 复盘导出：

```powershell
python tools/review_bg_combat.py --hdt-record 'HDT/对战记录/2026年10月19日.txt' --output 'new-review'
# 可额外附加已脱敏的 Power.log 快照和本地卡牌缓存；仍分开列出，不自动合并对局。
python tools/review_bg_combat.py --hdt-record 'record.txt' --output 'another-review' --power-snapshot 'observation/latest.json' --local-controller 1 --carddefs 'CardDefs.base.xml'
python -m unittest tools.test_bg_combat_review -q
```

重复的相同回合/英雄/双方阵容头会合并；不同估计、不同阵容、冲突实际结果保留。显式游戏结束与回合倒退用于划分来源片段；英雄变化本身不拆局，避免误拆变身英雄。文本缺少局 ID 和战斗时间，片段编号不视为已验证真实游戏 ID。文件末尾尚未写完的行不做有效战斗数据；未知阵容和观察到的空场分开。

本轮核查发现该文本末尾是托奇第 4 回合，而更新中的 Power.log 展示雷诺较后回合。两份来源尚未对齐：既不能凭同一天就拼为同局，也不能只凭英雄名不同断定是不同局（还需考虑英雄变换）。需要进一步取得同局标识、战斗时间或能确认的双方阵容关联，才能把胜率变化附到某次购买/站位操作上。不能从这份文本独自还原购买、出售和刷新。

安装的 HDT `CardDefs.base.xml` 可以补充咕嘎旧卡库缺少的 BG36 卡名和效果模板。导出注明缓存来源/修改时间和版本匹配未验证；动态 `{0}`/`{1}` 效果保留模板，不能拿静态基础值替代本局脚本数据。附加快照只展示观察到的实体，不宣称战斗阶段、正式招募阵容或场面稳定已确认；不填入来自其他对局的插件胜率。

这些复盘用于后续评估「操作前可见局面 → 人类选择 → 状态回执 → 同场战斗估计/结果 → 最终名次」。模拟概率不是实际结果；被抬走概率属于负率子集，不与胜/平/负再次相加。单场输赢也不是最优动作标签。导出保持 `training_ready=false`，不调用模型，不发送私有日志，不改变游戏输入、语音或聊天配置。
