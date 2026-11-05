# 社区动作素材筛选与任务自动触发

## 本轮结论

任务事件自动触发已经接入源码；没有把低帧率或形象不符的素材冒充合格动画。当前默认仍为原画的轻动作，渲染计时器33ms（约30Hz）。没有新增图像生成、视频生成、模型请求或付费服务。

目前找到的公开素材没有同时满足：原形象一致、原生连续帧20–30fps、透明边缘干净、动作自然。未将候选复制到正式动作包，也未重新打包EXE。

## 数据来源与本地实测

候选位于 `runtime/references/guga-community-20261102/`；API仅用于查仓库和公开文件，不运行第三方安装脚本。

| 来源 | 实测 | 审核结果 |
|---|---|---|
| Eijnewgnaw/gugugaga-codexpet | 低头搅手GIF：10帧/1.7秒，5.882fps；图集单格192×208 | 形象较接近，但帧率未达标，留作参考 |
| zzzhanga/gugugaga | waiting约5.94fps，failed约6.56fps，idle约5.45fps | 有任务动作编排，低帧率，不接入 |
| WilliamK112/gugugaga-desktop-assistant | thinking20帧/4.2秒；curious20帧/3.4秒；celebrate16帧/2.4秒 | 实际为4.76–6.67fps，且围巾、服装、发型偏离原形象，不接入 |
| guleguleguru/gugugaga-pet | 已有192×208基础动作候选 | 不是高帧率复杂动画，未获准替换原画 |
| quanqiubianlen/gugugaga、Peacefuldoge/PocketPet | 查公开仓库文件树，分别8/62张PNG，无独立视频/GIF | 未发现可直接取用的完整高帧率动作包 |

另查到多个Codex图集仓库，但图集存在不代表有24/30fps完整动作；不继续无上限下载。仓库许可证分别保存于候选目录；素材再分发仍按具体来源核对，不能把“GitHub可见”当成授权。

原始链接：
- https://github.com/Eijnewgnaw/gugugaga-codexpet
- https://github.com/zzzhanga/gugugaga
- https://github.com/WilliamK112/gugugaga-desktop-assistant
- https://github.com/guleguleguru/gugugaga-pet
- https://github.com/quanqiubianlen/gugugaga
- https://github.com/Peacefuldoge/PocketPet

## 修正的实际漏接

旧 MultiAgentManager.work_state 仅查召唤出来的伙伴，001本体没有入口。现已把001状态接到 SpriteAnimator；Dora接自己的动作调度器，大肥鱼保留原版透明视频状态入口。

任务阶段来自实际运行回调：
- 接受复杂任务：thinking（轻歪头）；简单任务不足1.2秒不闪动作。
- 工具开始：working（点头）。工具回执后回到thinking。
- 等待外部结果：waiting（原画轻探头）。
- 内层完成校验后：success（点头回应）；失败：error（轻摇头）。
- DSH返回但未独立核验：result，不庆祝为已验证成功。
- 取消：cancelled，移除任务状态；父任务返回而sidecar仍运行时继续显示工作状态。

相同状态动作间隔10秒，切状态至少间隔2.5秒；不增加模型调用。困倦、显式情绪、唱歌、说话、拖拽和当前手动动作优先。停止手动干预后，持续任务可恢复轻动作；已过期完成动作不会补播。

## 后续合格素材如何接入

`resources/actions/task-motion/manifest.json` 当前 states 为空，避免无审核换图。

每个状态可指定 `frames` 与 `native_fps`；加载器校验路径范围、原生帧率20–60，以及同目录 visual-review.json 的视觉审核和帧SHA256。正式帧动画播放时不再叠加原画程序形变，避免双层摆动；按源帧率推进，不加速、不复制帧假充30fps。

这一适配器还没有合格外部素材的实机验证，不能宣称完整复杂动作已经完成。

## 可复查结果

`python -m tools.preview_task_motion` 生成14秒/420帧/30fps MP4：

- `runtime/task-motion-review-20261102/automatic-task-motion-30fps.mp4`
- `runtime/task-motion-review-20261102/events.json`
- `runtime/task-motion-review-20261102/contact.png`

这是实际绘制器对模拟任务事件的自动反应，未手动逐次点播动作；它用于检查触发与原画保持，不是复杂动作素材验收。

本轮67项离线检查通过，覆盖本体与Dora状态路由、真实Qt任务回调、取消、并行父子任务、语音/拖拽/困倦优先级、原生帧率和审核关卡。未调用麦克风或真实云端模型；未替换当前运行程序或既有EXE。
