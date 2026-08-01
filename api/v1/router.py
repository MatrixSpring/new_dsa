# -*- coding: utf-8 -*-
"""
===================================
API v1 路由聚合
===================================

职责：
1. 聚合 v1 版本的所有 endpoint 路由
2. 统一添加 /api/v1 前缀
"""

from fastapi import APIRouter

from api.v1.endpoints import (
    agent,
    alerts,
    alphasift,
    analysis,
    auth,
    backtest,
    company,
    dashboard,
    factor_mining,
    mcp_gateway,
    persona_analysis,
    decision_signals,
    health,
    history,
    industry_chain,
    intelligence,
    portfolio,
    portfolio_optimization,
    stocks,
    system_config,
    trading,
    usage,
    strategy_backtest,
    graph_rl_strategy,
    export,
    community,
)

# 创建 v1 版本主路由。
# /api/v1 前缀在 api.app 挂载，避免新版 FastAPI 误判子路由 "" 为 empty path。
router = APIRouter()

router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Auth"]
)

router.include_router(
    agent.router,
    prefix="/agent",
    tags=["Agent"]
)

router.include_router(
    analysis.router,
    prefix="/analysis",
    tags=["Analysis"]
)

router.include_router(
    history.router,
    prefix="/history",
    tags=["History"]
)

router.include_router(
    stocks.router,
    prefix="/stocks",
    tags=["Stocks"]
)

router.include_router(
    backtest.router,
    prefix="/backtest",
    tags=["Backtest"]
)

router.include_router(
    system_config.router,
    prefix="/system",
    tags=["SystemConfig"]
)

router.include_router(
    usage.router,
    prefix="/usage",
    tags=["Usage"]
)

router.include_router(
    portfolio.router,
    prefix="/portfolio",
    tags=["Portfolio"]
)

router.include_router(
    alerts.router,
    prefix="/alerts",
    tags=["Alerts"]
)

router.include_router(
    decision_signals.router,
    prefix="/decision-signals",
    tags=["DecisionSignals"]
)

router.include_router(
    alphasift.router,
    prefix="/alphasift",
    tags=["AlphaSift"]
)

router.include_router(
    intelligence.router,
    prefix="/intelligence",
    tags=["Intelligence"]
)

router.include_router(
    health.router,
    tags=["Health"]
)

# ---- v2.1.0 Dashboard 仪表盘端点 ----
# dashboard.router 已内置完整路径前缀，只需挂载一次
router.include_router(
    dashboard.router,
    tags=["Dashboard"]
)

# ---- 产业链全景可视化（内置沙盘 + 新质生产力 xzsc 底层数据）----
router.include_router(
    industry_chain.router,
    tags=["IndustryChain"]
)

# ---- 上市公司全维度信息（company_profile 表只读接口）----
router.include_router(
    company.router,
    tags=["Company"]
)

# ---- 自动因子挖掘闭环（P0-②，借鉴 Qlib + RD-Agent）----
router.include_router(
    factor_mining.router,
    tags=["FactorMining"]
)

# ---- MCP 开放接口（P0-③，对标 Wind/同花顺 2026 Agent 生态）----
router.include_router(
    mcp_gateway.router,
    tags=["MCP"]
)

# ---- 人格化投资 Agent 决策层（P1-①，借鉴 ai-hedge-fund）----
router.include_router(
    persona_analysis.router,
    tags=["PersonaAnalysis"]
)

# ---- 实盘交易网关（P1-②，可插拔 Broker：模拟/实盘桩）----
router.include_router(
    trading.router,
    prefix="/trading",
    tags=["Trading"]
)

# ---- 组合优化与风险归因（P1-④，纯 numpy 均值-方差/风险平价/风险分解）----
router.include_router(
    portfolio_optimization.router,
    prefix="/portfolio",
    tags=["PortfolioOptimization"]
)

# ---- P2-① 策略回测引擎（内置 vector / 可选 backtrader 适配器）----
router.include_router(
    strategy_backtest.router,
    tags=["StrategyBacktest"]
)

# ---- P2-② 图网络 / RL 策略（相关性图谱 + 信号传播 + 多臂 Bandit）----
router.include_router(
    graph_rl_strategy.router,
    tags=["GraphRLStrategy"]
)

# ---- P2-③ Excel / 报告导出（openpyxl）----
router.include_router(
    export.router,
    prefix="/export",
    tags=["Export"]
)

# ---- P2-④ 社区 / 分享层（帖子/评论/点赞，自包含 DB）----
router.include_router(
    community.router,
    prefix="/community",
    tags=["Community"]
)
