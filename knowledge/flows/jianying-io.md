# 剪映专业版 · 输入输出能力档案

> ⚠⚠ **本机未安装剪映，本文档全部数值来自官网 / 官方帮助 / GitHub 资料，均未经真机实测（2026-11-05，2026-11-06 复核仍未安装）；接入前需先安装实测。**

> ### 档案定位（v2.0 口径）
> 剪映在本知识库里是**备用成员**：只在"需要出成片视频"时才用到，不参与日常对话接力的软件选择。**因本机未装机，本档案全体结论一律按【未验证】对待**，执行器只能把它当"待验证的线索清单"，不能当能力承诺。要真正接剪映，必须先安装并做一次真机小步验证（导出面板、草稿目录、素材导入）。
> **多环境说明**：本档案没有多环境实测矩阵——**一次真机都没跑过**，不存在"已适配某分辨率"的说法。装机首测时须同时登记"分辨率 + 缩放 + 显示器数"，并按 `generic-io.md` 第 0 条分辨率无关探测法逐项核对。

- **档案ID**：jianying-io
- **软件**：剪映专业版（JianyingPro，Windows 桌面客户端；与 CapCut 国际版同二进制但国内版草稿有加密差异，见下文专章）
- **实测版本**：【未验证】（本机未安装；官网当前页标注推荐 macOS v11.5.1、Windows 端版本号见官网下载页，本机无从核对）
- **实测时间**：2026-11-05（Asia/Shanghai）
- **实测环境**：Windows 11，屏幕 2560×1600，**未安装剪映、未登录**（2026-11-05 四层探测：进程 / Program Files / LOCALAPPDATA / 开始菜单均无剪映或 CapCut 痕迹）
- **覆盖能力**：视频剪辑成片、图片/视频/音频素材导入、字幕导入与导出、草稿工程（draft）读写、封面/帧导出；无对话/写作/AI 聊天能力

---

## 能产出什么（Output）

| 产物类型 | 形态 | 说明/限制 |
|---|---|---|
| 长文本 | 无此能力 | 【未验证】剪映是剪辑工具，输入区无对话/文本生成入口；不存在"对话内长文本"这一产物。判断依据：官网 jianying.com 介绍的全部能力为剪辑/AI 剪辑特效，无聊天写作模块。 |
| 文件类产物 | 成片视频可导出为 mp4（见下行"视频"行）；另可导出**封面/静帧图片**；工程本身是"草稿文件夹"而非单文件（见专章） | 【官方帮助，未在本机验证】导出入口为界面**右上角「导出」按钮**（CapCut 官方帮助原文：Step 2: Click "Export" (top-right)）。导出面板内可设分辨率、帧率、码率档位。封面/静帧导出入口位置与支持格式：【未验证】（官方帮助页未展开，需真机在导出面板/播放器截图核对）。 |
| 图片 | 可导出单帧/封面（png/jpg 档位以真机为准） | 【未验证】分辨率档位、张数上限、是否只能导当前帧——资料未给出。第三方百科称剪映"图片导入支持 JPEG、PNG"，但导出图片档位未查到官方原文。 |
| 视频 | 成片视频，mp4 容器下载到本地目录 | 【官方帮助，未在本机验证】官方帮助原文：导出面板 Resolution 可选 2K（2560×1440）或 4K（3840×2160）；Frame Rate **up to 60fps, depending on source**；Bitrate 可调（higher = better quality, larger file）。编码档位（H.264/HEVC 可选与否、码率低/推荐/高各档具体 Mbps）：【未验证】（官方帮助只给档位名不给数值；网传"6/16/25Mbps"来自 2021 年抖音视频作者口述，非官方，不采信为数值）。单文件大小上限、导出是否排队、会员档位限制：【未验证】（官网与官方帮助均未给出）。 |

**追加产出（SPEC 三行之外的剪映特有产物）：**

