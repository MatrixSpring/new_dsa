# -*- coding: utf-8 -*-
"""
========================================================
产业链传导推演 (P1-③ 深化)

在现有产业链图谱(nodes/edges/companies)基础上，新增「冲击传导」能力：
给定一个冲击事件(作用在某个环节节点、幅度、类型)，沿图谱边按 coeff/lag
向上下游(无向传染)传播，输出各环节与各公司的受影响程度，并给出链级汇总。

纯函数、无外部依赖、可离线运行；图谱来自 industry_chain 接口(内置沙盘 / xzsc)。
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _find_node(graph: Dict[str, Any], token: str) -> Optional[str]:
    """按节点 id 或 label 定位节点 id（支持精确/前缀/子串模糊匹配）。"""
    token = (token or "").strip()
    if not token:
        return None
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    # 1) 精确 id
    if token in nodes:
        return token
    # 2) 精确 label
    for nid, n in nodes.items():
        if n.get("label") == token:
            return nid
    # 3) 前缀匹配（label 以 token 开头）
    for nid, n in nodes.items():
        if (n.get("label") or "").startswith(token):
            return nid
    # 4) 子串匹配（token 为 label 子串，或 label 为 token 子串）
    for nid, n in nodes.items():
        lbl = n.get("label") or ""
        if token in lbl or lbl in token:
            return nid
    return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# 设计 §3.1 默认引擎参数（亦可被 dsa_global_params / 前端请求体覆盖）
_DEFAULT_MAX_DEPTH = 20                 # 最大递归深度
_DEFAULT_BIDIRECTIONAL_DECAY = 0.85     # 双向 / 多级传导逐跳衰减
_DEFAULT_BEARISH_DECAY = 0.7            # 利空情景额外衰减
_BEARISH_KINDS = {"negative", "bearish", "利空", "down", "负面"}


def _edge_coeff_lag(
    edge: Dict[str, Any],
    overrides: Dict[tuple, Dict[str, Any]],
    use_overrides: bool,
    cur: str,
    nb: str,
) -> tuple:
    """读取一条边的系数/滞后，应用覆盖表与 0~1 区间校验（设计 §3.1）。"""
    coeff = float(edge.get("coeff", 0.6) or 0.6)
    lag = float(edge.get("lag", 0) or 0)
    if use_overrides:
        ov = overrides.get((cur, nb))
        if ov:
            coeff = float(ov.get("coeff", coeff))
            lag = float(ov.get("lag", lag))
    return _clamp(coeff, 0.0, 1.0), max(0.0, lag)


def propagate_shock(
    graph: Dict[str, Any],
    shock: Dict[str, Any],
    opts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """沿图谱传播冲击，返回各环节/各公司影响与汇总。

    设计 §3.1 引擎规则（均可被 dsa_global_params / 前端请求体覆盖）：
      - max_depth            最大递归深度上限（默认 20）
      - bidirectional_decay  双向 / 多级传导逐跳衰减（默认 0.85）
      - bearish_decay        利空(kind=negative)情景额外衰减（默认 0.7）
      - use_overrides        是否应用 chain_edge_override 覆盖系数
      - overrides            预取的 {(source,target):{coeff,lag}}
      - factor_weights       多因子加权(宏观/政策/产业链/资金)，仅回显

    Args:
        graph: 产业链图谱(dict)，含 nodes/edges/companies
        shock: {node(环节 id 或名称), magnitude(相对冲击), kind(cost/demand/supply/.../negative)}
        opts:  可选引擎参数（见上）
    Returns:
        {shock_node, shock_label, magnitude, kind, params,
         node_impacts:[...], company_impacts:[...], summary:{...}}
    """
    opts = opts or {}
    max_depth = int(opts.get("max_depth", _DEFAULT_MAX_DEPTH))
    bidirectional_decay = float(opts.get("bidirectional_decay", _DEFAULT_BIDIRECTIONAL_DECAY))
    bearish_decay = float(opts.get("bearish_decay", _DEFAULT_BEARISH_DECAY))
    use_overrides = bool(opts.get("use_overrides", False))
    overrides = opts.get("overrides") or {}
    factor_weights = opts.get("factor_weights")

    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    if not nodes:
        return {"error": "图谱无节点", "node_impacts": [], "company_impacts": [],
                "summary": {"total_nodes": 0, "impacted": 0}}

    start = _find_node(graph, str(shock.get("node") or ""))
    if start is None:
        return {"error": f"未找到冲击环节: {shock.get('node')}",
                "node_impacts": [], "company_impacts": [],
                "summary": {"total_nodes": len(nodes), "impacted": 0}}

    mag = float(shock.get("magnitude", 0.0))
    kind = str(shock.get("kind") or "cost")
    # 利空情景额外衰减（设计 §3.1）
    if kind.lower() in _BEARISH_KINDS:
        mag = mag * bearish_decay

    # 无向邻接(保留边元数据用于系数/滞后)
    adj: Dict[str, List[tuple]] = {nid: [] for nid in nodes}
    for e in graph.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s in adj:
            adj[s].append((t, e))
        if t in adj:
            adj[t].append((s, e))

    # 深度受限 BFS 传播（设计 §3.1：最大递归深度、双向逐跳衰减、系数区间校验）
    impact: Dict[str, float] = {start: mag}
    q = deque([(start, 0)])
    while q:
        cur, d = q.popleft()
        if d >= max_depth:
            continue
        for nb, e in adj[cur]:
            coeff, lag = _edge_coeff_lag(e, overrides, use_overrides, cur, nb)
            decay = 1.0 / (1.0 + lag / 30.0)                 # 滞后越长，即时冲击越弱
            hops = d + 1
            bd_mult = bidirectional_decay ** max(0, hops - 1)  # 首跳不衰减，后续逐跳衰减
            child = impact[cur] * coeff * decay * bd_mult
            if nb not in impact:
                impact[nb] = child
                if abs(child) > 1e-4:
                    q.append((nb, d + 1))
            else:
                # 叠加（取影响更大者，避免过度放大）
                if abs(child) > abs(impact[nb]):
                    impact[nb] = child

    # 环节影响（排除冲击源自身）
    node_impacts: List[Dict[str, Any]] = []
    for nid, imp in impact.items():
        if nid == start or abs(imp) < 1e-4:
            continue
        n = nodes[nid]
        node_impacts.append({
            "node_id": nid,
            "label": n.get("label"),
            "stage": n.get("sub") or n.get("stage"),
            "layer": n.get("layer"),
            "impact": round(imp, 4),
            "impact_pct": round(imp * 100, 2),
            "direction": "positive" if imp > 0 else "negative",
        })
    node_impacts.sort(key=lambda x: -abs(x["impact"]))

    # 公司影响（挂在受影响节点上的公司）
    companies = graph.get("companies", {}) or {}
    comp_seen: Dict[str, Dict[str, Any]] = {}
    for nid, imp in impact.items():
        if abs(imp) < 1e-4:
            continue
        for c in companies.get(nid, []) or []:
            code = c.get("code") or c.get("name")
            if not code:
                continue
            rec = comp_seen.get(code)
            if rec is None:
                comp_seen[code] = {
                    "code": c.get("code"),
                    "name": c.get("name"),
                    "nodes": [nodes[nid].get("label")],
                    "impact": imp,
                }
            else:
                rec["nodes"].append(nodes[nid].get("label"))
                if abs(imp) > abs(rec["impact"]):
                    rec["impact"] = imp
    company_impacts = list(comp_seen.values())
    for c in company_impacts:
        c["impact_pct"] = round(c["impact"] * 100, 2)
        c["direction"] = "positive" if c["impact"] > 0 else "negative"
        c.pop("impact", None)
    company_impacts.sort(key=lambda x: -abs(x["impact_pct"]))

    impacted = len(node_impacts)
    avg = (sum(abs(x["impact"]) for x in node_impacts) / impacted) if impacted else 0.0
    max_abs = max((abs(x["impact"]) for x in node_impacts), default=0.0)

    summary = {
        "total_nodes": len(nodes),
        "impacted_nodes": impacted,
        "max_impact": round(max_abs, 4),
        "max_impact_pct": round(max_abs * 100, 2),
        "avg_abs_impact": round(avg, 4),
        "affected_companies": len(company_impacts),
        "params": {
            "max_depth": max_depth,
            "bidirectional_decay": round(bidirectional_decay, 4),
            "bearish_decay": round(bearish_decay, 4),
            "used_overrides": bool(use_overrides and overrides),
            "factor_weights": factor_weights,
        },
    }

    return {
        "shock_node": start,
        "shock_label": nodes[start].get("label"),
        "magnitude": mag,
        "magnitude_pct": round(mag * 100, 2),
        "kind": kind,
        "params": summary["params"],
        "node_impacts": node_impacts,
        "company_impacts": company_impacts,
        "summary": summary,
    }


def chain_exposure_from_holdings(
    holdings: List[Dict[str, Any]],
    chain_companies: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """把持仓(含股票代码与权重)映射到产业链，计算链级暴露与集中度。

    Args:
        holdings: [{code, weight}]  (weight 为 0-1 或 0-100，自动归一)
        chain_companies: {chain_id: [{code, name, ...}]}  —— 各产业链成分股
    Returns:
        {exposures:[{chain_id, name, weight, companies:[...]}], hhi, concentration_alert}
    """
    total_w = sum(float(h.get("weight") or 0) for h in holdings) or 1.0
    holding_map = {str(h.get("code")): float(h.get("weight") or 0) / total_w
                   for h in holdings if h.get("code")}

    exposures: List[Dict[str, Any]] = []
    for chain_id, comps in chain_companies.items():
        w = 0.0
        matched = []
        for c in comps:
            code = c.get("code")
            if code and code in holding_map:
                w += holding_map[code]
                matched.append({"code": code, "name": c.get("name"),
                                "weight": round(holding_map[code], 4)})
        if w > 1e-6:
            exposures.append({
                "chain_id": chain_id,
                "weight": round(w, 4),
                "weight_pct": round(w * 100, 2),
                "companies": matched,
            })
    exposures.sort(key=lambda x: -x["weight"])

    hhi = sum((e["weight"] ** 2) for e in exposures)
    top = exposures[0]["weight"] if exposures else 0.0
    return {
        "exposures": exposures,
        "chain_count": len(exposures),
        "hhi": round(hhi, 4),
        "top_chain_weight": round(top, 4),
        "top_chain_weight_pct": round(top * 100, 2),
        "concentration_alert": bool(top >= 0.35),
    }
