#!/bin/bash
set -eo pipefail

# 基于脚本位置定位项目根目录（scripts/ 的上一级）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 确保 uv 可用（沙箱重置后 uv 会被清除，需要自动重装）
ensure_uv() {
  if command -v uv &>/dev/null; then
    return 0
  fi
  echo "[setup] uv not found, installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  echo "[setup] uv installed: $(uv --version)"
}
ensure_uv

# 初始化目录
if [ "$COZE_PROJECT_ENV" = "DEV" ]; then
  if [ ! -d "${PROJECT_DIR}/assets" ]; then
    mkdir -p "${PROJECT_DIR}/assets"
  fi
fi

# uv 安装依赖
if [ -n "$PIP_TARGET" ]; then
  echo "[setup] Deploy mode (uv): installing to PIP_TARGET=$PIP_TARGET"
  uv export --frozen --no-hashes --no-dev | uv pip install --no-cache --target "$PIP_TARGET" -r -
else
  echo "[setup] Devbox mode (uv): installing to .venv"
  if [ -f "uv.lock" ]; then
    uv sync --frozen || uv sync
  else
    uv sync
  fi
  touch .venv/.uv_ready
fi
