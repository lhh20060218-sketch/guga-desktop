---
name: git-push-cn-windows
description: Troubleshoot and fix git push to GitHub on Windows in China when Steam++ or similar accelerators intercept HTTPS. Use when git push fails with CRYPT_E_NO_REVOCATION_CHECK, curl 55 Send failure, or Connection reset on github.com. Do not use for gitee, gitlab, or non-Windows environments.
---

# Git Push to GitHub on Windows in China

This skill covers the exact sequence that succeeded for `guga-competition`
pushing `263.7 MB / 5206 files` to `github.com/lhh20060218-sketch/guga-desktop`.

## Quick Diagnosis (run in order)

```powershell
# 1) hosts 里有没有 github.com（加速器 MITM 标志）
Select-String -Path "C:\Windows\System32\drivers\etc\hosts" -Pattern "github"

# 2) Steam++ / Watt Toolkit 是否在跑
Get-Process | Where-Object { $_.ProcessName -match '(?i)steam\+\+|steamtools|watt' }

# 3) WinHTTP（git schannel 用） vs WinINET（浏览器用）
netsh winhttp show proxy
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" | Select-Object ProxyEnable,ProxyServer

# 4) 直连 github.com:443 和 :22
Test-NetConnection github.com -Port 443 -WarningAction SilentlyContinue
Test-NetConnection github.com -Port 22 -WarningAction SilentlyContinue

# 5) 直连拿到的证书是谁签的
$tcp=New-Object System.Net.Sockets.TcpClient; $tcp.Connect("github.com",443)
$ssl=New-Object System.Net.Security.SslStream($tcp.GetStream(),$false,({$true} -as [System.Net.Security.RemoteCertificateValidationCallback]))
$ssl.AuthenticateAsClient('github.com')
$c=New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
"Subject=$($c.Subject)  Issuer=$($c.Issuer)  Thumbprint=$($c.Thumbprint)"
```

## Three Scenarios and Fixes

### Scenario A — MITM Hosts Block

Symptom: hosts 里有 `github.com 127.0.0.1` 或加速器 IP；git 报
`schannel: next InitializeSecurityContext failed: CRYPT_E_NO_REVOCATION_CHECK`；
直连 443 拿到的证书 Issuer 是 `SteamTools Certificate` 等加速器签发的。

Root cause: 加速器开了 HTTPS 加速 → hosts 劫持 + 自签根证书。
浏览器走 WinINET 代理能开 GitHub；git schannel 用 WinHTTP 直连 → 撞 MITM。

Fix: 让用户在加速器里**关闭 GitHub 加速**，或者**完全退出**加速器。
hosts 里的 github 条目会被清掉。重跑诊断步骤 1→应无输出。

### Scenario B — WinHTTP Not Using the Accelerator Proxy

Symptom: hosts 干净，加速器在跑，但 `netsh winhttp show proxy` 显示
`Direct access (no proxy server)`；Test-NetConnection github.com 443 = False
或 curl 超时。

Root cause: 加速器只接管了 WinINET（浏览器）和用户代理变量，
WinHTTP（git schannel 后端）没配置，直连 GitHub 443 在国内被墙。

Fix: 给 git 显式加代理：

```powershell
git -c http.proxy="http://127.0.0.1:<加速器代理端口>" ls-remote --heads origin
```

加速器代理端口常见值：Steam++ 在 `HKCU\Internet Settings\ProxyServer`
里能看到（如 `http://localhost:26501`），或 netstat 找 `LISTENING` 里
非系统的 `127.0.0.1:<端口>`。

注意：走 MITM 代理时证书会被替换，还需要加 `http.sslBackend=openssl`
（MinGit 自带）并临时 `http.sslVerify=false`。这是安全退化——
加速器本来就能看到流量，sslVerify=false 不增加新风险。

### Scenario C — CRL Timeout Only (Direct Connection Works)

Symptom: hosts 干净，443 TCP 通，证书是真 GitHub（Sectigo / DigiCert /
Let's Encrypt 签发），但 git 仍报 `CRYPT_E_NO_REVOCATION_CHECK`。

Root cause: schannel 默认查询 CRL / OCSP 吊销列表，国内网络常超时。
sslVerify 实际上没问题，只是吊销检查超时。

Fix — **安全，推荐**（sslVerify 保持开启）：

```powershell
git -c http.schannelCheckRevoke=false push -u origin main
```

这条命令是本次成功路径。sslVerify=true 保持，只跳过 CRL/OCSP。

## Persistent Config (Optional, Per-Repo)

不想每次打 `-c` 的话，只在当前仓库设置（不动全局）：

```powershell
git config --local http.schannelCheckRevoke false
git config --local credential.helper manager   # GCM 存凭据
```

**不要**写入全局 `http.sslVerify=false`——那会让所有仓库的 HTTPS
都失去证书校验。

## Successful Push Template

```powershell
git -c http.schannelCheckRevoke=false `
    -c credential.interactive=always `
    push -u origin main
```

264 MB / 5206 files 推 GitHub，国内网络约 3–15 分钟。
如果推到一半断（`curl 55 Send failure` / `Connection was reset`），
直接重跑同一条——已上的对象会被远端拒绝并复用，不会从头开始。

## Verification Checklist

```powershell
# 1) 远端 HEAD hash 必须等于本地 HEAD
git ls-remote --heads origin      # 第一列 hex sha = 本地 HEAD
git rev-parse HEAD                # 本地 sha

# 2) 分支跟踪已建立
git branch -vv                    # 应显示 main [origin/main] ...

# 3) 工作区干净
git status --short                # 应无输出

# 4) 网页能打开（API 不受 TLS 影响，最稳）
Invoke-RestMethod "https://api.github.com/repos/<owner>/<repo>/branches/main" |
    Select-Object -ExpandProperty commit | Select-Object sha
```

## Known Hazards

1. **不要用 SSL 证书链绕 MITM**——为了让 git 信任加速器根证书，把证书
   导出 `.pem` 后配 `http.sslCAInfo`，那等于把你对 GitHub 的信任
   降成对加速器的信任。加速器本来就在看，不如直接用
   `http.schannelCheckRevoke=false`。

2. **不要把 PAT 写进 remote URL**——GitHub Desktop 或 GCM 会存到
   Windows 凭据管理器。用 `git credential fill` 只看，不要 `erase`
   掉其他凭据。

3. **MinGit vs PortableGit**——MinGit 不带 Git Credential Manager
   的 device code 流程弹浏览器所需的完整组件。遇到
   `fatal: User cancelled device code authentication` 时先等 GCM
   等够 120 秒；不要在 `GIT_TERMINAL_PROMPT=0` 下重试。

4. **国内直连 GitHub 443 的通断不稳定**——早上/半夜能通、白天不行。
   推荐策略：直接开加速器（Steam++ 全功能模式）+ Scenario C 配置，
   而不是试图"裸连省一步"。