| 产物类型 | 形态 | 说明/限制 |
|---|---|---|
| 草稿工程（draft） | 一个文件夹，内含 `draft_content.json` + `draft_meta_info.json` + 素材/缓存，由剪映自动保存在草稿目录 | 【GitHub，未在本机验证】剪映工程不是单文件导出，而是实时落盘到草稿目录；程序可"生成一个草稿文件夹 → 扔进草稿目录 → 剪映里打开"。详见下文《草稿工程机制专章》。 |
| 字幕文件 | 可把识别/编辑好的字幕导出为 srt（能力存在性见 Input 行与专章） | 【未验证】（官方帮助只确认"可导入 srt/txt"，未在本机验证"能否反向导出 srt"；需真机在「文本/字幕」面板核对导出按钮）。 |
| 音频 | 可单独导出音轨 | 【未验证】（官网提及"音频剪辑"能力，但"能否把工程单独导出为 mp3/wav"未查到官方原文，需真机核对导出面板）。 |

## 能接收什么输入（Input）

| 输入方式 | 支持格式 | 大小/条数限制 | 入口（对照软件档案按钮位置） |
|---|---|---|---|
| 粘贴文本 | 纯文本（用于字幕/文本片段，非对话） | 【未验证】（单条字幕字数上限、单次粘贴条数——资料未给出） | 「文本」面板 → 新建文本框；非"聊天输入框" |
| 上传文件：视频素材 | 【官方帮助（CapCut PC 面向页），未在本机验证】Video: MP4, MOV, AVI, WMV, MKV（来源 capcut.com/create/video-collage）。另第三方百科称国内版另支持 m4v/flv/rmvb、编码 H.264/H.265/ProRes——**非官方原文，仅作线索，标【未验证】** | 【未验证】单个文件 MB 上限、单项目素材条数上限、单项目总时长上限——官网与官方帮助均未给出 | 「导入」按钮 / 直接拖入素材面板（CapCut 官方面向页原文：click "Import" to upload your video file, or drag & drop into the import window） |
| 上传文件：图片素材 | 【官方帮助（CapCut PC 面向页），未在本机验证】Image: JPG, PNG, GIF | 【未验证】单文件 MB 上限、张数上限——资料未给出 | 同上「导入」/拖拽 |
| 上传文件：音频素材 | 【官方帮助（CapCut PC 面向页），未在本机验证】Audio: MP3, WAV, M4A, AAC, FLAC | 【未验证】单文件 MB 上限——资料未给出 | 同上「导入」/拖拽 |
| 上传文件：字幕 | 【官方帮助，未在本机验证】外部字幕主要支持 **SRT (.srt) 或 TXT (.txt)**；该导入能力**仅 CapCut Desktop 与 Web 支持，移动端 2026 年起不支持直接导入字幕文件**（官方帮助原文："the subtitle import feature is only available on CapCut Desktop and CapCut Web"） | 【未验证】单文件大小、条数——资料未给出 | 桌面端路径：打开项目 →「文本 / Captions」→「本地字幕 / Add Captions」→「导入」选择 .srt/.txt（抖音教程与官方帮助互证入口在"文本→本地字幕→导入"）。导入后字幕带时间轴，需拖到轨道起始位与画面对齐（教程口径：时间线须放在素材起始位置再添加，否则字幕错位）。 |
| @引用 / 引用历史会话 | 无此能力（剪映无会话概念，不存在 @引用） | — | — |
| **吃结构化草稿（接力关键项）** | 剪映能直接"打开"的结构化工程 = 草稿目录里的 `draft_content.json` + `draft_meta_info.json`；**不是开放标准格式**（无公开 schema/无官方文档） | 【GitHub，未在本机验证】见专章。能否由程序生成/改写后被剪映正常打开：5.9 明文版可；6.0+ 国内版 `draft_content.json` 加密，生成路径需走社区库方案 | 无需界面入口——把生成好的草稿文件夹整个放进草稿目录，重启剪映即在首页草稿列表出现 |

## 接力特性

- **产物"停在对话里"还是"能落成文件"**：剪映一切产物都**落成文件**（mp4 / 草稿文件夹 / 可能的 srt / 静帧），不存在"停在对话框里"的中间态。这意味着下游接力要么接"成片 mp4"，要么接"草稿文件夹"，二选一。
- **两条接力路线的差别与适用条件**：
  1. **人工在剪映里剪**：上游产出脚本/分镜/素材文件 → 人在剪映里导入素材、手动拖轨。可靠、零版本风险，但每单都要人盯，不适合批量。
  2. **程序生成草稿 → 人工微调**：上游用第三方库直接在草稿目录生成 `draft_content.json` 骨架（素材已就位、时间轴已排好、srt 已挂）→ 打开剪映只做精修/导出。省掉重复拖轨，但**强绑剪映版本**（见专章的加密风险），属于"推测可达"路径，未在本机验证。
