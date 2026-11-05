# WPS Office · 按钮功能地图（KB8 · wps）

- **档案ID**：wps-buttons
- **优先级**：P2（v2.1 要求：最后做）
- **日期**：2026-11-06（第三～五轮补测完成，当前 **实测 18 颗**；其中 2 颗【待核对】）
- **取证环境**：Windows 11，单屏 2560×1600，缩放 **100%**（AppliedDPI=96）；WPS `12.2.0.23196`，**界面语言英文**
- **证据图**：`imgs/wps-*.png` 共 24 张（见文末索引）

---

## 适用条件

- **适用版本**：WPS Office **12.2.0.23196**，**界面语言英文**（锚文本按英文原文登记）
- **登录态**：本档案实测**未要求登录**（首启 `Agree & Continue` 后即可用首页与编辑器）；登录后的行为（如 `Improve Writing` 的实际效果）**未实测**
- **缩放与分辨率**：Windows 11 单屏 **2560×1600**、缩放 **100%**（AppliedDPI=96）。150% / 其他分辨率**未测**
- **失效条件**：`Export to Picture` 会弹独立窗口（1317×859），窗口尺寸与屏幕缩放相关，换缩放后按旧坐标点会偏；首页 `+ Blank` 按钮颜色随竖排导航切换而变（`Docs` 蓝 / `Sheets` 橙 / `PDF` 绿），按颜色认按钮在版本更新后可能失效（**推断**）
- **风险**：`Print` / `Save` / `Save As` 会写盘或占用打印机；`Share ⌄` 实际落到 `Save As` 保存框（W12）；`Export to PDF` 与 `Export to Picture` 的最终导出按钮**本库未点**，需用户在场

## 零、本轮结论摘要（先看这七条）

- **本篇适用**：用户只想知道 WPS 这一轮测出来哪几条结论

1. **WPS 首启弹 `WPS Privacy Policy`**，只有 `Exit WPS` / `Agree & Continue` 两个出口；点同意才进首页。**首启界面语言是英文**，本档案所有锚文本按屏幕原文（英文）抄。
2. **WPS 是"单窗口多标签"**：窗口标题随当前标签变——`WPS Office`（首页）→ `New - WPS Office`（新建页）→ `Document1 - WPS Office`（新建文档）→ `WPS Slides Quick Start Guide.pptx - WPS Office`（打开演示）。**用标题定位窗口会频繁失效**。
3. **`+ New` 不是"新建空白文档"**，是**新建页/模板中心**；真正建空白要再点一张 `Blank` 卡。断网时模板区只剩 `Blank`，并显示红字 `Network error. Please check the network connection and try again.`
4. **打开任何文档都会再弹一次「设为默认办公软件」框**（标题 `WPS Office`，726×377）。那个 `Confirm` **会改系统文件关联**，属危险按钮，本档案只记录不点。
5. **`WPS AI` 标签在未登录态下是一座空工具栏**（只有 `AI Spell Check` / `Improve Writing` / `Settings` 三格）；点 `Improve Writing` **不弹登录、不弹付费、不给结果，完全没有反馈**。别把它当作"文档内 AI 助手可用"。
6. **`Export to PDF` 面板是"主窗内嵌浮层"，不是独立窗口**——所以按"有没有新窗口"判断成败，会把它误判成"没点中/无反应"（这是本档案最大取证陷阱，E-035）。而它的邻居 `Export to Picture` **确实**弹独立面板，两者正好相反。
7. **未登录/未保存态点右上 `Share ⌄`，弹出来的是 `Save As` 保存框**（默认文件名直接取正文首句），不是分享面板。按 `Esc` 可关（E-036 / E-037）。

---

## 一、安装事实（已核实）

- **本篇适用**：用户问 WPS 装的是哪个版本、安装路径在哪

