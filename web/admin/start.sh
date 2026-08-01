#!/bin/bash
# ============================================================
# 量化投研管理后台 — 启动脚本
# 技术栈: Vue3 + Vite + Element Plus + ECharts
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
NODE_BIN="/Users/a123456/.workbuddy/binaries/node/versions/22.22.2/bin"

cd "$PROJECT_DIR"

# 检查 node_modules
if [ ! -d "node_modules" ]; then
  echo "[INFO] 首次运行，正在安装依赖..."
  $NODE_BIN/npm install
fi

# 确保后端 API 地址
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
export VITE_API_BASE="$BACKEND_URL"

echo "============================================"
echo "  量化投研管理后台"
echo "  前端地址: http://localhost:3100"
echo "  后端地址: $BACKEND_URL"
echo "============================================"

# 启动模式
MODE="${1:-dev}"

if [ "$MODE" = "build" ]; then
  echo "[BUILD] 构建生产包..."
  $NODE_BIN/npx vite build
  echo "[DONE] 构建产物在 dist/ 目录"
elif [ "$MODE" = "preview" ]; then
  echo "[PREVIEW] 预览构建产物..."
  $NODE_BIN/npx vite preview --port 3100 --host
else
  echo "[DEV] 启动开发服务器..."
  $NODE_BIN/npx vite --port 3100 --host
fi
