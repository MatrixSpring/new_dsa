# -*- coding: utf-8 -*-
"""
========================================================
量化投研管理后台 —— 接口 Mock 后端 (独立运行)
========================================================

前端 Vue3 管理后台 (web/admin) 按一套 /api/v1/* 接口契约开发，但项目原始
FastAPI 后端(api/app.py) 的路由路径与之完全不一致，且预览用的是纯静态文件
服务器(背后无后端)，导致每个接口请求都 404 -> 前端提示 "接口不存在"。

本文件用 FastAPI 实现前端期望的全部接口契约，返回符合各视图字段结构的
合成数据，并托管已构建的前端静态文件(dist)，使 7 个页面在单一端口真正跑起来。

运行方式:
    python mock_server.py            # 默认 0.0.0.0:3100
    python mock_server.py --port 8080
"""

import argparse
import json
import math
import os
import random
from datetime import datetime, timedelta

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

random.seed(20260801)

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
TODAY = datetime(2026, 8, 1)

# ---------------------------------------------------------------------------
# 响应包装
# ---------------------------------------------------------------------------
def wrap(data=None, msg="", code=200, success=True):
    """统一 ApiResp 格式: {success, code, msg, data}。request 拦截器取 data 字段。"""
    return {"success": success, "code": code, "msg": msg, "data": data}


def ok(data=None, msg=""):
    return wrap(data, msg)


# ---------------------------------------------------------------------------
# 基础数据：A 股样本池
# ---------------------------------------------------------------------------
STOCK_POOL = [
    ("600519", "贵州茅台", "白酒", 1685.0),
    ("000858", "五粮液", "白酒", 142.5),
    ("300750", "宁德时代", "电池", 198.3),
    ("002594", "比亚迪", "新能源车", 245.7),
    ("601012", "隆基绿能", "光伏", 18.6),
    ("600036", "招商银行", "银行", 38.2),
    ("000333", "美的集团", "家电", 72.4),
    ("600276", "恒瑞医药", "医药", 48.9),
    ("000651", "格力电器", "家电", 39.1),
    ("601318", "中国平安", "保险", 52.6),
    ("600900", "长江电力", "电力", 28.7),
    ("002415", "海康威视", "安防", 31.2),
    ("688981", "中芯国际", "半导体", 89.4),
    ("300059", "东方财富", "证券", 14.8),
    ("600030", "中信证券", "证券", 26.3),
    ("601899", "紫金矿业", "有色", 17.5),
    ("000725", "京东方A", "面板", 4.3),
    ("600585", "海螺水泥", "建材", 25.1),
]

STOCK_MAP = {c: (n, s, p) for c, n, s, p in STOCK_POOL}

# 产业链样本 (6 条)
CHAIN_NAMES = ["AI算力", "机器人", "光伏", "新能源汽车", "半导体", "白酒"]

NEWS_SOURCES = ["财联社", "上海证券报", "证券时报", "同花顺", "雪球", "东方财富", "华尔街见闻"]

POS_TITLES = [
    "业绩超预期，机构上调目标价", "获大额订单，产能利用率提升", "政策利好落地，行业景气度回升",
    "新技术突破，国产替代加速", "北向资金大幅净流入", "回购方案彰显发展信心",
    "签订战略合作，打开成长空间", "毛利率改善，盈利质量提升",
]
NEG_TITLES = [
    "下游需求疲软，库存压力加大", "价格战加剧，盈利承压", "海外制裁升级，出口承压",
    "业绩不及预期，估值面临回调", "大宗原材料涨价，成本端承压", "减持公告引发市场担忧",
    "行业竞争恶化，份额流失", "监管处罚落地，短期情绪受挫",
]
NEU_TITLES = [
    "召开股东大会，审议年度报告", "发布股权激励计划草案", "参与行业论坛，分享技术路线",
    "发布社会责任报告", "完成工商变更登记", "公布可转债发行进展",
]