- 目录：`C:\Users\<user>\AppData\Local\Kingsoft\WPS Office`
- 版本目录两个：`12.1.0.29162`、`12.2.0.23196`（本轮启动用后者）
- `12.2.0.23196\office6\` 下：`wps.exe` 1,111,544 B（文字）、`et.exe` 1,081,336 B（表格）、`wpp.exe` 1,077,876 B（演示）、`ksolaunch.exe` 685,048 B
- 根目录另有 `ksolaunch.exe` 797,056 B、`wpsupdate.exe` 7,385,984 B
- 启动方式实测：直接运行 `12.2.0.23196\office6\wps.exe` → 打开首页（不是先弹启动器）

---

## 二、启动首屏（W-00，实测）

- **本篇适用**：用户问 WPS 首启的 Agree & Continue 要不要点、点了之后什么样

**按钮原文**：`Agree & Continue`（弹窗底部右侧的蓝色实心按钮）／`Exit WPS`（同排左侧白底描边按钮）
**位置参照**：首启 `WPS Privacy Policy` 弹窗（白色，约 726×377 居中）底部一行按钮，`Agree & Continue` 在**右**，`Exit WPS` 在**左**；弹窗右上无 `×`
**点击后果**：点 `Agree & Continue` → 弹窗消失，露出首页 `Home` 标签（左栏 `Home`/`New`/`WPS AI`/`Docs`/`Slides`/`Sheets`/`PDF`）。点 `Exit WPS` → 见到的是"退出程序"，不进入首页。
#### W-00 弹窗逐字锚文本与判据

**结果锚文本**：弹窗正文首行 `Your privacy is important, and to protect your privacy we developed a Privacy Policy, which explains how we use any personal data we collect about you. It describes:`；条目 `What information we collect about you;` / `How we use your information;` / `Who we share your information with;` / `Collection and use of Non - Personal Data;` / `Your rights regarding our use of your information;` / `How long we keep your information;` / `How to contact us;` / `Advertisement information.`；底部一行 `You can change the agreement in WPS Office Configuration Tools.`
**如何确认点对**：点完**弹窗整块消失且首页左栏出现 `Drive` 分组**（`WPS Drive`/`Google Drive`/`Dropbox`）。若点完弹窗还在 → 落点没进弹窗（见第七节 E-033 的遮挡坑）。
**易混按钮**：`Exit WPS`（左）与 `Agree & Continue`（右）**都是纯按钮、无图标**，只靠左右位置区分；误点 `Exit WPS` 等于退出，不会进首页。
**误点后果与恢复**：误点 `Exit WPS` → 进程退出，重新运行 `wps.exe` 会**再弹同一个协议框**（不会记住），重来即可。
**对话可用性**：与对话无关（本机应用授权，不是聊天入口）。

---

## 三、首页层（W-01 ~ W-04，实测）

- **本篇适用**：用户问 WPS 首页 + New、Blank 卡、最近文件行点下去会怎样

### W-01 顶部 `+ New`

- **按钮原文**：`New`（前缀是加号图标 `+ New`）
- **图标特征**：细线加号，位于顶部标签条 `Home` 标签**右侧紧邻**位置
- **位置参照**：顶部标签条（`Home` 标签 → `+ New` → 后续文档标签）；右上角另有 `Upgrade Now`，别混
- **点击后果**：**不新建文档**，切换到一个新标签页「新建页」，**窗口标题随之变成 `New - WPS Office`**
- **结果锚文本**：页标题 `Create New`；搜索框占位 `Search for Docs templates`；左栏 `All` / `Docs`(选中高亮) / `Slides` / `Sheets` / `PDF`，左下 `My Templates`；主区一张卡，卡内是加号，卡下文字 `Blank`；网络不可用时右上红字 `Network error. Please check the network connection and try again.`
- **如何确认点对**：**看窗口标题是否变成 `New - WPS Office`**，且页面左上出现 `Create New`。仍在 `Recent` 列表 = 没点中。
- **易混按钮**：左栏那颗 `New`（绿色加号，在 `Home`/`New`/`WPS AI` 竖排里）——**是另一个入口，不是同一颗**（本轮未单独点，见待补 W-11）
- **误点后果与恢复**：只是多了个标签，点标签上的 `×` 或点 `Home` 标签即可回首页，不产生文件
- **对话可用性**：与对话无关

### W-02 `Blank` 卡

- **按钮原文**：`Blank`
- **图标特征**：一张白纸缩略卡，中间一个蓝色加号
- **位置参照**：`Create New` 页主区**最左第一张卡**（模板拉不到时是唯一一张）
- **点击后果**：**新建一份空白文字文档并进入编辑器**；窗口标题变成 `Document1 - WPS Office`；**同时弹出一个"设为默认办公软件"确认框**（独立窗口，标题 `WPS Office`，726×377，位于屏幕中部）
- **结果锚文本**：新标签 `Document1`；编辑器功能区首行 `Home` `Insert` `Page Layout` `References` `Review` `View` `Tools` `WPS AI`；状态栏 `Page: 1/1` `Words: 0` `AI Spell Check`；默认字体框显示 `等线`、字号 `10`
- **如何确认点对**：**标题变 `Document1 - WPS Office` 且出现 `Page: 1/1`**。若标题仍是 `New - WPS Office` = 没建成功。
- **易混按钮**：`Slides`/`Sheets`/`PDF` 页签下的 `Blank` 是**同名的另一颗**，点它建的是演示/表格/PDF
- **误点后果与恢复**：只建了一份未命名空白文档，不落盘；关标签时若问"是否保存"选不保存即可
- **对话可用性**：与对话无关

### W-03 首页「最近」列表里的文件条目

- **按钮原文**：文件名本身（实测那行是 `WPS Slides Quick Start Guide.pptx`，行尾带灰底小字 `Local`）
- **图标特征**：行首一个彩色方标（按类型：`P` 橙=演示、`W` 蓝=文字、`S` 绿=表格、`P` 红=PDF）
- **位置参照**：首页主区 `Recent` 分组下 `Within 7 days` 列表；四列分别是文件名 / `Location` / `Last Modified` / `Size`
- **点击后果**：**真的会打开该文件**——点了 pptx 那行后进入演示编辑器，窗口标题变成 `WPS Slides Quick Start Guide.pptx - WPS Office`；**并再次弹出「设为默认办公软件」确认框**
- **结果锚文本**：编辑器功能区 `Home` `Insert` `Design` `Transitions` `Animations` `Slide Show` `Review` `View` `Tools` `WPS AI`；左栏 `Outline` / `Slides`；左下 `Slide 1 / 13` `Office Theme` `Font Missing`；页面正文首屏 `Welcome to WPS Office - Presentation`
- **如何确认点对**：**标题变成"文件名 - WPS Office"**。只高亮不打开 = 点到了行但没落在文件名上。
- **易混按钮**：同一行右侧的 `Size` 数字区不是按钮；`Recent` 标题右侧的环形箭头是**刷新**，不是打开
- **误点后果与恢复**：打开的是 WPS 自带示例文件，只读风险低；若打开的是用户自己的文件，**只做查看、不要按 Ctrl+S**（避免覆盖）；关标签即退
- **对话可用性**：与对话无关

### W-04 首页右上 `Sign In` / `Upgrade Now`（未点，只记录）

- **按钮原文**：`Sign In`（人像圆点 + 文字）／`Upgrade Now`（带闪电的蓝紫渐变按钮）
- **位置参照**：首页顶部最右侧一排，`Sign In` 在左、`Upgrade Now` 在右
- **点击后果**：**未点**（账号/付费，不代点）
- **说明**：编辑器里同位置也有 `Sign in` 与 `Upgrade Now`，形状一致

---

## 四、文字编辑器层（W-05 ~ W-08，实测）

- **本篇适用**：用户问 WPS 编辑器里 File 菜单、WPS AI 页签有哪些项

### W-05 功能区标签 `WPS AI`

- **按钮原文**：`WPS AI`（前面带一个紫色四角星）
- **图标特征**：紫色星芒 + 文字，标签文字**紫色**（其它标签是深灰）
- **位置参照**：编辑器功能区标签条**最右一个**（`Home` `Insert` `Page Layout` `References` `Review` `View` `Tools` **`WPS AI`**），其右是放大镜搜索图标
- **点击后果**：**不移页、不开侧栏**，把整条功能区**清空成三格**：`AI Spell Check` / `Improve Writing` / `Settings`。未登录态下**没有任何可用的 AI 生成入口**
- **结果锚文本**：三格文字分别是 `AI Spell Check`（图标是 `AB✓`）、`Improve Writing`（图标是纸张+笔）、`Settings`（齿轮）；下方横幅 `Upgrade to unlock unlimited PDF features, advanced AI tools, and 100,000+ premium templates.` + 按钮 `Upgrade now`
- **如何确认点对**：**功能区只剩三格且 `WPS AI` 标签变紫底高亮**。若功能区仍是字体/段落那一大排 = 没点中。
- **易混按钮**：左侧竖排首页里的 `WPS AI`（那是首页导航项，不是这条标签）；底栏的 `AI Spell Check` 开关也是同名功能
- **误点后果与恢复**：无破坏，点 `Home` 标签即恢复原功能区
- **对话可用性**：**不能当对话用**。这里没有输入框、没有会话，只有三个功能钮

### W-06 `Improve Writing`（WPS AI 标签内）

- **按钮原文**：`Improve Writing`
- **图标特征**：一张带横线的纸 + 一支笔，蓝色细线
- **位置参照**：`WPS AI` 标签激活后，三格工具栏的**中间那格**
- **点击后果**：**空文档点：无任何可见变化**（无弹窗、无面板、无提示）。**选中一段文字后再点：仍然无任何可见变化**。两种情形都不弹登录框、不弹付费框。
- **结果锚文本**：无（点击前后画面完全一致；唯一变化是选区仍保持高亮，底栏 `Words: 6/6`）
- **如何确认点对**：点前记下"当前没有第四个窗口"，点后**枚举窗口列表没有新窗口** = 已点中但无产出。**别用"多了个面板"当成功判据，这里永远不会有**
- **易混按钮**：`AI Spell Check`（左，是开关类）与它并排，两颗都无 `⌄`
- **误点后果与恢复**：无破坏。**但会让人误以为软件卡死**——这是本档案最重要的一条"点不动"结论
- **对话可用性**：不能当对话用；**结论边界**：只在"未登录 + 免费态"下验证，登录/会员后是否可用 → **【待核对】**

### W-07 左上 `≡ 文件`（文件菜单）

- **按钮原文**：`File`（三横线图标 + 文字，紧贴标签条下方最左）
- **图标特征**：三条横线，深灰
- **位置参照**：编辑器左上角第一颗；它右边依次是保存、打印预览、撤销、重做 `⌄`、正文样式框
- **点击后果**：**从左侧滑出文件菜单浮层**（不是下拉小菜单），右侧同时铺开一块内容区（默认显示 `Recent`）
- **结果锚文本**：浮层竖向条目原文（自上而下）`New`(带 `▸`) / `Open` / `Save` / `Save As`(带 `▸`) / `Export to PDF` / `Export to Picture` / `Print`(带 `▸`) / `Share`(带 `▸`) / `Document Encryption`(带 `▸`) / `Backup and Restore`(带 `▸`) / `Help`(带 `▸`) / `Options`(带 `▸`) / `Exit`；`Print` 与 `Share` 之间有一条分隔线
- **如何确认点对**：**左侧出现整块白色浮层且首项是 `New`**。只有一排图标没变 = 没点中
- **易混按钮**：标签条上的 `Home` 标签（同在最左，但位置更靠上、且有白底标签形）
- **误点后果与恢复**：菜单本身无破坏；**但条目之间只差 40~60 px，极易点错邻项**（实测把 `Export to PDF` 点成了 `Export to Picture` 两次，见第七节 E-034）。点空白处或按 Esc 收起
- **对话可用性**：与对话无关

### W-08 文件菜单里的 `Export to Picture`

- **按钮原文**：`Export to Picture`
- **图标特征**：方框内一座小山（图片图标）+ 左侧蓝色小箭头
- **位置参照**：文件菜单浮层里**紧接在 `Export to PDF` 下面一行**（两者图标几乎一样，只差框内是 `P` 还是山）
- **点击后果**：弹一个**独立的大面板窗口**（标题 `Export to Picture`，1317×859，屏幕居中偏右），预览区右下角浮着 `Edit Watermark` 提示
- **结果锚文本**：面板字段原文 `Export Type`（两张卡 `By Page`(选中蓝边) / `Long picture`）、`Watermark`（三颗 `None`(选中) / `Custom` / `Default`）、`Pages`（`All`）、`Format`（`PNG ⌄`）、`Quality`（`Standard (200%) ⌄`）、`Export Path`（`C:\Users\<user>\My Pictures\` + `...` 按钮）、复选框 `Backup to WPS Cloud`（**默认未勾**）、左下 `Sign in to unlock more benefits.` + `Sign in`、右下主按钮 `Export`
- **如何确认点对**：**多出一个标题为 `Export to Picture` 的窗口**（与主窗分开，可单独截图）
- **易混按钮**：**`Export to PDF`（上一行）**——图标同族，误点会得到图片不是 PDF；`Export to Picture` 产出的是 **PNG 图片，不可再编辑**
- **误点后果与恢复**：未点 `Export` 就不落盘；点右上 `×` 关闭即可。**若点了 `Export` 会在 `My Pictures` 生成 PNG**
- **对话可用性**：与对话无关

---

## 五、第三轮追加补测（W-09 ~ W-12，实测）

- **本篇适用**：用户问 WPS 导出 PDF、导出图片、右上分享的实际落点

### W-09 文件菜单里的 `Export to PDF`

- **按钮原文**：`Export to PDF`
- **图标特征**：方框内一个蓝色 `P` 字母 + 左侧蓝色小箭头（**与下一行 `Export to Picture` 只差框内图案**：这里是 `P`，那里是山）
- **位置参照**：文件菜单浮层里 **`Save As` 下面第二行、`Export to Picture` 正上一行**
- **点击后果**：**不开独立窗口，在主窗内部弹出一块蓝头浮层**（覆盖在文档区上方，带阴影），档位默认已勾当前文档
- **结果锚文本**：标题条 `Export to PDF` + 右侧 `Feedback`；工具行橙色按钮 `+ Add files` + 右侧 `WPS Pro enjoys batch PDF export feature.` `Upgrade Now`；表头 `Select all (1)` `Remove All` | `Pages` | `Export range` | `Status` | `Operation`；数据行 `Document1` + 页码框 `1`~`1`；`Save Path`（下拉 `Same Directory` + 灰字 `Same directory as source file`）；`Export Type`（`Common PDF` 选中 / `Image PDF` 副说明 `Can't be edited and copied`）；复选框 `Backup to Cloud (WPS CloudExport to PDF)`（**默认未勾**）；`Advanced Settings`；绿色主按钮 `Export to PDF`；复选框 `Open after export`（**默认已勾**）
- **如何确认点对**：**主区内出现蓝 `Export to PDF` 标题条**即可；**别去枚举窗口**——它没有独立窗口（这是本档案最大的取证陷阱，见 E-035）
- **易混按钮**：`Export to Picture`（下一行，弹的是 1317×859 独立面板，**会多出一个窗口**——两者"有没有新窗口"正好相反，这就是区分判据）
- **误点后果与恢复**：点错成图片 → 关掉那个独立面板即可。**浮层里的绿色 `Export to PDF` 才是真导出**，且 `Open after export` 默认勾着，导出后会自动打开生成的 PDF
- **对话可用性**：与对话无关