- **处理上传文件的能力强弱**：剪映本身是"吃素材做剪辑"，不做文档理解/长文本解析；它对素材的兼容性 = 上述格式清单，格式不在清单内会出现"导入黑屏/无法识别"（官方帮助原文：file format not supported → convert before importing）。
- **已知的坑**（现象 → 规避动作）：
  - **草稿版本不兼容** → 新版剪映（6.0+）保存的草稿，旧版打不开；第三方库生成的草稿对剪映小版本敏感。规避：固定剪映版本再批量跑；每次换版本先拿一个小样草稿试开。
  - **素材绝对路径绑定** → 草稿 json 里素材是绝对路径记录，换机/换盘符后剪映里素材全红失效。规避：生成草稿时把素材放在固定相对位置，换机后先在剪映内"重新链接素材"，或把素材一起拷到相同绝对路径。
  - **草稿加密**（国内版 6.0+）→ 直接读/改写别人已保存好的草稿会读到密文而非 JSON。规避：新生成草稿走"全新生成"而非"加载别人草稿做模板"；确需模板模式要接社区 fallback_loader。
  - **未缓存的字体/特效/转场** → 剪映打开外部生成的草稿时会自动联网补下，可能超时显示"xx加载失败"（pyJianYingDraft README 明示）。规避：先用剪映打开一次让它缓存资源，二次打开再交付。
  - **导出排队 / 会员限制** → 【未验证】（官网与帮助未给出导出队列、4K/高帧率是否绑会员的明文；网传会员墙口径不采信，需真机在导出面板看是否弹付费提示）。
  - **自动批量导出在新版失效** → 剪映 7+ 隐藏了导出控件，基于 UI 自动化（uiautomation）的批量导出脚本不再可用（pyJianYingDraft README 明示：10.8 下控制剪映导出 ❌）。规避：批量成片这一步要么降级到剪映 6.x，要么改成"只生成草稿、人工点导出"。

---

## 草稿工程机制专章（KB7 接力的落点）

> 本章是本档案的核心价值。**以下均为 GitHub / PyPI / 社区文档的二手结论，本机未装剪映，全部属"推测可达"的自动接力路径，未在本机验证。**

### 1. Windows 下草稿目录长什么样

【GitHub（capcut-cli 文档），未在本机验证】Windows 草稿根目录形态：

```
%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft\
└── <每个项目一个文件夹，文件夹名常是日期或自命名，如 "9月5日" / "export_capcut_短剧名">
    ├── draft_content.json     ← 整个时间轴（画布配置 materials/tracks）都在这
    ├── draft_meta_info.json    ← 打开草稿所需的元信息；其素材列表出现在左侧素材库
    └── (素材、代理缓存、预览图等附属文件)
```

- 两个 json 的分工（【PyPI / GitHub 社区文档】）：`draft_meta_info.json` 里记录的素材会显示在**左侧素材库面板**；`draft_content.json` 里记录的素材与 segments 会显示在**下方时间线**。
- 占位符约定（【GitHub/掘金社区】）：json 里出现 `##_draftpath_placeholder_xxx_##` 字样代表"草稿文件夹自身位置"，程序改写时需做路径替换。
- Mac 端对应文件叫 `draft_info.json`（不是 draft_content.json），路径在 `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft`；**本档案只承诺 Windows 路径**。

### 2. 版本兼容风险（最重要的一条）

