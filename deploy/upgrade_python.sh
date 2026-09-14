#!/usr/bin/env bash
# =====================================================================
# auto-sui 后端 Python 升级脚本 (Ubuntu 22.04 后端 VM)
#
# 背景: Ubuntu 22.04 自带 Python 3.10.12, 而 google.api_core 将从
#       2026-10-04 起停止支持 3.10 (import 时已打印 FutureWarning)。
#       本脚本在不动系统 Python 的前提下, 并存安装指定版本的 Python,
#       并用它【重建 venv】(系统 Python 保持不动, 数据安全)。
#
# 设计:
#   - 只停服/起服, 不碰系统 python3
#   - venv 路径保持 /opt/auto-sui/venv 不变 => auto-sui.service 无需改动
#   - 旧 venv 改名备份, 不立即删除
#   - 数据文件 (autosui.db / sessions.db) 单独备份一次
#
# 用法:
#   sudo bash deploy/upgrade_python.sh            # 默认装 3.12
#   PYVER=3.11 sudo -E bash deploy/upgrade_python.sh
# =====================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/auto-sui}"
SERVICE="${SERVICE:-auto-sui}"
PYVER="${PYVER:-3.12}"

OLD_VENV="$INSTALL_DIR/venv"
TS="$(date +%s)"

echo "==> 目标: 将 venv 的 Python 升级到 $PYVER (系统 Python 不动)"
echo "    安装目录: $INSTALL_DIR"

# ------------------------- 1. 停服 -------------------------
echo "==> [1/6] 停止 $SERVICE"
systemctl stop "$SERVICE" 2>/dev/null || echo "    (服务未运行, 忽略)"

# ------------------------- 2. 备份数据文件 -------------------------
echo "==> [2/6] 备份数据文件"
BACKUP_DIR="$HOME/auto-sui-backup-$(date +%F)"
mkdir -p "$BACKUP_DIR"
for f in autosui.db sessions.db conf.json credentials.json; do
  if [ -f "$INSTALL_DIR/$f" ]; then
    cp -n "$INSTALL_DIR/$f" "$BACKUP_DIR/" && echo "    备份 $f"
  fi
done

# ------------------------- 3. 安装新 Python (deadsnakes) -------------------------
echo "==> [3/6] 安装 Python $PYVER (deadsnakes PPA)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -y
apt-get install -y --no-install-recommends "python${PYVER}-venv" "python${PYVER}-dev"

NEW_PY="/usr/bin/python${PYVER}"
if [ ! -x "$NEW_PY" ]; then
  echo "错误: 未找到 $NEW_PY"; exit 1
fi
echo "    新 Python: $("$NEW_PY" --version)"

# ------------------------- 4. 重建 venv (路径不变) -------------------------
echo "==> [4/6] 重建 venv -> $OLD_VENV"
if [ -d "$OLD_VENV" ]; then
  mv "$OLD_VENV" "${OLD_VENV}.old.${TS}"
  echo "    旧 venv 备份为 ${OLD_VENV}.old.${TS}"
fi
"$NEW_PY" -m venv "$OLD_VENV"

# ------------------------- 5. 重装依赖 -------------------------
echo "==> [5/6] 重装后端依赖"
"$OLD_VENV/bin/python" -m pip install --upgrade pip -q
"$OLD_VENV/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt" -q
echo "    venv Python: $("$OLD_VENV/bin/python" --version)"

# ------------------------- 6. 起服 -------------------------
echo "==> [6/6] 启动 $SERVICE"
systemctl daemon-reload
systemctl start "$SERVICE"
systemctl status "$SERVICE" --no-pager || true

echo
echo "==================== 升级完成 ===================="
echo "若需回滚: 停服后 mv ${OLD_VENV}.old.${TS} -> $OLD_VENV 并重启"
