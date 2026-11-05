#!/usr/bin/env bash
# 咕嘎管家体验版 · 一键部署（兼容 Debian/Ubuntu 与 CentOS/Alibaba Cloud Linux）
# 用法：上传 guga-server 目录到服务器后，cd 进来执行 bash deploy.sh
set -e
cd "$(dirname "$0")"

echo "=== 1/4 安装 Node.js 20（已有 node>=18 可跳过） ==="
if command -v node >/dev/null 2>&1 && [ "$(node -v | cut -dv -f2 | cut -d. -f1)" -ge 18 ]; then
  echo "node $(node -v) 已满足"
else
  if command -v apt-get >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
  elif command -v dnf >/dev/null 2>&1; then
    curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
    dnf install -y nodejs
  elif command -v yum >/dev/null 2>&1; then
    curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
    yum install -y nodejs
  else
    echo "未识别的包管理器，请手动安装 Node.js >= 18 后重跑本脚本"; exit 1
  fi
fi
node -v

echo "=== 2/4 安装依赖 ==="
npm install --omit=dev

echo "=== 3/4 生成配置文件 ==="
if [ ! -f .env ]; then
  cp .env.example .env
  echo ">>> 请编辑 .env：填入 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL（第 4 步启动前务必完成）"
fi

echo "=== 4/4 安装 pm2 并启动（开机自启） ==="
if ! command -v pm2 >/dev/null 2>&1; then npm install -g pm2; fi
pm2 delete guga 2>/dev/null || true
pm2 start server.js --name guga --time
pm2 save
pm2 startup 2>/dev/null || true

IP=$(curl -s ifconfig.me || echo "你的服务器公网IP")
echo ""
echo "=============================================="
echo " 服务已启动！访问:  http://$IP:3000"
echo " 下一步（必须）:"
echo "   1) vi .env 填大模型三件套，然后 pm2 restart guga"
echo "   2) 放行防火墙 TCP 3000（阿里云控制台防火墙 + 宝塔[安全]页）"
echo " 常用: pm2 logs guga | pm2 restart guga | pm2 stop guga"
echo "=============================================="
