#!/bin/bash

set -euo pipefail

# 基于脚本位置定位项目根目录（scripts/ 的上一级）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

PORT="${DEPLOY_RUN_PORT:-5000}"

# 确保 uv 可用（沙箱重置后 uv 会被清除，需要自动重装）
ensure_uv() {
  if command -v uv &>/dev/null; then
    return 0
  fi
  echo "[run] uv not found, installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  echo "[run] uv installed: $(uv --version)"
}

# 开发/预览环境标识，启用数据库降级
export DEV_MODE="1"

usage() {
  echo "用法: $0 -p <端口>"
}

while getopts "p:h" opt; do
  case "$opt" in
    p)
      PORT="$OPTARG"
      ;;
    h)
      usage
      exit 0
      ;;
    \?)
      echo "无效选项: -$OPTARG"
      usage
      exit 1
      ;;
  esac
done

# 显式声明关键环境变量，不依赖平台执行环境继承
export PORT

# 清理端口残留进程（幂等性：重复执行不会冲突）
fuser -k "${PORT}/tcp" 2>/dev/null || true
sleep 1

# 激活 .venv（devbox 环境），deploy 无 .venv 则跳过
if [ -f "${PROJECT_DIR}/.venv/bin/activate" ]; then
  source "${PROJECT_DIR}/.venv/bin/activate"
else
  # .venv 不存在（沙箱重置后），自动安装依赖
  echo "[run] .venv not found, running setup first..."
  ensure_uv
  if [ -f "uv.lock" ]; then
    uv sync --frozen || uv sync
  else
    uv sync
  fi
  touch .venv/.uv_ready
  source "${PROJECT_DIR}/.venv/bin/activate"
fi

exec python ${PROJECT_DIR}/src/main.py -m http -p $PORT
