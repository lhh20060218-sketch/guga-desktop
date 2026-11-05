# dsh-pet 独立移植与咕嘎高级动画路线

## 来源与结论

- 源码：https://github.com/PC2005-cloud/dsh-pet
- 读取提交：0ed254518cd4c20db1219fe0a3fcfc086f0e743d；npm 安装：0.3.8。
- 源码位于相邻目录 `../dsh-pet`。这是公开源代码分析，无需反编译二进制。
- 私有安装目录：runtime/dsh-pet-standalone；使用 --ignore-scripts --legacy-peer-deps，未升级 DSH，未复制任何 API Key。
- 上游原生 standalone 已有 DSH 替身 context、本机 HTTP 服务和 Electron helper；无需再移除整个 DSH 内核。
- 本次采用 Qt 原生适配以连接已有记忆、菜单和语音，避免并排再养一个与智能体身份脱节的 Electron 宠物。

## 交互感与立体感的实际来源

1. 上游 109 段 VP9-alpha WebM 动画，约 55.3 MB；不是实时 3D 骨骼渲染。
2. 生成视频时提前设计转身、脚步、重心、头发和表情；不是仅对整张图片旋转。
3. 按秒编排，统一角色比例、脚底基线和标准站姿；多数动作回到同一站姿。
4. 视频前后台交接、过时请求取消、睡眠开始/循环/起来接力。
5. 鼠标点击挤压曲线、释放速度估计、重力和边界反弹；AI 只决定何时选动作。
6. 上游制作说明强调高质量抠像：现有动作采用 PR 手工抠像；自动抠像只是可复现兜底。

## 本次实现范围

- resources/multiagent/dafish/dsh-pet：保留全部 109 段原文件、动画池、SHA-256、署名许可。
- ui/video_mascot.py：独立 Qt 播放器，PyAV/libvpx-vp9 保留透明通道；后台工作线程、最多六帧队列、取消旧切换、解码错误停止重试。
- 大肥鱼：现有智能体身份、记忆、菜单和缩放继续使用；点击/悬空拖拽/睡眠/工作/说话/舞蹈映射到原动画；右键可按原分类点播动作，漫游默认关闭。
- ui/pet_physics.py：借鉴上游曲线与参数，Qt 逻辑坐标内拖拽释放、抛掷、屏幕边界反弹；新按下或右键停止惯性；单次最多八秒，避免后台无限运动。
- 咕嘎保留原画、原表达语义与睡眠保持；新增轻点击回弹和释放惯性。
- 这是原素材复用加原生适配，不声称上游全部功能逐行等价：上游弹弓、宠物互撞、钱包、托盘设置页等没有完整移植。
- requirements 新增 av，Windows 打包脚本加入 av 收集；本轮未构建新的安装包。
- tools/dafish_standalone.py：完全无需 DSH、模型或麦克风的独立动画窗口；根目录「大肥鱼独立动画.cmd」启动。
- main.py 新增 --summon-fish，启动本地完整咕嘎后召唤 002。

## 验证与现状

- 69 项相关测试通过：含真实透明解码、109 文件校验、睡眠保持、快速切换清理、物理边界、既有同伴、表情、身份、语音路由。
- runtime/dsh-pet-upgrade/native-animation-review.png：实际 Qt 渲染器六动作画面审核。
- runtime/dsh-pet-upgrade/native-motion-review.gif：原版大肥鱼转身与原画咕嘎回弹对照；不是新生成的咕嘎舞蹈。
- 独立桌面窗口有限运行四秒：visible=true、frames_received=true、decode_error为空、queue_size=6、未打开麦克风；自动退出。回执为 standalone-live-check.json。
- 截至该回执，未启动持久的新完整主进程，未把有限验证说成用户已验收。
- 上游 npm standalone 的 --check 返回 0，但提示 Electron 尚未下载；本次 Qt 原生独立模式不需要 Electron。
- 回退：runtime/dsh-pet-upgrade/before-20261031-172732.zip，以及 before-extra-files.zip；未覆盖用户现有 Git 索引或提交全部历史脏文件。
- 先前长语音识别异常仍待单独诊断；本次语音路由回归通过不代表麦克风实测已恢复。

## 用户最新讨论：咕嘎高级动图

推荐制作顺序：固定原画和背侧面参考 → 图像工具做一致关键画面 → 图生视频或动作迁移 → 逐段审核 → 透明抠像 → 统一基线和首尾 → WebM 接入。

- 静态 image 工具适合角色设定、表情、动作关键帧，不能单独保证复杂舞蹈连续性。
- Wan2.2 Animate 可用角色图和参考动作视频传递动作与表情；官方强调身体比例差异需动作重定向并检查预处理。
- 主源：https://github.com/Wan-Video/Wan2.2 ，https://github.com/Wan-Video/Wan2.2/blob/main/wan/modules/animate/preprocess/UserGuider.md
- 本机核对为 RTX 4070 Laptop GPU / 8188 MiB；不能据此承诺大型视频模型本地顺畅运行。
- 当前已发现的可调用生成工具是静态 image_gen，没有直接可调用的视频生成连接器；没有付费视频请求或模型大下载。
- 第一条适合验收的小样：约 6–8 秒，站立→看向用户→开心眨眼→左右踏步摆鳍→小幅转身→回到站姿。
- 重点保留黑发、企鹅帽、发卡、锁链、白肚皮、黄脚和圆润体型；手脚/头发有独立运动，不裁切、不滑步、不换脸。
- 预制视频可包含编排好的表情变化；任意实时语音驱动面部，需要额外面部分层/绑定，不能把播放预制片段说成实时全身生成。
- 尚未生成咕嘎复杂舞蹈素材。
