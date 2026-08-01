# 产业链沙盘原型集成并对接底层数据

**日期**：2026-08-01
**需求**：将 `industry_chain_sandbox.html` 产业链沙盘原型页面源码集成到 Vue3 管理后台 `web/admin`，并与其底层数据层对接（不再使用原型硬编码的 INDUSTRY_CHAINS，改为从后端/数据库读取）。
**状态**：已完成

## 背景
原型为单文件 HTML（SVG 图谱 + BFS 传导推演 + 公司穿透 + 冲击事件），数据硬编码 3 条富数据链（锂电池/半导体/光伏）。
底层已持久化 58 条新质生产力链（xzsc_industry_chain 表）+ 原型自带 3 条富数据链，需让前端由"硬编码"升级为"底层数据驱动"。

## 关键决策
- 后端新建 `api/v1/endpoints/industry_chain.py`：三接口 list/graph/shocks，融合 3 内置沙盘富数据 + 58 xzsc 底层链；xzsc 链由 segments（上游/中游/下游）实时推导节点与边。
- 前端新建 `web/admin/src/api/industryChain.js` 对接后端；`IndustryChainSandbox.vue` 由原型脚本机械改造（DOM API 改 ref 查询、内联 onclick 挂 window、CSS 作用域到 `.ics-sandbox`），保留 SVG 布局/BFS 推演/公司穿透逻辑。
- `IndustryChainView.vue` 新增「产业链沙盘」Tab。
- 原型富数据落库 `src/data/industry_chain_sandbox_data.json`。

## 验证
- `npm run build` 成功；dev server `localhost:3100` 与 backend `:8000` 双 200。
- 接口：`/industry-chains` total 61（3 sandbox + 58 xzsc）；单链返回 nodes/edges/companies/news；shocks 6 条；未知 id 404。

## 关联
- 下游需求：xzsc 与申万产业链数据融合（见 `2026-08-01-xzsc-shenwan-fusion.md`）。
- 数据层：xzsc_industry_chain 表；sandbox 富数据 json。