### W-10 右上 `Share ⌄`

- **按钮原文**：`Share`（右侧一个 `⌄`）
- **图标特征**：蓝字 + 蓝色描边小圆角框 + 下拉箭头；**未登录态下是"描边"样式，不是实心**
- **位置参照**：编辑器右上角，`Not saved` 文字右侧、`...` 与窗口按钮左侧
- **点击后果**：**弹的是 `Save As` 保存对话框**（不是分享面板）——因为未登录/未保存时分享要先落盘
- **结果锚文本**：对话框标题 `Save As`；左栏 `Drive`（`Personal Space`/`Share`/`Google`/`Dropbox`）、`Local`（`This PC`/`Desktop`/`Documents`/`Downloads`/`Browse`）；路径栏 `This PC > Drive (C:) > Users > <user> > Desktop`；列头 `Name`/`Date modified`/`Size`；底部 `File Name`（默认填**正文首句**，实测为 `This sentence is very bad written.docx`）、`File Type`（`Word Documents (*.docx) ⌄`）、`Encrypt(E)...`、`Save`、`Cancel`
- **如何确认点对**：**出现 `Save As` 标题的对话框**。若什么都没弹，说明点在了 `⌄` 外面
- **易混按钮**：文件菜单里的 `Share`（同名不同位，在浮层里，**带 `▸` 子菜单**）
- **误点后果与恢复**：按 `Save` 会把文档存到**桌面**（默认路径现成的），属于往用户桌面写文件——**不要按**。**按 `Esc` 可关闭**（实测有效，见 E-037）
- **对话可用性**：与对话无关

