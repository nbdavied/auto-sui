#!/usr/bin/env bash
# =====================================================================
# auto-sui 后端服务部署脚本 (Ubuntu 22.04) —— 仅本机跑 HTTP 后端
#
# 拓扑: 本机只起一个 uvicorn 后端(同时托管前端静态文件), 监听 0.0.0.0:8000;
#       Nginx + 域名 TLS 证书在【另一台服务器】上, 由它反代到本机的 8000 端口。
#       本脚本不安装/不配置 Nginx、不申请证书、不碰防火墙。
#
# 前提(脚本不会替你做):
#   1. 能用 root 登录(装依赖需要)
#   2. (Gmail 用户) 一个能从本机连上的代理(Clash/V2Ray 地址)
#   3. 对端 nginx 服务器能把 https://域名 反代到 http://本机IP:8000
#
# 用法:
#   sudo bash install.sh
# 跑之前可改下面「配置区」的默认值, 或运行后用交互提示补全。
# =====================================================================

set -uo pipefail

# ------------------------- 配置区(可改) -------------------------
DOMAIN="${DOMAIN:-}"                       # 公网域名, 仅用于 FRONTEND_URL / GOOGLE_REDIRECT_URI(本机不配 nginx)
REPO_URL="${REPO_URL:-git@github.com:nbdavied/auto-sui.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/auto-sui}"
SERVICE_USER="${SERVICE_USER:-autosui}"
SERVICE_HOME="${SERVICE_HOME:-/var/lib/autosui}"
# Gmail 代理(境内必需). 例: socks5://127.0.0.1:10808 或 http://127.0.0.1:10809
# 留空则 Gmail 功能不可用(记账/对账仍正常).
GMAIL_PROXY="${GMAIL_PROXY:-}"
# 可选: 本机已有的 credentials.json 路径, 脚本会拷到项目根目录
GOOGLE_CREDENTIALS="${GOOGLE_CREDENTIALS:-}"
# 本机监听地址/端口(对端 nginx 要能访问, 故默认 0.0.0.0 而非 127.0.0.1)
BIND_HOST="${BIND_HOST:-0.0.0.0}"
BIND_PORT="${BIND_PORT:-8000}"
# ----------------------------------------------------------------

# 缺域名(仅 Gmail 需要)就交互询问, 允许留空
if [ -z "$DOMAIN" ]; then
  read -r -p "请输入公网域名(仅用于 Gmail 回调, 不用 Gmail 可直接回车): " DOMAIN
fi

TEMPLATE_DIR="$INSTALL_DIR/deploy"
LOG=/tmp/auto-sui-install.log
exec > >(tee -a "$LOG") 2>&1

echo "==> 部署 auto-sui 后端到 http://$BIND_HOST:$BIND_PORT (Nginx/证书在另一台服务器)"
echo "    代码目录: $INSTALL_DIR"
echo "    运行用户: $SERVICE_USER"

# ------------------------- 0. 权限检查 -------------------------
if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 运行: sudo bash install.sh"; exit 1
fi

# ------------------------- 1. 系统依赖 -------------------------
echo "==> [1/7] 安装系统依赖(不含 nginx/certbot)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  git curl ca-certificates gnupg lsb-release \
  python3-venv python3-pip software-properties-common

# ------------------------- 2. Node.js(构建前端) -------------------------
echo "==> [2/7] 安装 Node.js 20 (Vite 需要 18+)"
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 18 ]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
node -v; npm -v

# ------------------------- 3. 拉取代码 -------------------------
echo "==> [3/7] 获取代码"
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "    已存在, 执行 git pull"
  git -C "$INSTALL_DIR" pull --ff-only
else
  rm -rf "$INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

# ------------------------- 4. 运行用户 -------------------------
echo "==> [4/7] 创建运行用户 $SERVICE_USER"
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home-dir "$SERVICE_HOME" \
  --create-home --shell /usr/sbin/nologin "$SERVICE_USER"

