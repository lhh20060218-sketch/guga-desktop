# 上传到 GitHub 的步骤（可照抄）

适用：Windows，PowerShell。目标是把 `guga-competition` 整理成一个**只含源码与文档**的仓库，347MB 发行包走 Releases 附件。

> 当前机器未检测到 `git` 命令，先装 Git（第一步）。

---

## 0. 先看清三条红线

| 红线 | 说明 |
|---|---|
| 单个文件 ≤ 100MB | 本仓库最大文件 35.3MB（`HearthDb.dll`），满足 |
| 仓库只放源码/文档 | `dist/ build/ runtime/ tools/clean_bench/` 等已在 `.gitignore` 排除 |
| 绝不提交真实 Key | `ai_config.json`、`.env` 已排除；提交前再做一次扫描 |

当前可入库内容约 **265 MB / 5161 个文件**（主要是 `resources/actions` 动作帧 154MB 与 `knowledge/` 知识库）。

---

## 1. 安装 Git（本机尚未安装）

```powershell
winget install --id Git.Git -e --source winget
```

装完关掉并重开终端，确认：

```powershell
git --version
```

首次使用配置身份（替换成你自己的）：

```powershell
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

---

## 2. 处理旧 `.git`（重要）

仓库里已有 `.git`（约 376MB 的开发期历史），可能包含：
- 早期的大文件（会让推送极慢甚至被拒）
- 历史提交里已经写入过的 Key / 本机路径（删掉文件也仍在历史里）

**推荐做法：把旧历史移到仓库外备份，重新初始化一个干净仓库。**

```powershell
cd d:\rengongzhineng\guga-competition

# 移到仓库外，避免被 git add 重新收进来
Move-Item .git ..\.git-guga-backup-20261108

git init -b main
```

> 如果你确认要保留旧历史，跳过本节，但先自查：`git log --all --oneline` 与 `git rev-list --objects --all` 里有没有不该出现的文件。

---

## 3. 本地提交

```powershell
cd d:\rengongzhineng\guga-competition

# 看看会提交哪些文件（应为 5000 左右，不含 dist/build/runtime/tools/clean_bench）
git add .
git status --short | Measure-Object -Line

# 确认关键文件被忽略（应输出匹配的 .gitignore 规则）
git check-ignore -v ai_config.json
git check-ignore -v dist
git check-ignore -v tools/clean_bench

# 提交
git commit -m "feat: 咕嘎 · 会监工的 AI 管家桌宠（参赛版源码）"
```

如果 `git status` 里出现 `dist/`、`runtime/`、`tools/clean_bench/` 或任何 `.zip`，**先停下来检查 `.gitignore`**，不要提交。

---

## 4. 建远程仓库并推送

### 方式 A：用 GitHub CLI（最快）

```powershell
winget install --id GitHub.cli -e --source winget
gh auth login          # 选 GitHub.com → HTTPS → 浏览器登录

cd d:\rengongzhineng\guga-competition
gh repo create guga-desktop --public --source=. --remote=origin --push
```

### 方式 B：网页建仓 + 命令行推送

1. 打开 https://github.com/new
2. 仓库名填 `guga-desktop`，**不要**勾选 “Add a README / .gitignore / license”（本地已有）
3. 然后执行：

```powershell
cd d:\rengongzhineng\guga-competition
git remote add origin https://github.com/<你的账号>/guga-desktop.git
git push -u origin main
```

> 265MB 首次推送可能需要几分钟；若卡在 `Writing objects`，先检查是否误加了数 GB 目录。

---

## 5. 发 Release 并上传 347MB 发行包

发行包**不进 Git 历史**，只作为 Release 附件。

```powershell
# 打 tag 并推送
git tag -a v1.0.0 -m "咕嘎 v1.0.0 · 参赛交付版"
git push origin v1.0.0

