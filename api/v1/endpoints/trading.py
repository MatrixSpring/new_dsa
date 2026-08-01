# -*- coding: utf-8 -*-
"""实盘交易网关接口 (P1-②)。

统一入口：状态查询 / 下单 / 订单列表 / 持仓 / 账户 / 决策翻译。
默认 paper(模拟) 模式，零风险可离线测试；live 模式仅当配置凭证后启用。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from src.trading_gateway import Order, Position, get_gateway

logger = logging.getLogger(__name__)

router = APIRouter()


def _order_to_dict(o: Order) -> Dict[str, Any]:
    return o.to_dict()


def _pos_to_dict(p: Position) -> Dict[str, Any]:
    return p.to_dict()


@router.get("/status")
def gateway_status() -> Dict[str, Any]:
    """网关状态：当前模式 / broker / 是否配置实盘。"""
    return get_gateway().status()


@router.post("/orders")
def place_order(
    symbol: str = Body(..., description="6 位股票代码"),
    side: str = Body(..., description="buy / sell"),
    quantity: float = Body(..., description="数量(股)"),
    price: Optional[float] = Body(None, description="限价；不传则尝试在线行情(默认模拟模式需显式给价)"),
) -> Dict[str, Any]:
    """提交一笔订单(paper 模式模拟成交；live 模式需凭证)。"""
    order = get_gateway().place_order(symbol, side, quantity, price)
    return _order_to_dict(order)


@router.get("/orders")
def list_orders() -> Dict[str, Any]:
    """订单列表。"""
    return {"total": len(get_gateway().get_orders()),
            "items": [_order_to_dict(o) for o in get_gateway().get_orders()]}


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str) -> Dict[str, Any]:
    """撤单(仅对 submitted 状态有效，模拟模式即时成交故通常已 filled)。"""
    ok = get_gateway().cancel_order(order_id)
    return {"cancelled": 1 if ok else 0}


@router.get("/positions")
def list_positions() -> Dict[str, Any]:
    """当前持仓。"""
    positions = get_gateway().get_positions()
    return {"total": len(positions), "items": [_pos_to_dict(p) for p in positions]}


@router.get("/account")
def account_summary() -> Dict[str, Any]:
    """账户概览(现金/已实现盈亏/持仓数)。"""
    return get_gateway().get_account()


@router.post("/decide")
def decide(decision: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """把人格化 Agent 决策翻译为订单建议(不直接下单，需二次确认)。

    请求体: {symbol, consensus, consensus_score, risk_level, current_qty?}
    """
    return get_gateway().decide(decision)


@router.post("/execute-decision")
def execute_decision(
    symbol: str = Body(..., description="6 位股票代码"),
    consensus: str = Body(..., description="bullish/bearish/neutral/divergent"),
    consensus_score: float = Body(50.0, description="0-100"),
    risk_level: str = Body("medium", description="low/medium/high/extreme"),
    current_qty: float = Body(0.0, description="当前持仓(股)"),
    price: Optional[float] = Body(None, description="成交价(必填，模拟模式按此价撮合)"),
    max_notional: float = Body(100000.0, description="单笔最大金额预算(元)，用于换算建仓手数"),
) -> Dict[str, Any]:
    """按决策翻译并(在预算内)实际下单。仅当决策为 buy/reduce 且给出 price 时成交。

    安全：高风险等级强制 hold，不执行任何开仓。
    """
    gw = get_gateway()
    sug = gw.decide({
        "symbol": symbol, "consensus": consensus,
        "consensus_score": consensus_score, "risk_level": risk_level,
        "current_qty": current_qty,
    })
    action = sug.get("action")
    if action == "hold":
        return {"action": "hold", "executed": False, "reason": sug.get("reason"),
                "suggestion": sug}
    if price is None or price <= 0:
        return {"action": action, "executed": False,
                "reason": "缺少成交价 price，无法撮合(请先获取实时价)",
                "suggestion": sug}
    if action == "buy":
        qty = max(100, int(min(max_notional, gw.get_account().get("cash", 0)) // (price * 100)) * 100)
        if qty <= 0:
            return {"action": "buy", "executed": False,
                    "reason": "预算或现金不足，无法建仓", "suggestion": sug}
        order = gw.place_order(symbol, "buy", qty, price)
    else:  # reduce
        qty = max(100, int((current_qty * 0.34) // 100) * 100)
        if qty <= 0:
            return {"action": "reduce", "executed": False,
                    "reason": "可减仓数量不足", "suggestion": sug}
        order = gw.place_order(symbol, "sell", qty, price)
    return {"action": action, "executed": order.status == "filled",
            "order": _order_to_dict(order), "suggestion": sug}
