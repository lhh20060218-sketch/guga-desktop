# DeepBattler 决策协议与本地执行层：接入和实机验收记录

时间：2026-10-23。本轮采用用户明确选择的路线：现有 DeepSeek API 运行 DeepBattler 动作协议。没有加载 DeepBattler 的 Qwen3-4B LoRA，不以此宣称获得其训练实力。

## 已接通的代码路径

`LiveSession → StrategyEngine → bg_deepbattler.model_pick → bind_first → OperationEngine → 日志回执`

- 决策层配置 `strategy_mode=deepbattler`、`bg_deepbattler_transport=existing_api`；仅更新这两个本地配置项，保留现有密钥和语音配置。
- 本方棋盘、手牌和商店转换为 DeepBattler 使用的有序数组；牌名和效果优先来自已有卡牌资料，实体身份保留。
- BUY_FROM_TAVERN、PLAY_FROM_HAND、SELL_FROM_BOARD、ROLL、UPGRADE_TAVERN、FREEZE 映射到已有客户端合法候选。模型索引必须有效，卡名必须与指定位置一致，站位从 0 基索引转换为本地位置。
- 整回合计划只采用第一步，其余步骤不发送；下一步必须重新读取局面。禁止跳过不支持的首步去执行后续步骤。
- END_TURN、空计划和已冻结商店再次 FREEZE 作为等待，不发送输入。英雄技能、法术、发现、任意换位尚未打通，不能宣称整局全功能自动下棋。
- 可选 `endpoint` 传输兼容上游 `/generate_actions`。它不接收用户的聊天 API Key；远端模型身份尚未实测验证。

## 修复的真实接口故障

第一次真实请求返回 HTTP 400：缺少 `x-opencode-session`。已按 [OpenCode Go 官方客户端要求](https://opencode.ai/docs/go/#where-can-i-use-it) 添加真实客户端名 `GugaBattlegroundAgent/1.0` 和稳定的每局会话 ID，不冒充其他客户端。不同选项代次不改变同局会话，新局更换会话。

补齐后，使用构造局面完成一次真实 API 调用：

- 模型：`deepseek-v4.1-flash`。
- 用时约 2016 ms；输入 1111 token，输出 34 token，共 1145 token。
- 返回 PLAY_FROM_HAND，映射为本地合法 PLAY，实体 4，插入位置 2。
- `input_sent=false`、`fixture_only=true`、`upstream_weights=false`。

这只证明模型接口及动作适配成功，不证明真实游戏操作成功或棋力。

## 日志启动边界

实测当前游戏启动目录已创建，但尚无 Power.log；旧逻辑回退到了前一天的日志，得到历史战斗阶段。新增 `find_log_path(current_session=True)`：实战入口、诊断、准备流程只接受最新启动目录的 Power.log，等待当前进程首次写入，不能把旧局面当成当前状态。旧日志分析默认仍可选择历史日志。

注册表安装路径的日志子目录也纳入发现，准备流程使用最近一局增量读取。

## 验证结果

截至本次记录，72 项相关测试通过，覆盖协议映射、同名/索引、手牌法术占位、非法动作、只取首步、等待、会话稳定性、HTTP 故障、新进程日志边界、既有执行回执和 director 流程。Qt 面板通过 offscreen 冒烟并自动退出。测试均未发送真实游戏输入。

用户恢复炉石前台后，截图可确认酒馆大厅和“开始”按钮。只读权限探测确认测试进程和炉石完整性级别均为 8192，均非管理员。本轮 Computer Use 输入仍返回 `foreground window did not report a process id`；重新激活返回 `failed to activate captured window`。因此没有确认开始匹配、选择英雄、买牌或出牌成功；未使用其他输入方法绕过工具失败。

## 用户可直接查看的测试入口

双击工程根目录 `战棋实机测试.cmd`，打开独立实战面板；进入真实招募后使用“模型执行一步”或“限时连续操作”。面板读取新配置，连续模式最多 12 步、4 分钟，并显示决策、已发送输入和日志确认结果。Esc 或“停止操作”中止。

只读决策验证：`python tools/bg_core.py plan --strategy deepbattler --output runtime/bg-live/deepbattler-plan.json`。该命令只生成计划，不点击、不拖动。当前没有新局日志时会直接说明原因。

本轮仍需真实新局验收，不把本地代码测试和构造局面 API 调用替代实机结果。入口内存调用桥尚未实现；开始匹配依旧未验证成功。

用户随后手动开始并选择托奇，新 Power.log 已生成。只读入口在 13:43:26 对真实招募局面完成一次 DeepSeek 请求，约 1922 ms、635 token，返回 END_TURN，执行状态为等待，没有输入。这不证明已操作棋子。用户明确反馈没有实际操作，实机验收仍未通过。第一回合早期未出现明确阶段标签时，当前执行器会暂停；不以视觉猜测强行改写阶段。
