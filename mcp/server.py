# -*- coding: utf-8 -*-
"""标准 MCP server over stdio（JSON-RPC 2.0），零外部依赖。

外部 Agent（Claude Desktop / Cursor / 自研 Agent）通过 stdio 启动本进程即可接入：
    python -m mcp.server
内部通过本系统 REST API（http://127.0.0.1:8000/api/v1）桥接，复用全部已验证逻辑。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from mcp.tools_spec import TOOLS

BASE = "http://127.0.0.1:8000/api/v1"


def _api(method: str, path: str, params: dict = None, json_body: dict = None):
    url = BASE + path
    if params:
        q = {k: v for k, v in params.items() if v is not None}
        if q:
            url += "?" + urllib.parse.urlencode(q, doseq=True)
    data = json.dumps(json_body).encode() if json_body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode()[:800]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _h_list_companies(a):
    return _api("GET", "/companies", {
        "q": a.get("query"), "source": a.get("source"),
        "page": a.get("page"), "page_size": a.get("page_size"),
    })


def _h_get_company(a):
    return _api("GET", f"/companies/{a['code']}")


def _h_list_chains(a):
    return _api("GET", "/industry-chains")


def _h_get_chain(a):
    return _api("GET", f"/industry-chains/{a['chain_id']}")


def _h_fm_results(a):
    return _api("GET", "/factor-mining/results", {"active_only": a.get("active_only")})


def _h_fm_run(a):
    return _api("POST", "/factor-mining/run", {
        "code": a.get("code", "600519"),
        "max_gen": a.get("max_gen", 4),
        "top_k": a.get("top_k", 5),
        "online": a.get("online", False),
    })


def _h_backtest(a):
    return _api("POST", "/backtest", json_body={"code": a["code"]})


def _h_chat(a):
    return _api("POST", "/agent/chat", json_body={"message": a["message"]})


def _h_trading_status(a):
    return _api("GET", "/trading/status")


def _h_place_trade(a):
    return _api("POST", "/trading/orders", json_body={
        "symbol": a.get("symbol"),
        "side": a.get("side"),
        "quantity": a.get("quantity"),
        "price": a.get("price"),
    })


def _h_optimize(a):
    return _api("POST", "/portfolio/optimize", json_body={
        "symbols": a.get("symbols"),
        "objective": a.get("objective", "max_sharpe"),
        "risk_parity_mode": a.get("risk_parity_mode", False),
        "online": a.get("online", False),
    })


def _h_attr(a):
    return _api("POST", "/portfolio/risk-attribution", json_body={
        "symbols": a.get("symbols"),
        "weights": a.get("weights"),
        "online": a.get("online", False),
    })


def _h_strategy_bt(a):
    return _api("POST", "/strategy/run", json_body={
        "code": a.get("code"),
        "strategy": a.get("strategy", "ma_cross"),
        "engine": a.get("engine", "vector"),
        "online": a.get("online", False),
        "n": a.get("n", 250),
    })


def _h_graph_rl(a):
    return _api("POST", "/graph-rl/run", json_body={
        "symbols": a.get("symbols"),
        "online": a.get("online", False),
        "n": a.get("n", 250),
        "lookback": a.get("lookback", 20),
    })


def _h_export_report(a):
    return _api("POST", "/export/portfolio-report", json_body={
        "symbols": a.get("symbols"),
        "objective": a.get("objective", "max_sharpe"),
        "risk_parity_mode": a.get("risk_parity_mode", False),
        "online": a.get("online", False),
    })


def _h_community_post(a):
    return _api("POST", "/community/posts", json_body={
        "author": a.get("author", "匿名"),
        "title": a.get("title"),
        "body": a.get("body", ""),
        "tags": a.get("tags"),
    })


def _h_community_list(a):
    return _api("GET", "/community/posts", {
        "tag": a.get("tag"), "sort": a.get("sort", "new"),
        "limit": a.get("limit", 50), "offset": a.get("offset", 0),
    })


def _h_community_like(a):
    return _api("POST", f"/community/posts/{a['post_id']}/like",
                params={"user_name": a.get("user_name")})


HANDLERS = {
    "list_companies": _h_list_companies,
    "get_company": _h_get_company,
    "list_industry_chains": _h_list_chains,
    "get_industry_chain": _h_get_chain,
    "get_factor_mining_results": _h_fm_results,
    "run_factor_mining": _h_fm_run,
    "run_backtest": _h_backtest,
    "agent_chat": _h_chat,
    "trading_status": _h_trading_status,
    "place_trade": _h_place_trade,
    "optimize_portfolio": _h_optimize,
    "portfolio_risk_attribution": _h_attr,
    "run_strategy_backtest": _h_strategy_bt,
    "run_graph_rl": _h_graph_rl,
    "export_portfolio_report": _h_export_report,
    "community_post": _h_community_post,
    "community_list": _h_community_list,
    "community_like": _h_community_like,
}


def main() -> None:
    """stdio JSON-RPC 主循环。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            print(json.dumps({
                "jsonrpc": "2.0", "id": mid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "dsa-mcp", "version": "1.0.0"},
                },
            }, ensure_ascii=False), flush=True)
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            print(json.dumps({
                "jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS},
            }, ensure_ascii=False), flush=True)
        elif method == "tools/call":
            name = msg.get("params", {}).get("name")
            args = msg.get("params", {}).get("arguments", {})
            h = HANDLERS.get(name)
            if h:
                try:
                    res = h(args)
                except Exception as e:  # noqa: BLE001
                    res = {"error": str(e)}
            else:
                res = {"error": f"unknown tool: {name}"}
            text = json.dumps(res, ensure_ascii=False)[:12000]
            print(json.dumps({
                "jsonrpc": "2.0", "id": mid,
                "result": {"content": [{"type": "text", "text": text}]},
            }, ensure_ascii=False), flush=True)
        elif mid is not None:
            print(json.dumps({
                "jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": "method not found"},
            }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