- 【GitHub（capcut-cli 加密文档 + pyJianYingDraft README）】**剪映 5.9.x 是最后一个广泛使用的明文 `draft_content.json` 版本**；**剪映 6.0 起国内版把 `draft_content.json` 改成 AES 加密二进制**，不再是可读 JSON。
- 加密算法随版本变动（社区提到 issue #142/#169/#174 在跟进），意味着"解密/读旧草稿"这条路本身不稳定。
- **CapCut 国际版不加密，只有国内剪映加密**（社区原文："CapCut International is not encrypted — only JianYing"）。
- 推论：**"程序从零新建草稿文件夹"这条路在新版仍可行**（生成的是待剪映自己补全/加密的新草稿，不需要读旧密文）；**"加载一个已存在的草稿当模板再改素材"这条路在新版需要额外的 fallback_loader/解密器**。

### 3. 第三方库路线（GitHub）

**主选：`GuanYixuan/pyJianYingDraft`**（PyPI 包名 `pyjianyingdraft`）
- 仓库：https://github.com/GuanYixuan/pyJianYingDraft ；Gitee 镜像 `luojoe/pyJianYingDraft`。
- 它能做什么（【PyPI README 原文】）：用 Python 代码**从零生成剪映草稿**——本地视频/图片素材+时间控制、音频淡入淡出/音量、文本与样式、字幕（**支持导入 .srt**）、贴纸/关键帧/转场/特效/滤镜/蒙版/色度抠图；另支持"模板模式"（加载已有草稿→替换素材/替换文字/整轨导入）和"批量自动导出"。
- 依赖的剪映版本（README 功能表）：
  - **草稿生成**：剪映 5.9 ✅；新版（README 标到 **10.8**）✅。
  - **模板模式（加载别人草稿）**：5.9 ✅；10.8 🟡 **需 `fallback_loader`**（因新版 draft_content.json 加密）。
  - **批量自动导出（UI 自动化点导出）**：仅剪映 6.x（≤6.8）✅；**剪映 7+ / 10.8 ❌**（控件被隐藏）。
- 维护活跃度（【PyPI 发布历史】）：0.1.0 发布于 2025-03-22，持续迭代到 **0.3.1（2026-10-14）**，近一年发版密集。GitHub 实时 star 数：【未验证】（本机直连 github.com 被网络策略拦截，未取到 star/fork 数值；可由"PyPI 持续发版 + 多个 MCP 项目以它为底座"侧面判断活跃）。
- 平台：草稿生成/模板模式跨 Windows/macOS/Linux；**自动批量导出仅 Windows**，且导出的草稿最终仍需在 Windows 剪映里完成。推荐 Python 3.8 / 3.11。

**周边生态（佐证"草稿接力"是被验证过的通路，不是空想）**：
- `renezander030/capcut-cli`：命令行读写剪映草稿，**只检测加密、不做解密**；官方建议固定剪映 5.9。https://github.com/renezander030/capcut-cli
- `Xanthus-Sanslab/jianying-ai-mcp`：MCP server，把"剪辑计划 manifest"编译成可编辑草稿，验证基线剪映专业版 **10.0.5.13816**；加密草稿通过调用本机剪映 `videoeditor.dll` 的开源解密器 `jy-draftc` 读取，且明确"剪映版本与基线不同时必须先生成小样抽检"。
- 火山引擎「剧创」官方文档：分镜成片后可"导出剪映草稿"为 zip，解压后整个文件夹放入剪映草稿目录，重开剪映即见该草稿——**这是字节自家产品都在用的"产草稿→喂剪映"接力姿势**，可作为路线可信度的官方旁证。https://www.volcengine.com/docs/87744/2261814

### 4. 一句话结论

"上游程序 → 剪映草稿文件夹 → 人工打开微调 → 点右上角导出"这条路**社区已跑通、且字节自家剧创也这么做**，但它是**版本敏感、路径敏感、素材绝对路径敏感**的半自动路，不是稳定 API；在本机装好剪映前，任何"自动出成片"的承诺都只能算推测。

---

## 本机安装后的首轮实测清单（按优先级）

装好剪映专业版后，按此顺序测，前 3 项不通就先停：

