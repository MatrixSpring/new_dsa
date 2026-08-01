# -*- coding: utf-8 -*-
"""MCP 工具清单（P0-③）。供 stdio server 与 REST manifest 端点共享。"""

TOOLS = [
    {
        "name": "list_companies",
        "description": "搜索/列出上市公司（支持代码/名称/拼音模糊搜索，按数据来源过滤，分页）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "代码/名称/拼音关键字"},
                "source": {"type": "string", "description": "数据来源过滤，如 industry_chain_fusion"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_company",
        "description": "获取单家上市公司全维度详情（基础/估值/财务/产业链/一致预期/ESG）。",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "6 位股票代码"}},
            "required": ["code"],
        },
    },
    {
        "name": "list_industry_chains",
        "description": "列出全部产业链（新质生产力 xzsc 与申万融合），含每条链的融合公司与计数值。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_industry_chain",
        "description": "获取单条产业链的节点图、关联公司与融合（申万/curated）公司。",
        "inputSchema": {
            "type": "object",
            "properties": {"chain_id": {"type": "string"}},
            "required": ["chain_id"],
        },
    },
    {
        "name": "get_factor_mining_results",
        "description": "查看自动因子挖掘闭环结果（IC/多空收益等），可按代次或仅最优因子过滤。",
        "inputSchema": {
            "type": "object",
            "properties": {"active_only": {"type": "boolean", "description": "仅返回当前保留的最优因子"}},
        },
    },
    {
        "name": "run_factor_mining",
        "description": "触发一轮自动因子挖掘闭环（生成→评估→进化保留）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "max_gen": {"type": "integer"},
                "top_k": {"type": "integer"},
                "online": {"type": "boolean", "description": "联网用真实日线评估(默认离线合成)"},
            },
        },
    },
    {
        "name": "run_backtest",
        "description": "对指定股票运行分析建议回测。",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    {
        "name": "agent_chat",
        "description": "向分析 Agent 发起对话（股票/产业链/市场/因子等分析问答）。",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
    {
        "name": "trading_status",
        "description": "查询交易网关状态（模式 paper/live、是否配置实盘凭证）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "place_trade",
        "description": "通过交易网关提交一笔订单（默认 paper 模拟撮合，零风险）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "6 位股票代码"},
                "side": {"type": "string", "description": "buy / sell"},
                "quantity": {"type": "number", "description": "数量(股)"},
                "price": {"type": "number", "description": "成交价(模拟模式必填)"},
            },
            "required": ["symbol", "side", "quantity"],
        },
    },
    {
        "name": "optimize_portfolio",
        "description": "组合优化：均值-方差(max_sharpe/min_variance)或风险平价，返回目标权重与风险归因。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "objective": {"type": "string", "description": "max_sharpe / min_variance"},
                "risk_parity_mode": {"type": "boolean", "description": "True 返回风险平价权重"},
                "online": {"type": "boolean", "description": "是否用真实日线估计(默认合成)"},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "portfolio_risk_attribution",
        "description": "风险归因：把组合波动分解到每个标的(边际/成分/百分比贡献)。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "权重(与symbols等长)，缺省等权"},
                "online": {"type": "boolean"},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "run_strategy_backtest",
        "description": "策略回测：内置 vector 引擎（默认）或可选 backtrader。策略 ma_cross/momentum/mean_reversion/factor。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "6 位股票代码"},
                "strategy": {"type": "string", "description": "ma_cross/momentum/mean_reversion/factor"},
                "engine": {"type": "string", "description": "vector / backtrader（缺省 vector）"},
                "online": {"type": "boolean"},
                "n": {"type": "integer", "description": "回测长度(交易日)"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "run_graph_rl",
        "description": "图网络信号传播 + RL 多臂 Bandit 组合策略（相关性图谱+自适应选号），返回相关图/RL权重/组合回测。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "至少 2 只标的"},
                "online": {"type": "boolean"},
                "n": {"type": "integer"},
                "lookback": {"type": "integer"},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "export_portfolio_report",
        "description": "导出组合分析报告 JSON（组合优化+风险归因+候选画像+最优因子），用于前端预览或二次处理。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "objective": {"type": "string"},
                "risk_parity_mode": {"type": "boolean"},
                "online": {"type": "boolean"},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "community_post",
        "description": "在社区发布一条分享帖（标题/正文/标签）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "author": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
        },
    },
    {
        "name": "community_list",
        "description": "列出社区帖子（可按标签筛选，按 new/hot 排序）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag": {"type": "string"},
                "sort": {"type": "string", "description": "new / hot"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
        },
    },
    {
        "name": "community_like",
        "description": "对社区帖子点赞/取消点赞（按 user_name 去重）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "post_id": {"type": "integer"},
                "user_name": {"type": "string"},
            },
            "required": ["post_id"],
        },
    },
]