### W-11 首页左栏 `Docs`（类型导航）

- **按钮原文**：`Docs`（蓝底白字 `W` 方块图标 + 下方文字）
- **图标特征**：圆角方块，`W` 白字，蓝底（`Slides` 是橙底 `P`，`Sheets` 是绿底 `S`，`PDF` 是红底 `P`）
- **位置参照**：首页**最左侧竖排导航**，自上而下 `Home` / `New` / `WPS AI` / 分隔线 / `Docs` / `Slides` / `Sheets` / `PDF`
- **点击后果**：**仍在首页，但把内容区换成"只看文档"的过滤视图**，并多出一排快捷操作条；`Recent` 里只剩 docx 一条
- **结果锚文本**：内容区顶部一排：蓝色实心 `+ Blank`、`Open`、`Create from Template`，右侧两颗紫字 `AI Spell Check` `Improve Writing`；下方 `Recent` 列表仅 `WPS Docs Quick Start Guide.docx` + `Local`；右侧 `File Information` / `Select a file to view details`
- **如何确认点对**：**左栏该项变白底卡片（选中态）且顶部出现蓝色实心 `+ Blank`**。列表没被过滤 = 没切成功
- **易混按钮**：左栏竖排的 `New`（绿色加号）——`New` 去**模板中心**，`Docs` 只**过滤列表**
- **误点后果与恢复**：不改任何文件，点左栏 `Home` 回总览
- **对话可用性**：与对话无关