# 用 gh 直接发 Release（把 zip 路径换成你桌面上的实际文件）
gh release create v1.0.0 "C:\Users\<你>\Desktop\GUGA-Desktop-20261108-0716-最终版.zip" `
  --title "咕嘎 v1.0.0 · 参赛交付版" `
  --notes "Windows 10 1809+ / 11 x64。解压后双击 GUGA-Desktop.exe；首次运行需在 SmartScreen 点「更多信息 → 仍要运行」。使用说明见 README / INSTALL / USAGE。"
```

不想用命令行：网页仓库 → **Releases → Draft a new release** → 选择 tag `v1.0.0` → 填写标题说明 → 把 zip 拖进附件区 → **Publish release**。

Release 附件上限 2GB，347MB 没问题。

---

## 6. 大文件与 LFS 的正确用法

### 本仓库需要 LFS 吗？

**不需要。** 最大单文件 35.3MB，全部低于 GitHub 100MB 硬限制；265MB 总量也在正常范围。

### 什么时候才用 LFS

只有「必须把大于 100MB 的二进制放进 Git 历史」时才用：

```powershell
git lfs install
git lfs track "*.psd"        # 换成你的大文件类型
git add .gitattributes
git add <大文件>
git commit -m "chore: 用 LFS 管理大素材"
```

注意：
- GitHub 免费 LFS 额度约 1GB 存储 / 1GB 月流量，347MB 的包反复更新几次就会超额。
- **发行包不要用 LFS**，用 Releases 附件更合适（不计入仓库体积、可单独替换版本）。

### 如果仓库体积还想更小

| 可剔除项 | 体积 | 代价 |
|---|---|---|
| `resources/actions/task-motion/` | 93 MB | 任务执行动作动画缺失 |
| `resources/actions/idle-motion/` | 30.6 MB | 待机动画缺失 |
| `knowledge/buttons/` | 25.9 MB | 界面自动化按钮锚点截图缺失，UI 兜底变弱 |
| `resources/actions/_dz3_sample/` | 5.5 MB | 仅样本，可安全移除 |
| `knowledge/sense/` | 11.4 MB | 软件界面感知截图缺失 |

全部剔除可降到约 100MB，但会削弱演示效果，**不建议**为了体积牺牲可运行性。真要压缩，优先把 PNG 帧批量转 WebP 并降采样，而不是删功能。

---

## 7. 推送前后各做一次检查

```powershell
cd d:\rengongzhineng\guga-competition

# 1) 有没有超大文件（应无输出）
git ls-tree -r -l HEAD | ForEach-Object { $p=$_ -split "`t"; if([long]$p[0] -gt 50MB){ $p[0] + ' ' + $p[-1] } }

# 2) 有没有真实凭据
git grep -n -I -E "sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}" -- .

# 3) 有没有个人绝对路径
git grep -n -I -E "C:\\\\Users\\\\[A-Za-z0-9]+" -- .

# 4) 确认忽略项
git check-ignore -v ai_config.json dist runtime tools/clean_bench
```

三条检索都应为空。若第 3 条命中，把路径改成 `%USERPROFILE%` / `%LOCALAPPDATA%` 后再提交。

---

## 8. 上传后回填仓库地址

把 README 与 `ai_config.example.json` 里的占位地址替换成你的真实仓库/服务器地址，再次提交：

```powershell
git add README.md
git commit -m "docs: 补充仓库与 Release 地址"
git push
```

---

## 附：本次仓库已准备好的文件

| 文件 | 用途 |
|---|---|
| `README.md` | 作品介绍、能力、架构、快速开始 |
| `INSTALL.md` | 发行包安装 / 源码运行 / 常见安装问题 |
| `USAGE.md` | 实际使用方式与边界 |
| `LICENSE` | MIT |
| `.gitignore` | 排除构建产物、运行数据、凭据、本机验收台 |
| `requirements.txt` | 源码运行依赖（已按实际导入补齐） |
| `ai_config.example.json` | 配置模板（无真实 Key） |
| `docs/可移植性审计报告.md` | 换机器风险评估与限制清单 |
| `docs/` | 其余技术与演示文档 |
