# 前端"网络异常，请稍后重试"Bug 修复 + 架构体检

- 日期：2026-08-01
- 需求：点击页面出现"网络异常，请稍后重试"，修复该 Bug，并检查项目是否需架构优化
- 状态：已完成修复并验证；架构体检结论见下

## 根因
- 前端（web/admin，Vue）运行在 `http://localhost:3100`，但其请求层 `src/api/request.js` 的 `baseURL = VITE_API_BASE = http://127.0.0.1:8000`（绝对跨域地址）。
- 后端 `api/app.py` 的 CORS `allowed_origins` 仅含 5173/3000 端口，**缺少 `localhost:3100`**。
- 浏览器发起跨域请求后，后端未回显 `Access-Control-Allow-Origin`，浏览器拦截响应 → `error.response` 为空 → 触发 "网络异常，请稍后重试" 兜底提示。所有取数页面均受影响。

## 修复方案（双保险）
1. **后端 CORS**：`api/app.py` 的 `allowed_origins` 增补 `http://localhost:3100`、`http://127.0.0.1:3100`（保留原 5173/3000）。
2. **前端改用 Vite 代理（正本清源）**：`web/admin/.env.development` 的 `VITE_API_BASE` 置空，使请求走相对路径 `/api`，经 Vite dev server 代理（同源，彻底消除 CORS 依赖）。Vite 配置中 `/api` 代理目标为 `http://127.0.0.1:8000`，已验证可用。
- 验证：后端回显 `Access-Control-Allow-Origin: http://localhost:3100`；`http://localhost:3100/api/v1/companies` 经代理返回 200 与数据。

## 架构体检结论（是否需要优化）
需要，存在若干可优化点，本次已修复最关键的 2 项：
- **已修复**：① 跨域/CORS 不匹配；② 清理冗余的第二个 Vite dev server（5173，带 `--force`），现仅保留 3100 单一开发服务器。
- **建议（未改）**：
  1. **前端存在两套 axios 客户端且变量名不一致**：`src/api/request.js` 用 `VITE_API_BASE`（绝对、报"网络异常"），`src/utils/request.js` 用 `VITE_API_BASE_URL`（相对、带 token）。建议统一为单一 axios 实例，消除双套错误处理与配置漂移。
  2. **双前端并存**：生产由后端托管 `static/`（React，`apps/dsa-web` 构建，title=dsa-web），开发用 `web/admin`（Vue）。两套栈维护成本高，建议明确边界或收敛为单前端。
  3. **双后端入口**：根 `main.py`（61KB 旧版 CLI 编排器，内含 `from api.app import app`）与 `api.app:app`（现代 FastAPI）。建议明确 `api.app` 为唯一服务入口，`main.py` 仅保留分析编排职责或标注废弃。
  4. **模块边界重叠**：顶层 `core/` 与 `src/core/`、`api/`（后端）与 `src/api/`（客户端库）并存，易引发导入歧义。建议梳理职责边界。
  5. **构建产物入库**：`static/assets/*` 为 React 构建产物且被 git 跟踪，可能随源码漂移。建议确认 `static/` 是否仍为生产前端，若是则纳入 CI 构建而非手填，或改由 `apps/dsa-web/dist` 统一产出。

## 涉及改动文件
- `api/app.py`（CORS 白名单）
- `web/admin/.env.development`（VITE_API_BASE 置空，改用代理）
- 提交：`487bc01`