# ---------------------------------------------------------------------------
# 数据生成工具
# ---------------------------------------------------------------------------
def trading_days(n, end=TODAY):
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:  # 周一到周五
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def gen_kline(code, start_date=None, end_date=None, days=120):
    """生成日K线 (OHLC + 成交量)，随机游走的真实感序列。"""
    name, sector, base = STOCK_MAP.get(code, (code, "未知", 30.0))
    prices = trading_days(days)
    out = []
    price = base * (0.85 + random.random() * 0.3)
    for d in prices:
        drift = random.uniform(-0.025, 0.027)
        open_p = price * (1 + random.uniform(-0.01, 0.01))
        close_p = open_p * (1 + drift)
        high_p = max(open_p, close_p) * (1 + random.uniform(0, 0.015))
        low_p = min(open_p, close_p) * (1 - random.uniform(0, 0.015))
        vol = random.randint(8_000_00, 1_200_000) * (1 + abs(drift) * 20)
        out.append({
            "date": d.strftime("%Y-%m-%d"),
            "open": round(open_p, 2),
            "close": round(close_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "volume": int(vol),
        })
        price = close_p
    return out


def gen_capital(code, days=60):
    prices = trading_days(days)
    out = []
    acc = 0.0
    for i, d in enumerate(prices):
        super_n = random.uniform(-3e8, 3.2e8)
        big_n = random.uniform(-2.5e8, 2.6e8)
        mid_n = random.uniform(-1.5e8, 1.5e8)
        small_n = -(super_n + big_n + mid_n) + random.uniform(-5e7, 5e7)
        main = super_n + big_n
        acc += main
        out.append({
            "date": d.strftime("%Y-%m-%d"),
            "net_amount": round(main, 2),
            "accumulate_net": round(acc, 2),
            "super_net": round(super_n, 2),
            "big_net": round(big_n, 2),
            "mid_net": round(mid_n, 2),
            "small_net": round(small_n, 2),
        })
    return out


def gen_news(key, count=22):
    items = []
    for i in range(count):
        roll = random.random()
        if roll < 0.42:
            sentiment, title_pool = "正面", POS_TITLES
        elif roll < 0.78:
            sentiment, title_pool = "负面", NEG_TITLES
        else:
            sentiment, title_pool = "中性", NEU_TITLES
        score = {"正面": random.uniform(0.3, 0.95), "负面": random.uniform(-0.95, -0.3),
                 "中性": random.uniform(-0.15, 0.15)}[sentiment]
        d = TODAY - timedelta(hours=random.randint(1, 360))
        items.append({
            "id": f"news_{key}_{i}",
            "title": f"【{key}】{random.choice(title_pool)}",
            "content": f"{key}相关动态：{random.choice(title_pool)}。市场关注度高，"
                       f"后续需观察基本面变化与资金面验证。",
            "source": random.choice(NEWS_SOURCES),
            "datetime": d.strftime("%Y-%m-%d %H:%M"),
            "sentiment": sentiment,
            "sentiment_score": round(score, 3),
            "url": "#",
        })
    # 排序
    items.sort(key=lambda x: x["datetime"], reverse=True)
    stat = {"正面": 0, "负面": 0, "中性": 0}
    for it in items:
        stat[it["sentiment"]] += 1
    return {"list": items, "sentiment_stat": stat}


def gen_backtest_result(stock_code, start, end, strategy):
    days = trading_days(random.randint(90, 220))
    nav = 1.0
    eq = []
    for d in days:
        nav *= (1 + random.uniform(-0.018, 0.021))
        eq.append({"date": d.strftime("%Y-%m-%d"), "equity": round(nav, 4)})
    total_return = nav - 1
    # 简易回撤
    peak = eq[0]["equity"]
    max_dd = 0.0
    for p in eq:
        peak = max(peak, p["equity"])
        dd = (p["equity"] - peak) / peak
        max_dd = min(max_dd, dd)
    years = max(0.2, (days[-1] - days[0]).days / 365.0)
    annual = (nav ** (1 / years)) - 1
    sharpe = round(annual / 0.18, 2)
    sortino = round(sharpe * random.uniform(1.1, 1.4), 2)
    calmar = round(annual / abs(max_dd), 2) if max_dd != 0 else 0.0
    win = random.uniform(0.48, 0.62)
    trades = []
    for i in range(random.randint(8, 26)):
        pnl = random.uniform(-0.06, 0.09)
        trades.append({
            "trade_id": i + 1,
            "date": days[random.randint(0, len(days) - 1)].strftime("%Y-%m-%d"),
            "symbol": stock_code,
            "side": "BUY" if pnl >= 0 else "SELL",
            "price": round(random.uniform(10, 200), 2),
            "qty": random.randint(100, 5000),
            "pnl": round(pnl, 4),
            "pnl_pct": round(pnl * 100, 2),
        })
    return {
        "id": None,  # 由调用方填充
        "task_id": None,
        "stock_code": stock_code,
        "strategy_name": strategy,
        "start_date": start,
        "end_date": end,
        "status": "completed",
        "total_return": round(total_return, 4),
        "annual_return": round(annual, 4),
        "max_drawdown": round(max_dd, 4),
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "win_rate": round(win, 4),
        "trade_count": len(trades),
        "equity_curve": eq,
        "trades": trades,
        "monthly_returns": _gen_monthly_returns(days, eq),
    }


def _gen_monthly_returns(days, eq):
    months = {}
    for p in eq:
        key = p["date"][:7]
        months.setdefault(key, []).append(p["equity"])
    out = []
    for m, vals in sorted(months.items()):
        if len(vals) >= 2:
            ret = (vals[-1] / vals[0] - 1) * 100
        else:
            ret = 0.0
        out.append({"month": m, "return": round(ret, 2)})
    return out


def gen_chain_graph(chain_name):
    """生成产业链多层级图谱 (上游/中游/下游 + 公司节点)。"""
    seg_nodes = {
        "upstream": [f"{chain_name}-上游原料", f"{chain_name}-关键材料"],
        "midstream": [f"{chain_name}-核心部件", f"{chain_name}-整机制造"],
        "downstream": [f"{chain_name}-工业应用", f"{chain_name}-终端消费"],
    }
    nodes = []
    nid = 1
    seg_ids = {}
    for seg, names in seg_nodes.items():
        for nm in names:
            seg_ids.setdefault(seg, []).append(nid)
            nodes.append({
                "id": nid,
                "name": nm,
                "type": "industry",
                "segment": seg,
                "impact_score": round(random.uniform(-2.5, 2.8), 1),
                "style": {"fill": {"upstream": "#38bdf8", "midstream": "#fbbf24",
                                   "downstream": "#34d399"}[seg], "size": 56},
            })
            nid += 1
    # 公司节点
    companies = random.sample([n for _, n, _, _ in STOCK_POOL], k=4)
    for cname in companies:
        nodes.append({
            "id": nid,
            "name": cname,
            "type": "company",
            "segment": "downstream",
            "impact_score": round(random.uniform(-1.5, 2.2), 1),
            "style": {"fill": "#a78bfa", "size": 40},
        })
        nid += 1
    # 边
    edges = []
    eid = 1
    for seg in ["upstream", "midstream", "downstream"]:
        ids = seg_ids[seg]
        if seg == "upstream":
            for s in ids:
                edges.append({"id": eid, "source": s, "target": seg_ids["midstream"][0],
                              "style": {"stroke": "#64748b", "lineWidth": 2, "label": "供给"},
                              "is_impact_path": False}); eid += 1
        elif seg == "midstream":
            for s in ids:
                edges.append({"id": eid, "source": s, "target": seg_ids["downstream"][0],
                              "style": {"stroke": "#64748b", "lineWidth": 2, "label": "集成"},
                              "is_impact_path": False}); eid += 1
    # 公司挂在下游
    for nd in nodes:
        if nd["type"] == "company":
            edges.append({"id": eid, "source": seg_ids["downstream"][-1], "target": nd["id"],
                          "style": {"stroke": "#a78bfa", "lineWidth": 1, "label": "关联"},
                          "is_impact_path": False}); eid += 1
    benefited = [n["id"] for n in nodes if n["impact_score"] > 1][:3]
    damaged = [n["id"] for n in nodes if n["impact_score"] < -1][:3]
    return {
        "nodes": nodes,
        "edges": edges,
        "benefited": benefited,
        "damaged": damaged,
        "animation_frames": [{"step": i, "node": random.choice(nodes)["id"]} for i in range(4)],
    }


def gen_chain_sim(event_key, layers):
    """动态事件推演引擎返回结构 (IndustryChainPanel 直接读取顶层字段)。"""
    nodes = []
    for i in range(1, 8):
        nodes.append({
            "id": i, "name": f"节点{i}", "layer": random.choice(["上游层", "中游层", "下游层", "配套层"]),
            "category": i % 4, "score": random.randint(35, 85),
        })
    links = [
        {"source": 1, "target": 3, "value": "成本传导", "elastic": 0.85},
        {"source": 2, "target": 3, "value": "材料支撑", "elastic": 0.75},
        {"source": 3, "target": 4, "value": "部件供给", "elastic": 0.90},
        {"source": 4, "target": 5, "value": "终端供货", "elastic": 0.80},
        {"source": 4, "target": 6, "value": "消费供给", "elastic": 0.82},
        {"source": 7, "target": 4, "value": "配套支撑", "elastic": 0.70},
    ]
    stock_list = [
        {"code": "300750", "name": "宁德时代", "relation": "直接受益", "effect": "利好",
         "effectType": "success", "logic": "需求扩张带动订单增长"},
        {"code": "002594", "name": "比亚迪", "relation": "间接受益", "effect": "利好",
         "effectType": "success", "logic": "产业链景气度提升"},
        {"code": "600519", "name": "贵州茅台", "relation": "弱相关", "effect": "中性",
         "effectType": "info", "logic": "消费端传导较弱"},
    ]
    return {
        "policyDesc": f"事件[{event_key}]触发产业政策正向调整，补贴与准入条件改善。",
        "sentimentDesc": "舆情情绪边际转暖，散户关注度上升。",
        "graphData": {"nodes": nodes, "links": links},
        "stockList": stock_list,
        "resultDesc": (f"综合多因子博弈推演：在 [{', '.join(layers) or '全部'}] 图层作用下，"
                       f"上游成本传导弹性较高，中游制造环节弹性最强，下游消费传导滞后。"
                       f"建议重点关注传导弹性 >0.8 的中游节点对应上市公司。"),
    }


# ---------------------------------------------------------------------------
# 内存状态 (自选股 / 回测任务)
# ---------------------------------------------------------------------------
_FAV_ID = 0
favorites = []
for _c, _n, _s, _p in STOCK_POOL[:10]:
    _FAV_ID += 1
    favorites.append({
        "id": _FAV_ID, "code": _c, "name": _n, "group": _s,
        "price": round(_p * (0.9 + random.random() * 0.2), 2),
        "change": round(random.uniform(-3.5, 4.2), 2),
        "change_amount": round(random.uniform(-5, 6), 2),
        "net_amount": round(random.uniform(-2e8, 2.2e8), 2),
        "add_time": (TODAY - timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d %H:%M"),
    })

bt_seq = 0
backtest_tasks = []


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(title="量化投研 Mock API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ===================== 自选股 =====================
@app.get("/api/v1/favorite/list")
def favorite_list():
    return ok(favorites)


@app.post("/api/v1/favorite/add")
def favorite_add(code: str = Query(""), name: str = Query("")):
    global _FAV_ID
    code = (code or "").strip()
    if not code:
        return wrap(None, "代码不能为空", 400, False)
    if any(f["code"] == code for f in favorites):
        return wrap(None, "已在自选股中", 400, False)
    _FAV_ID += 1
    nm, sec, _ = STOCK_MAP.get(code, (name or code, "其他", 30.0))
    favorites.append({
        "id": _FAV_ID, "code": code, "name": nm, "group": sec,
        "price": round(random.uniform(10, 200), 2),
        "change": round(random.uniform(-3, 4), 2),
        "change_amount": round(random.uniform(-5, 5), 2),
        "net_amount": round(random.uniform(-1e8, 1.2e8), 2),
        "add_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return ok({"id": _FAV_ID, "code": code, "name": nm})


@app.delete("/api/v1/favorite/delete")
def favorite_delete(fav_id: int = Query(0)):
    global favorites
    favorites = [f for f in favorites if f["id"] != fav_id]
    return ok({"deleted": fav_id})


# ===================== 行情 =====================
@app.get("/api/v1/stock/info")
def stock_info(code: str = Query("")):
    nm, sec, base = STOCK_MAP.get(code, (code or "未知", "其他", 30.0))
    price = round(base * (0.9 + random.random() * 0.2), 2)
    chg = round(random.uniform(-3.5, 4.2), 2)
    pre = price / (1 + chg / 100)
    return ok({
        "code": code, "name": nm, "sector": sec,
        "price": price, "pre_close": round(pre, 2),
        "open": round(pre * (1 + random.uniform(-0.01, 0.01)), 2),
        "high": round(price * 1.02, 2), "low": round(pre * 0.98, 2),
        "change": chg, "change_amount": round(price - pre, 2),
        "volume": random.randint(5_000_00, 2_000_000),
        "turnover": round(random.uniform(0.5, 6), 2),
        "amplitude": round(random.uniform(1, 5), 2),
        "pe_ratio": round(random.uniform(8, 45), 2),
        "pb_ratio": round(random.uniform(1, 9), 2),
        "market_cap": round(random.uniform(500, 20000), 2),
        "circ_market_cap": round(random.uniform(400, 18000), 2),
    })


@app.get("/api/v1/stock/kline")
def stock_kline(code: str = Query(""), start_date: str = Query(""),
                end_date: str = Query(""), use_cache: bool = Query(True)):
    return ok(gen_kline(code or "600519"))


# ===================== 资金 =====================
@app.get("/api/v1/capital/daily")
def capital_daily(code: str = Query(""), start_date: str = Query(""),
                  end_date: str = Query(""), accumulate_days: int = Query(0),
                  use_cache: bool = Query(True)):
    return ok(gen_capital(code or "600519", days=60))


# ===================== 资讯 =====================
@app.get("/api/v1/news/stock")
def news_stock(code: str = Query(""), start_date: str = Query(""),
               end_date: str = Query(""), stat: bool = Query(True)):
    return ok(gen_news(code or "600519"))


@app.get("/api/v1/news/industry")
def news_industry(industry: str = Query(""), start_date: str = Query(""),
                  end_date: str = Query(""), stat: bool = Query(True)):
    return ok(gen_news(industry or "半导体"))


# ===================== LLM =====================
@app.get("/api/v1/llm/health")
def llm_health():
    return ok({"doubao": True, "deepseek": True})


@app.post("/api/v1/llm/chat")
async def llm_chat(request: Request):
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    model = body.get("model_type") or "deepseek"
    content = (
        f"## 智能分析结论\n\n"
        f"针对您的问题：**{prompt or '（未提供具体问题）'}**，结合量化模型与产业链逻辑，得出以下研判：\n\n"
        f"1. **基本面**：当前样本池盈利质量分化，关注高景气赛道中具备成本传导能力的龙头。\n"
        f"2. **资金面**：近 20 日主力资金呈现结构性流入，超大单偏好中下游制造环节。\n"
        f"3. **风险点**：估值分位偏高叠加海外扰动，需警惕回撤；建议分批布局、控制仓位。\n"
        f"4. **操作建议**：以均线系统(MA20)作为趋势确认信号，配合 BOLL 通道做区间管理。\n\n"
        f"> 本结论由量化投研 AI 工作台生成，仅供研究参考，不构成投资建议。"
    )
    return ok({"content": content, "model_name": model, "tokens": len(content)})


# ===================== 回测 =====================
@app.post("/api/v1/backtest/run")
async def backtest_run(request: Request):
    global bt_seq
    body = await request.json()
    code = body.get("stock_code") or "600519"
    strat = body.get("strategy_name") or "均线交叉"
    sd = body.get("start_date") or "2025-01-01"
    ed = body.get("end_date") or "2026-07-31"
    bt_seq += 1
    res = gen_backtest_result(code, sd, ed, strat)
    res["id"] = bt_seq
    res["task_id"] = f"BT{bt_seq:04d}"
    backtest_tasks.insert(0, res)
    return ok({"task_id": res["task_id"]})


@app.get("/api/v1/backtest/task/list")
def backtest_list(code: str = Query("")):
    tasks = backtest_tasks
    if code:
        tasks = [t for t in tasks if t["stock_code"] == code]
    return ok(tasks)


# ===================== 产业链图谱 (graph) =====================
@app.get("/api/v1/graph/data/{chain_name}")
def graph_data(chain_name: str):
    return ok(gen_chain_graph(chain_name))


@app.get("/api/v1/graph/events")
def graph_events():
    events = [
        {"event_id": "evt_1", "title": "美联储降息预期升温", "category": "macro",
         "direction": "positive", "strength": 6},
        {"event_id": "evt_2", "title": "原材料价格大幅上涨", "category": "cost",
         "direction": "negative", "strength": 7},
        {"event_id": "evt_3", "title": "行业补贴政策落地", "category": "policy",
         "direction": "positive", "strength": 5},
        {"event_id": "evt_4", "title": "海外技术封锁升级", "category": "geo",
         "direction": "negative", "strength": 8},
    ]
    return ok(events)


@app.post("/api/v1/graph/impact/{chain_name}")
async def graph_impact(chain_name: str, request: Request):
    body = await request.json()
    return ok({"ok": True, "title": body.get("title"), "chain": chain_name})


@app.get("/api/v1/graph/snapshot/{chain_name}")
def graph_snapshot(chain_name: str):
    return ok({"json": json.dumps(gen_chain_graph(chain_name), ensure_ascii=False)})


# ===================== 传导推演 (expert) =====================
@app.post("/api/v1/expert/chain/sim")
async def expert_chain_sim(request: Request):
    """注意：IndustryChainPanel 用裸 axios 调用，直接读取响应顶层字段，故不包装。"""
    body = await request.json()
    return gen_chain_sim(body.get("eventKey", ""), body.get("layers", []) or [])


@app.get("/api/v1/expert/overview")
def expert_overview():
    return ok({
        "macro": {"cpi": 1.8, "ppi": -1.2, "gdp_growth": 5.0, "policy_rate": 1.5},
        "industries": [
            {"name": "半导体", "score": 82, "trend": "up"},
            {"name": "新能源", "score": 75, "trend": "up"},
            {"name": "白酒", "score": 60, "trend": "flat"},
            {"name": "银行", "score": 55, "trend": "down"},
        ],
        "stocks": [
            {"code": "688981", "name": "中芯国际", "score": 84, "signal": "买入"},
            {"code": "300750", "name": "宁德时代", "score": 80, "signal": "增持"},
            {"code": "600519", "name": "贵州茅台", "score": 70, "signal": "持有"},
        ],
        "content": "当前市场结构性机会集中在科技成长与高端制造，建议关注具备国产替代逻辑的细分龙头。",
    })


# ===================== 产业链台账 / 路径 =====================
LEDGER = [
    {"code": "801080", "l1_name": "电子", "l2_name": "半导体", "l3_name": "集成电路封测", "leaders": "长电科技,通富微电,华天科技", "factors": "晶圆代工产能,封测订单,国产替代"},
    {"code": "801081", "l1_name": "电子", "l2_name": "半导体", "l3_name": "集成电路设计", "leaders": "韦尔股份,兆易创新,卓胜微", "factors": "下游需求,库存周期,国产替代进度"},
    {"code": "801082", "l1_name": "电子", "l2_name": "半导体", "l3_name": "半导体设备", "leaders": "北方华创,中微公司,拓荆科技", "factors": "晶圆厂资本开支,国产化率"},
    {"code": "801120", "l1_name": "食品饮料", "l2_name": "白酒", "l3_name": "白酒", "leaders": "贵州茅台,五粮液,泸州老窖", "factors": "批价,库存,消费场景"},
    {"code": "801730", "l1_name": "电力设备", "l2_name": "光伏设备", "l3_name": "硅片", "leaders": "隆基绿能,TCL中环", "factors": "硅料价格,装机需求"},
    {"code": "801740", "l1_name": "电力设备", "l2_name": "电池", "l3_name": "锂电池", "leaders": "宁德时代,比亚迪,亿纬锂能", "factors": "新能源车销量,碳酸锂价格"},
    {"code": "801750", "l1_name": "机械设备", "l2_name": "通用设备", "l3_name": "机器人", "leaders": "埃斯顿,汇川技术,绿的谐波", "factors": "工业自动化,核心部件国产化"},
    {"code": "801780", "l1_name": "银行", "l2_name": "银行", "l3_name": "国有大型银行", "leaders": "工商银行,建设银行", "factors": "信贷投放,净息差"},
    {"code": "801790", "l1_name": "非银金融", "l2_name": "证券", "l3_name": "证券", "leaders": "中信证券,东方财富", "factors": "成交量,两融余额,市场情绪"},
    {"code": "801030", "l1_name": "化工", "l2_name": "化学原料", "l3_name": "纯碱", "leaders": "远兴能源,中盐化工", "factors": "光伏玻璃需求,出口"},
    {"code": "801710", "l1_name": "建筑材料", "l2_name": "水泥", "l3_name": "水泥制造", "leaders": "海螺水泥,华新水泥", "factors": "基建投资,地产需求"},
    {"code": "801050", "l1_name": "有色金属", "l2_name": "工业金属", "l3_name": "铜", "leaders": "紫金矿业,江西铜业", "factors": "全球需求,美元指数"},
]


@app.get("/api/v1/chain/list")
def chain_list(l1: str = Query("")):
    data = LEDGER
    if l1:
        data = [r for r in LEDGER if r["l1_name"] == l1]
    return ok(data)


@app.get("/api/v1/chain/path/{code}")
def chain_path(code: str):
    rec = next((r for r in LEDGER if r["code"] == code), LEDGER[0])
    path = [
        {"level": 1, "name": rec["l1_name"], "type": "L1"},
        {"level": 2, "name": rec["l2_name"], "type": "L2"},
        {"level": 3, "name": rec["l3_name"], "type": "L3"},
        {"level": 4, "name": rec["leaders"].split(",")[0], "type": "龙头公司"},
    ]
    return ok({"code": code, "path": path})


@app.get("/api/v1/chain/{chain_id}/graph")
def chain_graph(chain_id: str):
    return ok(gen_chain_graph(chain_id))


# ===================== 仿真路径计算 (无 v1 前缀) =====================
@app.post("/api/simulation/calcPath")
async def simulation_calc_path(request: Request):
    body = await request.json()
    root = body.get("rootNodeId", 1)
    max_level = body.get("maxLevel", 5)
    path = []
    for lvl in range(1, max_level + 1):
        path.append({
            "target_id": root + lvl,
            "level": lvl,
            "strength": round(random.uniform(0.1, 0.95), 2),
            "coeff": round(random.uniform(0.05, 0.9), 2),
        })
    return ok(path)


# ===================== 全球宏观资金 =====================
COUNTRIES = [
    {"id": "USA", "name": "美国", "riskScore": 72, "vulnerability": 68,
     "indicators": {"policy_rate": 4.5, "cpi": 3.1, "gdp_growth": 2.1, "debt_gdp": 123, "cds": 32, "fx_pressure": 45}},
    {"id": "CN", "name": "中国", "riskScore": 38, "vulnerability": 35,
     "indicators": {"policy_rate": 1.5, "cpi": 1.8, "gdp_growth": 5.0, "debt_gdp": 82, "cds": 48, "fx_pressure": 30}},
    {"id": "JP", "name": "日本", "riskScore": 55, "vulnerability": 60,
     "indicators": {"policy_rate": 0.25, "cpi": 2.6, "gdp_growth": 1.0, "debt_gdp": 255, "cds": 22, "fx_pressure": 70}},
    {"id": "DE", "name": "德国", "riskScore": 49, "vulnerability": 52,
     "indicators": {"policy_rate": 3.75, "cpi": 2.4, "gdp_growth": 0.8, "debt_gdp": 64, "cds": 18, "fx_pressure": 40}},
    {"id": "IN", "name": "印度", "riskScore": 44, "vulnerability": 48,
     "indicators": {"policy_rate": 6.5, "cpi": 5.2, "gdp_growth": 6.8, "debt_gdp": 81, "cds": 75, "fx_pressure": 38}},
    {"id": "GB", "name": "英国", "riskScore": 52, "vulnerability": 55,
     "indicators": {"policy_rate": 5.0, "cpi": 3.4, "gdp_growth": 1.2, "debt_gdp": 101, "cds": 25, "fx_pressure": 50}},
    {"id": "FR", "name": "法国", "riskScore": 50, "vulnerability": 54,
     "indicators": {"policy_rate": 3.75, "cpi": 2.5, "gdp_growth": 1.0, "debt_gdp": 112, "cds": 28, "fx_pressure": 42}},
    {"id": "BR", "name": "巴西", "riskScore": 62, "vulnerability": 66,
     "indicators": {"policy_rate": 10.5, "cpi": 4.6, "gdp_growth": 2.2, "debt_gdp": 88, "cds": 120, "fx_pressure": 72}},
    {"id": "KR", "name": "韩国", "riskScore": 47, "vulnerability": 50,
     "indicators": {"policy_rate": 3.5, "cpi": 2.8, "gdp_growth": 2.4, "debt_gdp": 54, "cds": 35, "fx_pressure": 46}},
    {"id": "RU", "name": "俄罗斯", "riskScore": 78, "vulnerability": 82,
     "indicators": {"policy_rate": 16.0, "cpi": 7.5, "gdp_growth": 1.5, "debt_gdp": 19, "cds": 210, "fx_pressure": 88}},
]


@app.get("/api/v1/macro/countries")
def macro_countries():
    return ok(COUNTRIES)


@app.get("/api/v1/macro/country/{country_id}")
def macro_country(country_id: str):
    c = next((x for x in COUNTRIES if x["id"] == country_id), COUNTRIES[0])
    return ok(c)


@app.get("/api/v1/macro/timeseries")
def macro_timeseries(country_id: str = Query("CN"), indicator: str = Query("policy_rate"),
                     start_date: str = Query(""), end_date: str = Query("")):
    days = trading_days(60)
    base = {"policy_rate": 1.5, "cpi": 1.8, "gdp_growth": 5.0, "debt_gdp": 82,
            "cds": 48, "fx_pressure": 30}.get(indicator, 50)
    data = [{"date": d.strftime("%Y-%m-%d"),
             "value": round(base + random.uniform(-base * 0.1, base * 0.1), 2)} for d in days]
    return ok({"country_id": country_id, "indicator": indicator, "data": data})


@app.get("/api/v1/macro/capital_flow")
def macro_capital_flow(period: str = Query("")):
    data = [{"country": c["name"], "inflow": round(random.uniform(50, 500), 1),
             "outflow": round(random.uniform(50, 500), 1), "net": round(random.uniform(-200, 300), 1)}
            for c in COUNTRIES]
    return ok(data)


@app.get("/api/v1/macro/rate_compare")
def macro_rate_compare():
    return ok([{"country": c["name"], "rate": c["indicators"]["policy_rate"]} for c in COUNTRIES])


@app.get("/api/v1/macro/trade_balance")
def macro_trade_balance():
    return ok([{"country": c["name"], "export": round(random.uniform(200, 2000), 1),
                "import": round(random.uniform(200, 2000), 1),
                "balance": round(random.uniform(-800, 800), 1)} for c in COUNTRIES])


@app.get("/api/v1/macro/sim/events")
def macro_sim_events():
    events = [
        {"event_id": "m1", "title": "美元流动性收紧", "direction": "negative", "strength": 7},
        {"event_id": "m2", "title": "新兴市场资本回流", "direction": "positive", "strength": 5},
        {"event_id": "m3", "title": "大宗商品价格冲击", "direction": "negative", "strength": 6},
        {"event_id": "m4", "title": "地缘风险缓和", "direction": "positive", "strength": 4},
        {"event_id": "m5", "title": "主权债务压力", "direction": "negative", "strength": 8},
        {"event_id": "m6", "title": "宽松货币政策", "direction": "positive", "strength": 5},
    ]
    return ok(events)


@app.get("/api/v1/macro/sim/graph")
def macro_sim_graph():
    nodes = [{"id": c["id"], "name": c["name"], "riskScore": c["riskScore"]} for c in COUNTRIES]
    edges = []
    for i, a in enumerate(COUNTRIES):
        for b in COUNTRIES[i + 1:]:
            if random.random() < 0.25:
                edges.append({"source": a["id"], "target": b["id"]})
    return ok({"nodes": nodes, "edges": edges})


@app.post("/api/v1/macro/sim/calcPath")
async def macro_sim_calcpatch(request: Request):
    body = await request.json()
    root = body.get("rootNodeId", "USA")
    max_level = body.get("maxLevel", 5)
    path = []
    for lvl in range(1, max_level + 1):
        path.append({"target_id": f"{root}_L{lvl}", "level": lvl,
                     "strength": round(random.uniform(0.1, 0.95), 2)})
    return ok(path)


@app.post("/api/v1/macro/ai_report")
async def macro_ai_report(request: Request):
    body = await request.json()
    cid = body.get("country_id", "CN")
    c = next((x for x in COUNTRIES if x["id"] == cid), COUNTRIES[0])
    report = (
        f"## {c['name']} 宏观研判报告\n\n"
        f"- **脆弱性得分**：{c['riskScore']}（{'高' if c['riskScore']>60 else '中' if c['riskScore']>40 else '低'}风险）\n"
        f"- **政策利率**：{c['indicators']['policy_rate']}%，通胀 {c['indicators']['cpi']}%\n"
        f"- **增长动能**：GDP 增速 {c['indicators']['gdp_growth']}%，债务/GDP {c['indicators']['debt_gdp']}%\n"
        f"- **研判**：在当前全球资本流动格局下，建议{'保持谨慎，关注外溢风险' if c['riskScore']>60 else '把握结构性配置机会'}。"
    )
    return ok({"content": report})


# ---------------------------------------------------------------------------
# 前端静态文件托管 (生产模式) + SPA 回退
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


def _serve_spa(path: str):
    # 优先返回真实文件
    file_path = os.path.join(DIST_DIR, path.lstrip("/"))
    if path and os.path.isfile(file_path):
        return FileResponse(file_path)
    # SPA 回退
    index = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return JSONResponse({"detail": "前端未构建，请先执行 npm run build"}, status_code=404)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    return _serve_spa(full_path)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3100)
    args = parser.parse_args()

    if not os.path.isdir(DIST_DIR):
        print(f"[WARN] 未找到前端构建目录: {DIST_DIR}，页面将无法加载。请先 `npm run build`。")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