1. **确认版本号 + 草稿明文/加密形态**：打开剪映→关于里记版本号；在草稿目录手动建一个空草稿，看 `draft_content.json` 是明文 JSON 还是密文。决定后续走"新建草稿"还是"需要 fallback_loader"。
2. **草稿目录实路径核对**：确认 `%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft` 是否真实存在、每个项目文件夹里到底有哪几个 json（Windows 是 draft_content.json 还是别的名字）。
3. **最小草稿生成冒烟测试**：用 pyJianYingDraft 0.3.1 生成一个只含 1 段 mp4 + 1 条 srt 的草稿，扔进草稿目录，重开剪映看能不能正常打开、素材红不红、字幕对不对位。
4. **导入格式实探**：在「导入」按钮的系统文件选择框里，把"文件类型"下拉的过滤串原文抄下来（这是 io 表"支持格式"列要回填的实测值）；各喂一个 mp4/mov/mkv/mp3/wav/png/jpg/srt 试吃。
5. **导出面板实探**：点右上角「导出」，把分辨率档位、帧率档位、码率档位的**实际文案与可选项**抄下来；确认编码是否可选 H.264/HEVC、导出到哪、有没有会员/付费弹窗。
6. **srt 导入对齐测试**：按"文本→本地字幕→导入"挂一个 srt，验证时间轴对齐行为（是否需要把时间线游标放素材起始位）。
7. **素材路径迁移测试**：把草稿里素材改个目录名，重开剪映看报什么错、有没有"重新链接素材"入口——量化"换机失效"这个坑。
8. **封面/静帧导出与音轨单独导出**是否存在、入口在哪。

---

## 数值与来源登记表

> 来源类型仅限：官方文档 / 官方帮助 / GitHub / 推测。本机未装剪映，**验证状态一栏除"官方页面原文"外一律为"未在本机验证"**。

