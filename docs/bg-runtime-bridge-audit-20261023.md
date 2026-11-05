# 战棋运行时桥审计：2026-10-23

## 可验证结论

客户端确实存在内部发送动作流程；**当前尚无已验证的外部动作桥**。HearthMirror 的本机版本可以作为读取接口候选，不能当成购买、出售、出牌的执行 API。此次仅静态读取程序集，不附加炉石、不发送输入、不改变权限、不写入游戏内存。

已新增可复现的静态审计器 `tools/bg_runtime_audit.py`，实际运行成功。它只向 Python 加载 HDT 自带的 Mono.Cecil 元数据解析器，目标程序集通过 `ReadAssembly` 作为数据读取，不向 Python `AddReference` 炉石或 HearthMirror。无需安装组件，无网络调用。

| 本地制品 | 已核验 SHA-256 |
|---|---|
| `G:\游戏\Battle.net\Hearthstone\Hearthstone_Data\Managed\Assembly-CSharp.dll` | `786376bddad544709639d4b3ab60ce8799d4b1c6c7d7fc4c225ce79fe07228c6` |
| HDT `HearthMirror.dll` | `3cc1180b89582127fe737d0a8c6e03f13d460437a43511a6fc382bc958f31d1d` |

客户端哈希与既有 `runtime/bg-client-action-evidence-20261023.json` 一致。因此可以复用之前的静态证据；不表示运行时兼容性或执行成功。审计器会明确标记哈希变化，避免客户端更新后静默沿用证据。

## 已确认的动作调用与上下文限制

扫描包括嵌套类型，不只是顶层类型。共有 6 个直接调用 `GameState.SendOption()` 的方法：

- `InputManager.DoEndTurnInternal()`
- `InputManager.DoNetworkOptions(Entity, GAME_TAG)`
- `InputManager.DoNetworkSubOptions(Entity)`
- `InputManager.DoNetworkOptionTarget(Entity)`
- `InputManager.DoNetworkOptionReverseTarget(Entity)`
- `MoveMinionHoverTarget.DropCardOnHoverTarget(Card)`

既有证据中的 `GameState.SendOption → Network.SendOption → Networking.ConnectAPI.SendOption` 调用关系得到复核。选项选择与实体拖放分属不同输入流程，绕过屏幕坐标并不等于可以只改棋子数值：合法选项、目标、子选项、站位、服务器确认仍是必要状态。

观察到 `InputManager.Update()`、`GameState.Update()` 以及上述输入入口。**未观察其实际执行线程，未验证外部线程可安全调用**。静态方法名不能证明 Unity 主线程调度已经解决。

`Networking.QueueDispatcher` 的实际接口为连接、收包、发包、网络队列处理等。其名称含 Dispatcher 不代表它是外部可调用的 Unity 主线程任务调度器。此次没有把它当作执行通道，也没有运行其网络方法。

## HearthMirror 的 IPC 不是现成的下棋 RPC

已完整列出本机 `HearthMirror.IReflection` 的 77 个方法。它们均为 `Get*`、`Is*` 或 `FindDeckTemplateIdForDeckId` 查询；不存在 `SendOption` 或购买、出售、出牌入口。

静态 IL 进一步确认：

- `Reflection` 的初始化创建 `LocalReflectionProxy<IReflection>`。
- `IpcClient` 的初始化创建 `RemoteReflectionProxy<IReflection>`。
- `IpcClient.MaintenanceThread` 使用匿名管道启动辅助子进程并建立 JsonRpc 管道。

因此“存在 IPC / JsonRpc”只能证明有辅助读取进程通信；两个代理都围绕同一查询接口。没有证据证明这个管道能向游戏分发动作。不能把序列化 `SendOption` 消息交给它，就宣称存在执行桥。

可复用的数据接口包括 `GetBoardState(includeFriendly)`、`GetDiscoverState`、`GetBattlegroundsHeroOptions`、`GetAvailableBattlegroundsRaces`、`GetBattlegroundsLobbyInfo`；其在当前局的返回值和时效性仍须分别验证。本轮没有读取账号、好友、收藏或其他无关数据。

## 下一步实施判断

1. 当前现成可复用的是 **日志状态源、HearthMirror 查询接口、候选动作编译器和窗口输入执行器**。本轮未找到可以直接替代窗口输入的现成动作组件。
2. 读取权限问题与动作执行桥是两个独立验收项。既有诊断记录为普通脚本完整性 8192、游戏 12288，实际 `AccessDenied`；本轮未再次探测，不把历史结果当成当前权限。
3. 若后续研究运行时调用，先在自有测试宿主验证同线程调度、局面版本核对、重复请求去重、超时取消和回执。仅找到内部方法名不满足进入实局执行的条件。此次未实现注入、远程调用或任意写内存接口。
4. 执行通道的必要验收仍是：新鲜局面和合法候选 → 实际动作发送 → 客户端日志确认 → 对应实体状态变化。静态审计器始终输出 `transport_ready=false`，不能用它的成功退出码代表自动下棋成功。

## 复现与测试

从项目根目录执行：

```powershell
python -X utf8 tools/bg_runtime_audit.py --assembly 'G:\游戏\Battle.net\Hearthstone\Hearthstone_Data\Managed\Assembly-CSharp.dll'
python -X utf8 -m unittest tools/test_bg_runtime_audit.py -v
```

实际审计约 10 秒完成，返回哈希匹配、6 个直接调用者、77 个读取接口，未发送输入或写入内存。3 项测试通过：证据哈希变化会被标记、嵌套类型不遗漏、摘要绑定实际文件字节。

可用 `--output <新文件路径>` 保存详细 JSON（含方法签名与调用边），输出文件采用独占创建，已有文件不会被覆盖。未指定该参数时不落盘证据，不会意外复制账号配置或密钥。

本报告使用 `reverse-engineer-anything` 技能，先复用该技能的 `references/hearthstone-box.md` 与项目现有证据，再使用本机 Mono.Cecil 作定向静态检查。上述不是 REA 保留证据 ID，也不是运行时执行记录。尚未确认炉石盒子的私有协议和动作接口，不能宣传“盒子 AI 已接入”。
