# 交付包三家真机回归 · 2026-11-08 07:16 最终版

包：`GUGA-Desktop-20261108-0716-最终版.zip`
SHA256：`C0A023F74F9CD2744929FC5D364A9523414D47B227DCB838EF4BEA0DC2EE014C`（本机复算一致，见 package-sha256.txt）

运行方式：解压后直接启动 `GUGA-Desktop.exe`，**未设 `GUGA_WORKSPACE`、未设 `GUGA_HOME` 或任何其他环境变量**。
唯一前置：首启向导要求模型配置，按演示机既定配置放入 `%LOCALAPPDATA%\GUGA\ai_config.json`（真实 Key 不随包）。

## 三条真机结果

| 目标 | 耗时 | 正文字数 | 来源字段 | 产物路径 | 失败码 |
|---|---|---|---|---|---|
| WorkBuddy | 56s（07:25:37 → 07:26:33） | 160 | 界面自动化，非接口调用 | `%LOCALAPPDATA%\GUGA\deliverables\guga-WorkBuddy-20261108-072633.txt` | 无 |
| JoyCode | 157s（07:27:25 → 07:30:02 回执；产物 07:29:22） | 1142（回执正文） | `/guga-run` 文件总线回执，status=done，非接口 | `D:\rengongzhineng\.guga\answers\T-20261108-072725-6b699c.md`（62 行） | 无 |
| 豆包 | 40s（07:31:59 → 07:32:39） | 135 | 界面自动化，非接口调用（自动拉起豆包桌面端） | `%LOCALAPPDATA%\GUGA\deliverables\guga-豆包-20261108-073239.txt` | 无 |

## 幂等拦截（同一目标连派两次）

JoyCode 目标：`用 JoyCode 读工作区根目录、用一句话说明这个项目`

```
07:27:25 create  T-20261108-072725-6b699c  workspace=D:\rengongzhineng
07:27:39 duplicate_blocked stage=ui_busy  task_id=T-20261108-072725-6b699c
07:30:02 回执 status=done
07:30:03 consume → inbox-archive/T-20261108-072725-6b699c.json
```

第二次派单未写新任务文件（inbox 4→4，只有首单），界面气泡原文：“同一目标已经在执行（T-20261108-072725-6b699c），这次不重复派单。”
完成后 inbox 回到 3（仅保留 060558 / 063703 / 065513 三条历史成功单），inbox-archive 44。
工程路径来源：JoyCode 配置自动识别（`storage.json` → 最近窗口工程），未使用环境变量。

## 文件说明

- `workbuddy-deliverable.txt` / `workbuddy-dialog.png`：正文与来源标注截图
- `joycode-receipt.json`：done 回执（artifact_paths 指向 .guga/answers）
- `joycode-artifact.md`：JoyCode 产物原文
- `joycode-deliverable.txt`：咕嘎转存的回执正文
- `joycode-inbox-consumed.json`：回执到达后被移出 inbox 的任务（防重复触发）
- `joycode-bus.log`：本次 create / duplicate_blocked / consume 日志
- `joycode-duplicate-blocked.png`：第二次派单被拦下的界面气泡
- `doubao-deliverable.txt` / `doubao-dialog.png`：正文与来源标注截图
- `package-sha256.txt`：交付包 SHA256
- `SHA256SUMS.txt`：本目录全部文件校验清单

## 备注

首次豆包派单（07:30:20）时，上一条 JoyCode 产物弹框尚未关闭，模态弹框拦截了宠物输入，任务未送出；关闭弹框后 07:31:59 重派成功。属操作顺序问题，非适配器失败。