### W-12 Docs 视图里的实心 `+ Blank`

- **按钮原文**：`Blank`（左侧一个 `+`）
- **图标特征**：**蓝色实心**圆角按钮 + 白色 `+`，是全页最显眼的主按钮
- **位置参照**：Docs/Slides/Sheets/PDF 过滤视图顶部操作条**最左第一个**
- **点击后果**：**直接新建空白文档并切到该标签，不经过 `Create New` 模板页**；标题变 `Document2 - WPS Office`（序号递增，说明是同一进程里第 2 份）
- **结果锚文本**：新标签 `Document2`；状态栏 `Page: 1/1` `Words: 0`
- **如何确认点对**：**标题出现递增的 `DocumentN`**。仍在 `Home - WPS Office` = 没点中
- **易混按钮**（三颗都叫 Blank，后果不同）：
  - `Create New` 模板页里的 `Blank` **卡**（白纸缩略卡）→ 同样建空白文档，但路径要绕模板页
  - 本条的实心 `Blank` **按钮**（Docs 等过滤页顶栏）→ **一步到位**
  - `Slides`/`Sheets`/`PDF` 过滤页里的同名按钮 → 建的是对应类型
- **误点后果与恢复**：只建一份未落盘的空白文档；关标签时选"不保存"即可
- **对话可用性**：与对话无关

### 附带实测：`Esc` 能关掉 WPS 的 `Save As` 框

