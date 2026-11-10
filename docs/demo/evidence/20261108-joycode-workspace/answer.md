# 工作区根目录一句话说明

- task_id: `T-20261108-060558-2346de`
- goal: 读工作区根目录、一句话说明项目
- acceptance: 按需求完成，并在回执 self_check 里写清结果与产物路径
- callback: `guga:desk`

---

## 一句话结论

**`d:\rengongzhineng` 是「咕嘎」这个 AI 参赛作品（第二届全国人工智能应用创新大赛 · 生产力/办公效率赛道）的开发工作区：咕嘎是一只常驻 Windows 桌面的 Q 版桌宠，内核是个会监工的 AI 管家（包工头）——你说一个目标，它拆成子任务派给豆包/Kimi/元宝/智谱等多个 AI 去干，全程盯进度、按验收标准收货、不合格当场打回，再把经验沉淀回知识库。**

## 依据（本次实读核对，逐条可回查）

| 证据位置 | 原文要点 |
|---|---|
| `咕嘎参赛方案书-v2.md:5` | 「你说目标，它指挥其他 AI 智能体干活，并全程替你监工——派单、盯进度、验收、催办、复盘，把"人管 AI"升级成"管家替你管 AI"」 |
| `咕嘎参赛方案书-v2.md:7-9` | 大赛＝第二届通用赛道「AI Agent 赋能千行百业」；申报锚点单一锁定生产力/办公效率；差异化＝唯一以监工为核心的生产力桌宠 |
| `guga-competition/README.md:1-8` | 现行产品口径：既是桌宠也是管家；「市面上的桌宠陪你聊天，咕嘎替你管着所有 AI」 |
| `guga-competition/README.md:24-26` | 「四个 AI 是四个工具，不是四个员工，缺的那个角色是包工头」＋内核「任务拆解 + 智能体派单 + 进度监工 + 验收打回 + 经验沉淀」闭环 |
| `guga-desktop/使用说明.txt:6-10` | 本机执行端＝咕嘎的「手和脚」，配对后真实拉起本机 AI 软件干活，产物回传走同一套监工验收（不合格真打回） |
| `guga-server/README-部署指南.md:1-4` | 线上体验版＝大赛提交材料里的智能体链接，评委免安装体验「AI 指挥 AI + 监工」完整闭环 |

> 口径差异（如实记录，未擅自改写）：方案书 v2（2026-11-03）写「Live2D 原创管家猫」，`guga-competition/README.md:5` 现行写「Q 版企鹅」；方案书 `:10` 登记的代码仓库仍是 `heimao-zhuochong`（黑猫前身目录）。形象已由猫迭代为企鹅，历史文档与目录名尚未同步。

## 根目录逐块角色（40+ 顶层目录归为七层）

1. **咕嘎主线三端 + 前身**：`guga-competition`（参赛主程序，PyQt5 桌宠本体 + 指挥/监工引擎，`GUGA-Desktop.spec` 打包）、`guga-desktop`（本机执行端 `GUGA-Agent.exe`）、`guga-server`（Node.js 线上体验版）、`guga-web`（当前空目录）、`heimao-zhuochong`（黑猫前身，含战棋/语音早期能力）
2. **知识库供应链**：`知识库-完整版-新`、`知识库-队友交付`、`KB-v2-验收`、`KB6KB7-验收`
3. **美术与动作素材**：`素材-动作视频`、`素材备份`、`mascot-candidates`（企鹅/灵狐/黑猫三稿）、`交队友-20261106`（形象与知识库整改要求）
4. **打包发布与归档**：`参赛内部归档`、`guga-competition/release-private`、`安装包`（第三方 AI 客户端，属被调度对象）、`pkgtest_0102`、`runtime`、`_guga_*backup_*` / `_kb8_v2_backup_*`（改动前快照）
5. **核验观测管线（临时，非交付物）**：`temp_sprite_check`（DPI/边缘/抠像）、`temp_videocheck`（帧与动画）、`temp_avatar_video`（形象合成）、`temp_rekey`（动作重抠帧）、`temp_index_verify`、`temp_proactive_check`、`temp_control_check`、`temp_delivery_check`、`.screenshots`
6. **任务总线与协作配置**：`.guga`（`inbox` 派单 / `outbox` 回执 / `answers` 产物 / `questions` / `mcp-connections`，即本次通信协议本体）、`.joycode`（技能含 `guga-worker`、规则、记忆、MCP）、`.workbuddy`、`.ssh`
7. **根级决策文档**：`咕嘎参赛方案书-v1/v2.md`、`JOYCODE-GUGA.md`、`团队分工总表.md`、`知识库制作要求-完整整合版-v2.0.md`、`验收-知识库完整版-v2.md`、`本地工具与路由说明.md`、`素材接入指南.md`、`夜间进度.md` / `夜间检查-*.md`、`启动参赛版.cmd`、`大赛作品提交说明-官方.pdf`

**旁支无关项**：`python-xuexiji`（PyMaster，3D 像素风 Python 编程学习平台，独立作品）、`craft-anything` / `craft-anything-app` / `craft-anything-src`（第三方 Rust 桌面应用 ArtCraft，仅作参考）。

## 结论

根目录并非杂乱，而是「一个参赛产品 + 知识库/素材供应链 + 打包归档 + 核验管线 + 任务总线」的分层结构，全部服务于同一目标：把咕嘎做成能真正替你指挥并监工其他 AI 的桌面管家。唯一需要留意的是历史命名与形象口径（猫 → 企鹅、`heimao-zhuochong` 旧仓库名）尚未与 v2 方案对齐。