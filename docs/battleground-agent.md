# 咕嘎战棋智能体：第一阶段

新增：[八人离线自博弈与本地策略训练实验室](battleground-selfplay.md)。它与本页的单步决策工作台是两个独立入口。

当前版本是可验证的离线决策原型：算法生成和排序候选，大模型从候选中选择一步，程序校验状态版本与动作。它尚未具备完整实服规则、经过评测的高分策略或客户端自动执行。

## 打开与使用

重启桌宠后，在右键菜单或托盘中打开 **战棋决策实验室**。

1. 载入示例或导入结构化局面 JSON。示例为合成无效果随从，不代表实服卡牌。
2. 点击 **本地算法分析**：不联网、不消耗模型额度。
3. 点击 **模型 + 算法分析**：读取现有 `ai_config.json` 的文本模型配置，通过其原地址调用一次；消耗现有套餐额度。发送的是面板局面、候选及规则参考，不含配置密钥、账户信息或其他窗口截图。
4. 查看下一步动作、依据、限制和候选分数。修改输入后旧建议立即失效。

普通 Edge TTS、实时语音、已有聊天和视觉配置未改变；新增面板不自动启动这些功能。

CLI（项目目录）：

```powershell
python tools/bg_agent.py
python tools/bg_agent.py path/to/snapshot.json
python tools/bg_agent.py path/to/snapshot.json --model
python tools/bg_agent.py --log-check
python tools/bg_agent.py --ui
```

## 已实现的算法

- 以 `game_id + revision + 实体身份 + 局面内容` 生成状态指纹。
- 验证字段类型、容量、实体 ID 唯一性；未知数字保留为 `null`。
- 已声明基础经济规则下，生成购买、出售、无效果随从出牌、刷新、冻结、升本、选择和结束动作。只生成已知费用和货币满足条件的动作；普通场面上限 7、手牌上限 10。
- 按基础身材、圣盾粗略价值、替换收益、配对线索、金币和升本风险评分。
- 对已知无额外效果的买/卖动作进行最多两层有限推演。未知效果、三连、发现、刷新结果等不会被虚构；它们会终止相关分支扩展。
- 大模型只可选择提供的候选 ID，并返回相同状态指纹。幻觉动作、格式错误、旧局面或接口失败均有明确结果；失败时标明本地启发式回退，不自动重试。
- 一次只建议一步。再读取状态后必须重新决策；面板编辑、关闭或实时数据过期会使旧结果失效。

**候选 score 是手写启发式效用，不是概率、胜率或训练出来的价值网络。**

## 局面数据要求

参考 `data/bg_agent/demo.json`。`schema_version=1`；必须提供 `game_id`、`revision`、`patch`、`source`、`phase`。每个实体有全局唯一的 `entity_id`，`card_id` 用于识别同类牌，名称不能代替实体身份。

`rules_profile=vanilla-recruit-v1` 和 `economy_confirmed=true` 表示数据提供方已确认本局适用的基础费用；不能在尚未核对英雄、饰品、畸变等特殊规则时随便设为 true。该标志不等于本引擎已验证所有规则。

费用需显式提供：商店 `buy_cost`、场面 `sell_value`、选择 `choice_cost`、局面 `refresh_cost/upgrade_cost`；货币 `currency` 当前仅支持已知的金币。未知费用为 `null`，不会按零费用处理。

`effect=vanilla` 只用于数据提供方确认没有额外出牌/购买/出售触发的实体；其他使用 `unknown/targeted/special`。手牌未知效果、法术与磁力不生成盲目出牌动作。

有限推演还需要 `vanilla_transitions_confirmed=true`，声明已确认全局英雄/饰品等没有额外触发；未确认时仍可做基础候选排序，但不推演动作后的局面。其他可见实体有未知效果时也停止推演，防止遗漏它们对买卖/出牌的反应。

实时输入 `source=live` 还需要 Unix 秒时间戳 `observed_at`；超过 5 秒的观测不用于决策。离线导入和合成示例不套用实时过期阈值。

## 为什么现有日志还不能直接驱动完整智能体

旧的 `log_reader.read_current_board()` 主要服务于场面解读和简化战斗胜率，当前摘要缺少可靠的商店、手牌、有效费用、阶段与稳定实体 ID。“检查日志数据”只报告就绪情况，不把缺失数据补成虚构局面。

下一阶段需要独立观测适配器：将日志/视觉中的可见信息合并，标注来源与未知字段，并核对当前剩余血量和可用金币（不能直接把最大资源当余额）。不应把战斗中的临时状态当成招募局面。

现新增 `core/bg_observation.py` 作为纯数据转换起点。导入面板可识别含 `entities` 的显式标签快照，CLI 可加 `--tag-observation`。它不读取真实日志或进程，不猜测阶段和身份：调用方须提供本地/商店控制器、英雄/玩家实体 ID、阶段、版本和有效费用。金币由 `RESOURCES + TEMP_RESOURCES - RESOURCES_USED` 计算，血量由 `HEALTH - DAMAGE` 计算；缺标签保留未知，商店买价不会从普通 `COST` 字段推断。示例测试使用匿名合成标签，实服标签语义尚需独立对照确认。

## 社区研究怎样落到代码

| 来源 | 借鉴的设计 | 本项目采取的实现 |
|---|---|---|
| [HSBRSIM](https://github.com/Gallo13th/HSBRSIM) | 实体、动作掩码、策略与价值分工 | 独立数据格式、基础合法动作和有边界的算法候选 |
| [DeepBattler](https://huggingface.co/spaces/iteratehack/deepbattler/tree/main) | 结构化局面、模型返回动作 | 模型只能选择候选 ID，结果经过独立校验 |
| [Rizling 公开前端](https://rizling.top/static/app.js) | 状态代次与旧建议失效 | 指纹校验、面板输入代次、异步迟到结果丢弃 |

以上是设计参考，新增代码为本项目编写，没有将第三方仓库代码或权重并入仓库。

不能直接照搬的部分：HSBRSIM 的 `bc_train.py` 只用动作类型损失；DeepBattler 的公开训练奖励主要按候选动作序列匹配。它们不能直接证明当前版本高分棋力。

## 规则来源与覆盖

`data/bg_agent/rules.json` 存储带来源与日期的少量补丁事实，随模型输入提供。当前引用客户端总补丁 37.0 与战棋平衡 36.6.3；它不是完整卡池或规则实现，patch 标签也不代表已经完成版本适配。

来源：[36.6.3 官方补丁](https://hearthstone.blizzard.com/en-us/news/24303864/36-6-3-patch-notes)、[36.6 介绍](https://hearthstone.blizzard.com/en-us/news/24294373)、[37.0 说明](https://hearthstone.blizzard.com/en-us/news/24301454)。

## 验证与下一阶段

```powershell
python tools/test_bg_agent.py
python tools/test_bg_observation.py
python tools/smoke_bg_agent.py
```

离线测试核对动作合法性、资源/容量、未知规则停止推演、状态失效和 API 错误回退；面板测试核对异步结果、编辑失效及分析中关闭。不启动炉石、不调用模型或麦克风。

后续顺序：补齐观测格式与当前卡牌语义 → 建立人工审核的战略参考局面集 → 比较大模型、启发式与二者结合的效果 → 再评估小型策略模型/专家轨迹微调。棋力应以独立样本与对照评测验收。实机阶段继续遵循用户暂缓要求。

现有 DeepSeek 配置的文本接口可以复用；多模态输入能力在本阶段未验证，也未将普通文本接口当成已验证的图像识别通路。
