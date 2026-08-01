# P1 能力补齐：人格化决策 / 实盘网关 / 产业链深化 / 组合优化

**日期**：2026-08-01
**需求**：按差距分析路线图 P0→P1→P2 顺序，落地 P1 四项：①人格化 Agent 决策层 ②实盘交易网关 ③产业链深化 ④组合优化与风险归因
**状态**：已完成并实测

## ① 人格化 Agent 决策层（P1-①）
多角色 Agent（估值/基本面/技术/情绪/风控，权重 0.25/0.25/0.15/0.15/0.20）并行研判 + PM 加权共识汇总。
- 模块：`src/persona_agents.py`；端点：`POST /api/v1/persona-analysis?code=`
- 复用 `MultiAgentOrchestrator`（其内置等权共识），本层用 `_pm_decide` 按人格权重重算共识、风险等级；LLM 可选增强，失败降级规则。
- 修复：原 `analyze_personas` 把 `ConsensusReport` 直接当 `Dict[str, AgentReport]` 传入 `_pm_decide` 导致 `AttributeError`，改为提取 `orch.analyze().agents` 后重算。

## ② 实盘交易网关（P1-②，可插拔 Broker）
- 模块：`src/trading_gateway.py`；端点：`/api/v1/trading/*`（status / orders / positions / account / decide / execute-decision）
- 默认 `paper` 模拟撮合（本地 JSON 账本 `data/trading/paper_ledger.json`，零风险可离线测）；`live` 模式仅当环境变量 `TRADING_BROKER/TRADING_API_KEY/TRADING_API_SECRET` 配置后启用（否则 `LiveBroker` 拒绝一切操作）。
- 决策翻译 `decide()`：bullish+低风险→建仓建议；bearish+持仓→减仓建议；high/extreme 风险→禁止开仓（仅允许减仓）。
- MCP 工具：`trading_status`、`place_trade`。

## ③ 产业链深化（P1-③）
- 模块：`src/industry_chain_propagation.py`；端点：
  - `POST /api/v1/industry-chains/{chain_id}/propagate`（冲击传导推演，沿边 coeff/lag 向上下游传染，返回环节与公司受影响程度）
  - `POST /api/v1/industry-chains/portfolio-exposure`（持仓→产业链暴露映射 + HHI 集中度与预警）
- 复用既有 `industry_chain.py` 图谱（内置沙盘 + xzsc 融合），冲击节点支持模糊匹配（id/label/子串）。

## ④ 组合优化与风险归因（P1-④，纯 numpy）
- 模块：`src/portfolio_optimizer.py`；端点：
  - `POST /api/v1/portfolio/optimize`（max_sharpe / min_variance / risk_parity）
  - `POST /api/v1/portfolio/risk-attribution`（边际/成分/百分比风险贡献分解 + HHI 风险集中度）
- 收益协方差估计：在线 akshare 真实日线，离线确定性合成（市场因子+特质噪声，可复现）。
- 风险平价用 Gauss-Seidel 坐标下降（逐坐标解 a·w_i²+c_i·w_i−K=0 正根），保证等边际风险贡献。
- MCP 工具：`optimize_portfolio`、`portfolio_risk_attribution`。

## 设计与约定
- 可插拔 + 离线降级：在线数据优先，离线/失败走规则估算或合成数据，绝不编造（ESG 等不编造评分）。
- 注意：持仓→产业链为「多归属」映射（单股票可属多条链），暴露权重之和可超过 100%，HHI 仅作粗略集中指示。