- 误开 `Save As` 后按 `Esc`，对话框立即消失、文档原样保留（**与智谱/豆包"Esc 关不掉菜单"相反**，见 E-037）

---

## 六、本次**未点**或**未测成**的（诚实登记）

- **本篇适用**：用户问 WPS 哪些按钮是刻意没点、为什么没点

| 编号 | 按钮 | 状态 | 原因 |
|---|---|---|---|
| W-09 | 文件菜单 `Export to PDF` | **✅ 已测**（见 五、W-09） | 内嵌浮层，非独立窗口，已补齐 |
| W-10b | 首页左栏 `Slides` / `Sheets` / `PDF` | 未点 | `Docs` 已测，其余三项同构但未逐颗点 |
| W-11b | 首页左栏那颗竖排 `New`（绿色加号） | 未点 | 与顶部 `+ New` 同名不同位，需单独验 |
| W-12b | Docs 页 `Open` / `Create from Template` / `AI Spell Check` / `Improve Writing` | 未点 | 与已测的同名功能重复度高，`Open` 会拉系统文件框 |
| W-13 | 编辑器右上 `Sign in` / `Upgrade Now` | 未点 | 账号/付费，不代点 |
| W-14 | 表格 `et.exe` / 演示放映 `Slide Show` | 未测 | 本轮只进了文字与演示的编辑界面，未做放映与表格 |
| W-X1 | 「设为默认办公软件」框的 `Confirm` | **只读不点** | 会改系统文件关联 |
| W-X2 | 文件菜单 `Exit` / `Document Encryption` / `Backup and Restore` / `Print` / `Save` / `Save As` | 只读不点 | 退出程序 / 加密 / 恢复 / 打印 / 落盘，属破坏、改状态或写用户磁盘 |

**「设为默认办公软件」框（W-X1）实测形态**（只记录不断言执行）：标题 `WPS Office`，正文 `Set WPS Office as the default office software to make your work more convenient.`，右侧一个 `ⓘ`，底部复选框 `Don't remind me again`（**默认未勾**），按钮 `Confirm`，右上 `×`。**每次打开文档都会再弹一次**，点 `×` 可关。

---

## 七、多分辨率

- **本篇适用**：用户问 WPS 这些结论在什么屏幕分辨率和缩放下成立

全部实测仅在 **100% 缩放**（2560×1600）下完成。150%/125% 与其他分辨率 **未测**（按既定决定标"待补测"）。

---

## 八、新增经验（详见 `experience.md` E-029 ~ E-037）

- **本篇适用**：用户要 WPS 相关经验条目与本档案的对应关系

- **E-029** WPS 首启是**英文界面 + 隐私协议**，照中文习惯找"同意"会找错，锚文本必须抄英文
- **E-030** WPS 是**单窗口多标签**，标题随标签变（`WPS Office`→`New - WPS Office`→`Document1 - WPS Office`），用标题定位窗口会失效
- **E-031** 打开任何文档都重弹「设为默认办公软件」，`Confirm` 改系统关联
- **E-032** `WPS AI` 标签未登录态=空三格，点 `Improve Writing` 零反馈（不弹登录也不弹付费）
- **E-033** 最大化窗口压在上面时，`-title` 窗口截图截到的是**压在上面那个窗口**，会误判"点了没反应"（本次因此白点十几次）
- **E-034** 整窗截图里目测比例换算坐标会偏 10%+，密集菜单必点错邻项；必须先**裁剪标定**再点
- **E-035** WPS 多数"看似弹窗"的东西是**主窗内嵌浮层**（`Export to PDF` 面板即是），窗口枚举永远找不到它——用"有没有新窗口"判成败会误判成"没点中"
- **E-036** 未登录/未保存态点右上 `Share ⌄`，弹的是 `Save As` 保存框（不是分享面板），默认文件名取**正文首句**
- **E-037** WPS 的 `Save As` 框按 `Esc` 能关；`Esc 关不掉菜单` 只是智谱/豆包的结论，不能跨软件推论

---

## 九、证据图索引（`imgs/`）

- **本篇适用**：用户要 WPS 每颗按钮对应的证据图文件名

