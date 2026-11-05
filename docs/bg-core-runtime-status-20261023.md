# 独立战棋核心：2026-10-23 实测阶段交付

## 当前结论

尚未实现真实客户端内存自动下棋。已具备日志状态解析、候选动作生成、本地/DeepSeek 一步决策、窗口输入执行器。HearthMirror 是读取通道；没有发现其公开接口可直接执行购买、出售或出牌。

本轮没有启动桌宠，没有发送游戏输入、写入游戏内存、修改客户端文件或系统权限。静态读取了本机 HDT 的 HearthMirror.dll 和炉石 Assembly-CSharp.dll。只新增/修改战棋核心、诊断工具和相关测试。

## 本轮发现与修复

- 当前 build 254477 的真实 Power.log 使用 `BACON_IN_COMBAT_PHASE`。此前解析器未收录这个字段，导致已出现招募候选仍被判为 unknown。已加入解析和阶段判定，并测试 recruit/combat 切换。
- `GetBoardState` 的布尔参数为 `includeFriendly`；此前传 False，已改为 True。
- 读取接口不再复用窗口输入的权限预检查。订阅 HearthMirror 自己的 AccessDenied 事件，将实际拒绝与未取得棋盘区分，错误码通过子进程保留。
- 实测令牌：检查进程完整性 8192，游戏进程完整性 12288。HearthMirror 实际触发 AccessDenied。这是当前读取阻塞的证据，不能称为模型或网络问题。
- 独立入口 `tools/bg_core.py` 不加载桌宠 UI，支持 probe 和仅计划不执行的 plan。
- 动作编译器将当前合法候选转换成选项批次、选项索引、目标实体、子选项、站位字段；局面过期、被篡改或阶段不符时拒绝。输出明确标记 `transport_ready=false` 和 `executed=false`。

## 客户端内部动作的静态证据

本机程序集包含 GameState.SendOption、SetSelectedOption、SetSelectedSubOption、SetSelectedOptionTarget、SetSelectedOptionPosition。SendOption 的 IL 读取当前选项批次和选择字段，调用 Network.SendOption；后者调用 Networking.ConnectAPI.SendOption。InputManager、MoveMinionHoverTarget 存在调用 GameState.SendOption 的实际 IL 锚点。

这说明后续值得研究客户端自己的动作分发流程。它不是开放的外部 API，也不证明外部 Python 能调用成功。尚缺运行时对象获取、正确线程/上下文调度、版本核验和实际状态回执；没有进行注入、附加调试或运行时调用。

完整程序集哈希、方法签名和 IL 证据：`runtime/bg-client-action-evidence-20261023.json`。这些是本地 Mono.Cecil 静态检查结果，不冒充 REA 保留证据或真实执行结果。

## 策略实力

已训练的是本地小策略网络，不是 DeepSeek 的模型参数。DeepSeek 当前读取结构化局面和可用的策略先验进行推理。

既有近似模拟器独立评测每组 16 局：规则策略平均名次 2.875，模仿模型 3.78125，PPO 4.125。候选未晋级。当前效果卡中仍有 50 张没有专用规则，英雄/饰品等尚未完整接入，不能用这些结果证明真实天梯实力。

## 使用与下一阶段

1. 双击根目录 `战棋核心-读取诊断.cmd` 得到诊断；若游戏为提升权限而读取仍 AccessDenied，可由用户右键以管理员身份运行此诊断，再核对实际返回。该脚本不发动作。
2. 开发环境可运行 `python -X utf8 tools/bg_core.py plan --strategy model`，只在招募阶段有支持候选时调用现有模型；生成动作前再次读取并核对局面，过期直接拒绝。
3. 读取通道可用后再单独验证运行时动作桥：先一条合法动作及其日志/状态双回执，再扩大动作覆盖和速度测试。HDT 读取成功不能替代动作桥验证。
4. 继续补齐同版本模拟器规则、独立评测策略。策略训练与客户端动作执行分别验收。

本轮 43 项相关回归测试通过。尝试当前局仅规划时分别遇到无合法候选、战斗阶段，工具正确停止；未将失败包装成执行成功。没有后台训练或操作进程持续运行。