# ------------------------- 5. Python 虚拟环境 -------------------------
echo "==> [5/7] 创建 venv 并安装后端依赖"
if [ ! -d "$INSTALL_DIR/venv" ]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip -q
"$INSTALL_DIR/venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt" -q

# ------------------------- 6. 构建前端 -------------------------
echo "==> [6/7] 安装并构建前端(由本机 uvicorn 一起托管)"
cd "$INSTALL_DIR/web"
if [ ! -d node_modules ]; then npm install; fi
npm run build
cd "$INSTALL_DIR"

# ------------------------- 7. 环境变量 + 注册服务 -------------------------
echo "==> [7/7] 写入 /etc/auto-sui/env 并注册 systemd"
if [ -n "$GOOGLE_CREDENTIALS" ] && [ -f "$GOOGLE_CREDENTIALS" ]; then
  echo "    拷贝 credentials.json"
  cp "$GOOGLE_CREDENTIALS" "$INSTALL_DIR/credentials.json"
fi

mkdir -p /etc/auto-sui
cat > /etc/auto-sui/env <<EOF
# auto-sui 后端服务环境变量(改完执行: systemctl restart auto-sui)
# 本机只跑 HTTP 后端, Nginx/TLS 在另一台服务器; 故监听所有网卡供对端反代
HOST=$BIND_HOST
PORT=$BIND_PORT
RELOAD=0

# 会话落盘: 解决 Gmail 授权中途服务重启导致授权失效
AUTOSUI_SESSION_FILE=$INSTALL_DIR/sessions.db
AUTOSUI_SESSION_TTL=28800

# Gmail(境内必需代理才能连 Google)
HTTPS_PROXY=$GMAIL_PROXY
HTTP_PROXY=$GMAIL_PROXY
GOOGLE_TIMEOUT=15
# 若 credentials.json 不在项目根目录, 取消下面这行注释并改为实际路径
# GOOGLE_CREDENTIALS=$INSTALL_DIR/credentials.json
EOF

# 域名仅用于 Gmail 回调跳回公网地址; 不启用 Gmail 可不设
if [ -n "$DOMAIN" ]; then
cat >> /etc/auto-sui/env <<EOF

# 公网域名(生产必须, 否则 OAuth 回调会跳回本机地址)
FRONTEND_URL=https://$DOMAIN
GOOGLE_REDIRECT_URI=https://$DOMAIN/api/gmail/callback
EOF
else
cat >> /etc/auto-sui/env <<'EOF'

# 未设置域名: 如启用 Gmail, 取消下面注释并填公网域名
# FRONTEND_URL=https://your.domain
# GOOGLE_REDIRECT_URI=https://your.domain/api/gmail/callback
EOF
fi
chmod 600 /etc/auto-sui/env

# systemd
sed -e "s|__SERVICE_USER__|$SERVICE_USER|g" \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    "$TEMPLATE_DIR/auto-sui.service" > /etc/systemd/system/auto-sui.service
systemctl daemon-reload
systemctl enable --now auto-sui

# 赋权
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"
chmod 600 "$INSTALL_DIR"/sessions.db 2>/dev/null || true

echo
echo "==================== 后端部署完成 ===================="
echo "本机服务地址: http://$BIND_HOST:$BIND_PORT"
echo "查看状态: systemctl status auto-sui"
echo "查看日志: journalctl -u auto-sui -f"
echo
echo ">>> 下一步(在【另一台】带域名证书的 nginx 服务器上):"
echo "    1) 参考 deploy/auto-sui.nginx.conf, 把 __DOMAIN__ 改成你的域名,"
echo "       把 __BACKEND_ADDR__ 改成  http://本机IP:$BIND_PORT"
echo "    2) Google Cloud 的重定向 URI 填: https://你的域名/api/gmail/callback"
echo "    3) 本机防火墙建议只放行【对端 nginx 的 IP】到 $BIND_PORT, 不要对公网开放"
if [ -z "$GMAIL_PROXY" ]; then
  echo "⚠️ 未配置 Gmail 代理(GMAIL_PROXY 为空). Gmail 功能将不可用; 如需启用请填代理后 restart。"
fi