| 文件 | 拍到什么 |
|---|---|
| `wps-start-home-1.png` | 协议已过后的首页（英文：`Home`/`New`/`WPS AI`/`Docs`/`Slides`/`Sheets`/`PDF`、四张卡、`Recent` 四行） |
| `wps-btn_new-1.png` | 点 `+ New` 后的 `Create New` 页 + 红字 `Network error...` + `Blank` 卡 |
| `wps-popup_defaultoffice-1.png` | 「设为默认办公软件」确认框（`Confirm` / `Don't remind me again` / `×`） |
| `wps-editor-home-1.png` | 文字编辑器 `Home` 功能区全貌 + 状态栏 `Page: 1/1` |
| `wps-btn_ai_tab-1.png` | `WPS AI` 标签激活后只剩三格（`AI Spell Check`/`Improve Writing`/`Settings`） |
| `wps-btn_improve-1.png` | 选中文本（`Words: 6/6`）后点 `Improve Writing` 仍无任何反馈 |
| `wps-btn_filemenu-1.png` | `≡ 文件` 滑出的整块浮层（`New`…`Exit` 十二项） |
| `wps-btn_exportpic-1.png` | `Export to Picture` 面板（格式/质量/路径/`Export`） |
| `wps-slides-editor-1.png` | 打开 pptx 后的演示编辑器（`Slide 1 / 13`） |
| `wps-btn_exportpdf-1.png` | 文件菜单 `Export to PDF` 弹出的**主窗内嵌浮层**全字段（`+ Add files`/表格行/`Export Type`/`Export to PDF` 绿钮/`Open after export` 已勾） |
| `wps-btn_share_saveas-1.png` | 点右上 `Share ⌄` 后弹出的 `Save As` 保存框（左栏 Drive/Local、文件名预填正文首句、`Save`/`Cancel`） |
| `wps-btn_docs-1.png` | 左栏 `Docs` 过滤视图：实心 `+ Blank`/`Open`/`Create from Template`/两颗 AI 快捷 + `Recent` 只剩 docx |

---

## 十、自检

- **本篇适用**：用户要核对 WPS 这份有没有把没测写成实测

- [x] 每颗实测按钮都有九字段（按钮原文/图标特征/位置参照/点击后果/结果锚文本/如何确认点对/易混按钮/误点后果与恢复/对话可用性）
- [x] 锚文本逐字抄英文原文，未翻译、未编造
- [x] 位置一律相对参照物（"最左第一张卡"、"紧接在 X 下面一行"），**全文无绝对坐标**
- [x] **`Export to PDF` 已实测**：面板字段逐字抄录，并注明它**没有独立窗口**；仍未按导出主按钮（会往磁盘落 PDF），这一点已写在误点后果里
- [x] 危险按钮（`Confirm`/`Exit`/`Exit WPS`/`Save`）单独登记，只读不点；`Share ⌄` 误开的 `Save As` 已用 `Esc` 取消、未落盘
- [x] 多分辨率状态明写"待补测"

## 五之二、第五轮补测：首页左侧竖排导航 4 颗 + File 菜单 `Open`

- **本篇适用**：用户问 WPS 左侧竖排 Slides/Sheets/PDF 和 File 菜单 Open 点下去什么后果

> 前提：WPS 首页（`Home - WPS Office`）。左侧竖排图标自上而下依次是 `Home`、`New`（绿色圆加号）、`WPS AI`（紫色星）、`Docs`（蓝）、`Slides`（橙）、`Sheets`（绿）、`PDF`（红）。**每个都是图标在上、文字在下**，所以点的时候要对准图案本身而不是文字。

### W-13 竖排 `Slides`

- **按钮原文**：`Slides`（橙色方块内白色 `P` + 下方文字）
- **点击后果**：首页**就地切换成幻灯片过滤**，不切窗口、标题仍是 `Home - WPS Office`、不新开标签
- **结果锚文本（逐字）**：`Recent` 列表只剩一行 `WPS Slides Quick Start Guide.pptx` + `Local`，路径列 `C:\Users\<user>\...`，时间 `Today 04:22`，大小 `814 KB`；左栏 `Slides` 出现白色圆角选中框；按钮行 `+ Blank` 仍为**蓝色**
- **如何确认点对**：**列表文件名后缀从 `.docx` 变成 `.pptx`**，且左栏该项有白色选中底
- **易混按钮**：与上方的 `WPS AI`（紫色星）紧邻，两个图标之间只隔约 10 像素；与底部 `Create from Template` 的模板分类不是一处
- **误点后果与恢复**：只是筛选视图，不改文件；点 `Home` 图标可回全类型 `Recent`
- **对话可用性**：与对话无关

### W-14 竖排 `Sheets`

- **按钮原文**：`Sheets`（绿色方块内白色 `S`）
- **点击后果**：首页就地切换成表格过滤
- **结果锚文本（逐字）**：`+ Blank` 按钮**由蓝变橙**（这是最可靠的判据）；`AI Spell Check` 与 `Improve Writing` 两颗**消失**（表格没有这两个文档能力）；列表随后出现 `WPS Sheets Quick Start Guide.xlsx` + `Local`，大小 `1.5 MB`
- **如何确认点对**：**`+ Blank` 变橙色**；列表后缀是 `.xlsx`
- **注意（易误判）**：切换瞬间列表可能**仍显示上一次的 pptx**（约 1–2 秒后才换成 xlsx），只截第一屏会得错误结论
- **误点后果与恢复**：纯筛选，点 `Home` 复原
- **对话可用性**：与对话无关

### W-15 竖排 `PDF`