| 字段 | 数值/结论 | 来源类型 | 验证状态 | 证据（URL / 入口文案 / 报错原文） |
|---|---|---|---|---|
| 官网域名可信性 | 国内剪映官网 jianying.com，公司主体深圳脸萌/字节，客服 957123，与即梦/抖音/西瓜互链 | 官方文档 | 未在本机验证 | https://www.jianying.com/ |
| 导出按钮位置 | 界面右上角「Export / 导出」 | 官方帮助 | 未在本机验证 | https://www.capcut.com/help/export-videos-in-capcut |
| 导出分辨率档位 | 2K(2560×1440) / 4K(3840×2160) | 官方帮助 | 未在本机验证 | https://www.capcut.com/help/export-videos-in-capcut |
| 导出帧率上限 | up to 60fps, depending on source | 官方帮助 | 未在本机验证 | https://www.capcut.com/help/export-videos-in-capcut |
| 导出码率 | 有档位可调（higher=更好质量更大文件），具体 Mbps 数值未给出 | 官方帮助 | 未在本机验证 | https://www.capcut.com/help/export-videos-in-capcut |
| 导出编码（H.264/HEVC 可选） | 【未验证】（导出帮助页未列编码选项，资料未给出） | 推测 | 未在本机验证 | https://www.capcut.com/help/export-videos-in-capcut |
| 导出单文件 MB 上限 / 会员限制 | 【未验证】（官网与导出帮助均未给出，资料未给出） | 推测 | 未在本机验证 | https://www.jianying.com/ |
| PC 导入视频格式 | MP4 / MOV / AVI / WMV / MKV | 官方帮助 | 未在本机验证 | https://www.capcut.com/create/video-collage |
| PC 导入图片格式 | JPG / PNG / GIF | 官方帮助 | 未在本机验证 | https://www.capcut.com/create/video-collage |
| PC 导入音频格式 | MP3 / WAV / M4A / AAC / FLAC | 官方帮助 | 未在本机验证 | https://www.capcut.com/create/video-collage |
| 字幕导入格式 | SRT(.srt) / TXT(.txt)；仅 Desktop & Web，移动端不支持 | 官方帮助 | 未在本机验证 | https://www.capcut.com/fr-fr/help/how-to-import-subtitles |
| 字幕导入入口 | 文本/Captions → 本地字幕/Add Captions → 导入 | 官方帮助 | 未在本机验证 | https://www.capcut.com/create/ai-video-generator/import-srt-captions |
| 单项目素材条数 / 时长上限 | 【未验证】（官网与导入帮助均未给出，资料未给出） | 推测 | 未在本机验证 | https://www.capcut.com/help/can-not-local-assets-be-recognized-during-import |
| 草稿目录（Windows） | `%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft` | GitHub | 未在本机验证 | https://unpkg.com/capcut-cli@0.20.0/docs/quickstart.zh-CN.md |
| 草稿文件构成 | draft_content.json（时间轴）+ draft_meta_info.json（素材库元信息） | GitHub | 未在本机验证 | https://pypi.org/project/JianYingDraft.PY/ |
| 草稿加密分界 | 5.9 明文；6.0+ 国内版 AES 加密；CapCut 国际版不加密 | GitHub | 未在本机验证 | http://raw.githubusercontent.com/renezander030/capcut-cli/HEAD/docs/jianying-encryption.md |
| pyJianYingDraft 版本/适配 | 0.3.1（2026-10-14 发布）；草稿生成适配到剪映 10.8；模板模式需 fallback_loader；批量自动导出仅剪映 ≤6.x | GitHub | 未在本机验证 | https://pypi.org/project/pyjianyingdraft/ |
| pyJianYingDraft 仓库 | https://github.com/GuanYixuan/pyJianYingDraft | GitHub | 未在本机验证 | https://pypi.org/project/pyjianyingdraft/ |
| pyJianYingDraft star 数 | 【未验证】（GitHub 直连被网络策略拦截，未取到实时 star；PyPI 发布页见此） | 推测 | 未在本机验证 | https://pypi.org/project/pyjianyingdraft/ |
| 字节官方"产草稿喂剪映"旁证 | 剧创支持"导出剪映草稿" zip，解压放入草稿目录重开剪映即见 | 官方文档 | 未在本机验证 | https://www.volcengine.com/docs/87744/2261814 |
| 素材绝对路径绑定换机失效 | 草稿 json 记录素材绝对路径，换机素材红/需重链 | GitHub | 未在本机验证 | https://juejin.cn/post/7341288829684318260 |
| 未缓存字体/特效需二次打开 | 打开外部草稿会联网补下，可能超时"xx加载失败" | GitHub | 未在本机验证 | https://pypi.org/project/pyjianyingdraft/ |
| 封面/静帧导出档位 | 【未验证】（导出帮助页未展开封面选项，资料未给出） | 推测 | 未在本机验证 | https://www.capcut.com/help/export-videos-in-capcut |
| 音轨单独导出 | 【未验证】（官网仅提音频剪辑能力，未提单独导出音轨，资料未给出） | 推测 | 未在本机验证 | https://www.jianying.com/ |
| 反向导出 srt | 【未验证】（官方字幕帮助仅确认可导入，未确认可导出，资料未给出） | 推测 | 未在本机验证 | https://www.capcut.com/fr-fr/help/how-to-import-subtitles |

## 自检清单

- [x] 三张表列头与本目录其余 `{slug}-io.md` 完全一致，未增删列（Output 三列 / Input 四列 / 登记表五列）
- [x] Output 四行齐全（长文本=无此能力并写了依据；文件类产物；图片；视频）；追加了草稿工程/字幕/音频三行
- [x] 每个数值都有【实测】/【未验证】/【官方】标记：本机未装，全部数值为【未验证】或【官方帮助，未在本机验证】，无裸数字
- [x] 上传格式来自官方页面原文（capcut.com/create/video-collage 的格式清单）；国内版系统选择框过滤串原文留待实测回填
- [x] 文件头已写"本机未安装剪映，全部数值未经真机实测"醒目声明
- [x] 文末《数值与来源登记表》每条带 URL，来源类型仅用 官方文档/官方帮助/GitHub/推测
- [x] 专章覆盖：草稿目录结构、两 json 分工、5.9/6.0+ 加密分界、pyJianYingDraft 仓库与版本适配、周边 MCP/CLI
- [x] 结尾写了 8 项首轮实测清单（按优先级）
- [x] 未写任何"用户说剪视频就走剪映"式关键词映射，只写能力与差距
- 未验证项清单：见登记表中"验证状态=未在本机验证"全部行，重点 = 导出编码/码率具体值、单文件 MB 上限、素材条数/时长上限、封面与音轨导出、srt 反向导出、star 数
