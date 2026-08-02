#!/usr/bin/env bash
# 前端「数据 → 显示」验证运行器：esbuild 打包 verify 脚本（注入 import.meta.env shim）后 node 执行 SSR 断言。
set -euo pipefail

ROOT=/Users/a123456/Downloads/AABB/0725/test01
ESBUILD="$ROOT/node_modules/@esbuild/darwin-arm64/bin/esbuild"
ENTRY="$ROOT/apps/dsa-web/scripts/verify_backtrace_display.tsx"
OUT=/tmp/verify_backtrace.cjs

cd "$ROOT"
"$ESBUILD" "$ENTRY" \
  --bundle \
  --platform=node \
  --format=cjs \
  --jsx=automatic \
  --loader:.json=json \
  --define:import.meta.env='{"VITE_API_URL":"","MODE":"production"}' \
  --log-level=warning \
  --outfile="$OUT"

node "$OUT"