- **按钮原文**：`PDF`（红色方块内白色 `P` 形）
- **点击后果**：首页就地切换成 PDF 过滤
- **结果锚文本（逐字）**：`+ Blank` 按钮**由橙变绿**（PDF 用绿色，与 Sheets 的橙不同，**别把绿当成"回到初始态"**）
- **如何确认点对**：`+ Blank` 的底色是绿色；与 Sheets 的橙色是两颗不同按钮
- **易混按钮**：`Sheets` 与 `PDF` 都是绿/红方块带字母，且上下紧邻，**只能靠颜色区分**（Sheets 绿底 `S`，PDF 红底 `P`）
- **误点后果与恢复**：纯筛选，点 `Home` 复原
- **对话可用性**：与对话无关

### W-16 竖排 `New`（绿色圆加号）

- **按钮原文**：`New`（绿色实心圆 + 白色 `+`）
- **点击后果**：打开一个**独立的 `New` 标签页**（标签条上新出现 `New`），页面标题 `Create New`；窗口标题随之变成 **`New - WPS Office`**
- **结果锚文本（逐字）**：`Create New`；搜索框占位 `Search for Docs templates`；左列 `All` / `Docs`（选中）/ `Slides` / `Sheets` / `PDF`；内容区一张虚线卡片，中间 `+`，下方 `Blank`；左下角 `My Templates`
- **如何确认点对**：标签条多出一个叫 `New` 的页签，标题栏变 `New - WPS Office`
- **易混按钮**：与首页的实心 `+ Blank`（直接建空白文档）**不是一回事**——`New` 是"模板选择页"，`+ Blank` 是"立刻建空白"
- **误点后果与恢复**：只是多一个页签，点该页签右上的 `×` 关闭即可
- **对话可用性**：与对话无关
- **证据**：`imgs/wps-btn_new_page-1.png`

### W-17 File 菜单 `Open`（打开文件）

- **按钮原文**：`Open`（文件夹图标）
- **位置参照**：`≡ File` 下拉里，**`New` 的下一项**（`New` 有右箭头子菜单，`Open` 没有）
- **点击后果**：弹出**WPS 自绘的 `Open File` 面板**（在主窗内的浮层，**不是 Windows 原生「打开」对话框**）
- **结果锚文本（逐字）**：面板标题 `Open File`；左列分组 `Drive` 下 `Personal Space`、`Share`、`Google`、`Dropbox`；分组 `Local` 下 `This PC`、`Desktop`、`Documents`、`Downloads`；右侧筛选页签 `ALL` / `Docs`（选中）/ `Sheets` / `Slides` / `PDF`；表头 `Name`
- **点 `Desktop` 之后**：面板变成**文件浏览器**——工具条 `←` `→` `↑` `⟳`；面包屑 `This PC > Drive (C:) > Users > <user> > Desktop`；列表列出桌面的文件夹（`<工号><用户>`、`<工号>-<用户>-药店管理系统`、`cs2_startup_backup`、`咕嘎管家知识库` …），列头 `Name` / `Date`
- **如何确认点对**：出现 `Open File` 标题 + `Recent`/`Personal Space`/`Dropbox` 这一列来源；点 `Desktop` 后面包屑里出现 `Desktop`
- **易混按钮**：与首页那个 `Open` 按钮**不是一处**（首页是宽按钮，File 菜单里是列表项）；与 `Save As` 的保存框长得很像，**靠标题区分**：保存框标题是 `Save As`，这里是 `Open File`
- **误点后果与恢复**：**只读浏览**，不选文件就不会打开任何文档；按 `Esc` 关闭（WPS 的 Esc 有效）
- **对话可用性**：与对话无关
- **证据**：`imgs/wps-btn_file_open_panel-1.png`、`imgs/wps-btn_open_desktop-1.png`

### W-18 状态栏 `AI Spell Check` 开关（结论：未确认）

- **按钮原文**：`AI Spell Check`（蓝色胶囊形开关，位于窗口**左下状态栏**，`Words: n/n` 右边）
- **点击后果**：点击后**外观仍是蓝色 ON**，未见任何面板、提示或正文标记变化；本次**无法判断是否真的切换了**
- **如何确认点对**：开关位于状态栏、紧跟在 `Words:` 计数右边——位置确认没问题，**但状态反馈未确认**
- **诚实标注**：本颗**只能算"点过"，不能算"测出后果"**，标【待核对】
- **误点后果与恢复**：无可见副作用
- **对话可用性**：与对话无关
- **证据**：`imgs/wps-btn_ai_spell_statusbar-1.png`

## 检索提示

- WPS 首启协议、首页 + New、Blank 卡、最近文件行
- WPS File 菜单各项、WPS AI 页签、导出 PDF 与导出图片
- WPS 左侧竖排 Docs/Slides/Sheets/PDF 的就地过滤
- WPS 哪些按钮刻意没点及原因

