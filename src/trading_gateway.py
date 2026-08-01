# -*- coding: utf-8 -*-
"""
========================================================
实盘交易网关 (P1-②, 对标 ai-hedge-fund 的 Broker 层)

可插拔 Broker 适配设计：
  - PaperTradingBroker : 模拟撮合 + 本地账本(默认，离线可测、零风险)
  - LiveBroker         : 实盘桩，仅当环境变量配置凭证后才可用；否则任何下单均拒绝
                         （TRADING_BROKER / TRADING_API_KEY / TRADING_API_SECRET）
TradingGateway 按 TRADING_MODE(paper|live, 默认 paper) 选择 broker，
并负责把「人格化 Agent 决策」翻译为可执行订单建议(不直接自动下单，需二次确认)。

安全约定：实盘默认关闭，任何实盘操作都需显式配置凭证；决策→下单之间必须人工确认。
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "trading"
_LEDGER_PATH = _DATA_DIR / "paper_ledger.json"

# 风险等级 → 是否允许开仓的映射
_RISK_ALLOW_OPEN = {
    "low": True,
    "medium": True,
    "high": False,
    "extreme": False,
}


@dataclass
class Order:
    order_id: str
    symbol: str
    side: str            # buy / sell
    quantity: float
    price: Optional[float]
    status: str = "submitted"   # submitted / filled / rejected / cancelled
    filled_price: Optional[float] = None
    filled_qty: float = 0.0
    reason: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status,
            "filled_price": self.filled_price,
            "filled_qty": self.filled_qty,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_cost: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
        }


class BrokerAdapter(ABC):
    """Broker 适配接口。"""

    name = "abstract"

    @abstractmethod
    def place_order(self, symbol: str, side: str, quantity: float,
                    price: Optional[float]) -> Order:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def get_orders(self) -> List[Order]:
        ...

    @abstractmethod
    def get_positions(self) -> List[Position]:
        ...

    @abstractmethod
    def get_account(self) -> Dict[str, Any]:
        ...

    def price_fn(self, symbol: str) -> Optional[float]:
        """可选的实时价获取(在线优先)。默认返回 None(需调用方显式给价)。"""
        return None


class PaperTradingBroker(BrokerAdapter):
    """模拟撮合经纪商：本地 JSON 账本，T+0 即时按给定价成交(无滑点/手续费简化)。"""

    name = "paper"

    def __init__(self, cash: float = 1_000_000.0, ledger_path: Path = _LEDGER_PATH,
                 price_fn: Optional[Callable[[str], Optional[float]]] = None):
        self._cash = cash
        self._positions: Dict[str, Position] = {}
        self._orders: List[Order] = []
        self._ledger_path = ledger_path
        self._price_fn = price_fn
        self._realized_pnl = 0.0
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            if self._ledger_path.exists():
                data = json.loads(self._ledger_path.read_text(encoding="utf-8"))
                self._cash = float(data.get("cash", self._cash))
                self._realized_pnl = float(data.get("realized_pnl", 0.0))
                self._positions = {
                    s: Position(**p) for s, p in (data.get("positions") or {}).items()
                }
                self._orders = [Order(**o) for o in (data.get("orders") or [])]
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取模拟账本失败，使用空账本: %s", exc)

    def _save(self) -> None:
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "cash": self._cash,
                "realized_pnl": self._realized_pnl,
                "positions": {s: p.to_dict() for s, p in self._positions.items()},
                "orders": [o.to_dict() for o in self._orders],
            }
            self._ledger_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("写入模拟账本失败: %s", exc)

    # ---------- 接口实现 ----------
    def place_order(self, symbol: str, side: str, quantity: float,
                    price: Optional[float]) -> Order:
        side = (side or "").lower()
        if side not in ("buy", "sell"):
            return self._reject(symbol, side, quantity, price, "side 必须是 buy/sell")
        if quantity <= 0:
            return self._reject(symbol, side, quantity, price, "数量必须为正")
        # 取价：显式价优先，否则尝试 price_fn
        fill_price = price
        if fill_price is None:
            fill_price = self.price_fn(symbol) if self._price_fn else None
        if fill_price is None or fill_price <= 0:
            return self._reject(symbol, side, quantity, price, "缺少成交价(需显式 price 或在线行情)")

        if side == "buy":
            cost = quantity * fill_price
            if cost > self._cash + 1e-9:
                return self._reject(symbol, side, quantity, price, "现金不足")
            pos = self._positions.get(symbol)
            if pos is None:
                self._positions[symbol] = Position(symbol, quantity, fill_price)
            else:
                new_qty = pos.quantity + quantity
                pos.avg_cost = (pos.avg_cost * pos.quantity + fill_price * quantity) / new_qty
                pos.quantity = new_qty
            self._cash -= cost
        else:  # sell
            pos = self._positions.get(symbol)
            if pos is None or pos.quantity + 1e-9 < quantity:
                return self._reject(symbol, side, quantity, price, "持仓不足")
            # 实现盈亏
            self._realized_pnl += (fill_price - pos.avg_cost) * quantity
            pos.quantity -= quantity
            if pos.quantity <= 1e-9:
                del self._positions[symbol]
            self._cash += quantity * fill_price

        order = Order(
            order_id=uuid.uuid4().hex[:12], symbol=symbol, side=side,
            quantity=quantity, price=price, status="filled",
            filled_price=fill_price, filled_qty=quantity,
            reason="paper fill",
        )
        self._orders.append(order)
        self._save()
        return order

    def cancel_order(self, order_id: str) -> bool:
        for o in self._orders:
            if o.order_id == order_id and o.status == "submitted":
                o.status = "cancelled"
                o.updated_at = time.time()
                self._save()
                return True
        return False

    def get_orders(self) -> List[Order]:
        return list(self._orders)

    def get_positions(self) -> List[Position]:
        return list(self._positions.values())

    def get_account(self) -> Dict[str, Any]:
        return {
            "broker": self.name,
            "cash": round(self._cash, 2),
            "market_value": 0.0,  # 仅以成本计的基础市值(无实时价)
            "realized_pnl": round(self._realized_pnl, 2),
            "position_count": len(self._positions),
        }

    def _reject(self, symbol, side, quantity, price, reason) -> Order:
        order = Order(
            order_id=uuid.uuid4().hex[:12], symbol=symbol, side=side,
            quantity=quantity, price=price, status="rejected", reason=reason,
        )
        self._orders.append(order)
        self._save()
        return order

    def reset(self, confirm: bool = False) -> None:
        """重置模拟账本(测试用)。需 confirm=True。"""
        if not confirm:
            raise ValueError("reset 需 confirm=True")
        self._cash = 1_000_000.0
        self._positions = {}
        self._orders = []
        self._realized_pnl = 0.0
        self._save()


class LiveBroker(BrokerAdapter):
    """实盘经纪商桩：仅当环境变量配置凭证后才可用。未配置则拒绝一切操作。

    真实接入时，在 _connect() 中实现对应券商 SDK 的 orders.submit / positions.get 等，
    并保持与 BrokerAdapter 接口一致即可(可插拔替换)。
    """

    name = "live"

    def __init__(self):
        self._broker = os.getenv("TRADING_BROKER", "")
        self._api_key = os.getenv("TRADING_API_KEY", "")
        self._api_secret = os.getenv("TRADING_API_SECRET", "")
        self._configured = bool(self._broker and self._api_key and self._api_secret)

    def _guard(self) -> None:
        if not self._configured:
            raise RuntimeError(
                "实盘交易未配置：请设置环境变量 TRADING_BROKER / TRADING_API_KEY / "
                "TRADING_API_SECRET 并在安全环境中启动。当前网关模式为 live 但未提供凭证。"
            )

    def place_order(self, symbol, side, quantity, price=None) -> Order:
        self._guard()
        # TODO: 真实券商下单(此处仅占位)。接入时替换为 SDK 调用并将返回映射为 Order。
        raise NotImplementedError("LiveBroker 实盘下单尚未接入具体券商 SDK")

    def cancel_order(self, order_id) -> bool:
        self._guard()
        raise NotImplementedError("LiveBroker 撤单尚未接入")

    def get_orders(self) -> List[Order]:
        self._guard()
        raise NotImplementedError("LiveBroker 查单尚未接入")

    def get_positions(self) -> List[Position]:
        self._guard()
        raise NotImplementedError("LiveBroker 持仓查询尚未接入")

    def get_account(self) -> Dict[str, Any]:
        self._guard()
        raise NotImplementedError("LiveBroker 账户查询尚未接入")

    def status(self) -> Dict[str, Any]:
        return {
            "broker": self.name,
            "configured": self._configured,
            "broker_tag": self._broker or None,
        }


class TradingGateway:
    """交易网关：选择 broker + 决策→订单翻译 + 统一指令入口。"""

    def __init__(self):
        mode = (os.getenv("TRADING_MODE", "paper") or "paper").lower()
        self._live = LiveBroker()
        if mode == "live" and self._live._configured:
            self._broker: BrokerAdapter = self._live
        else:
            self._broker = PaperTradingBroker()
        self.mode = "live" if self._broker is self._live else "paper"

    # ---------- 统一指令 ----------
    def place_order(self, symbol, side, quantity, price=None) -> Order:
        return self._broker.place_order(symbol, side, quantity, price)

    def cancel_order(self, order_id) -> bool:
        return self._broker.cancel_order(order_id)

    def get_orders(self) -> List[Order]:
        return self._broker.get_orders()

    def get_positions(self) -> List[Position]:
        return self._broker.get_positions()

    def get_account(self) -> Dict[str, Any]:
        return self._broker.get_account()

    def status(self) -> Dict[str, Any]:
        if self._broker is self._live:
            st = self._live.status()
            st["mode"] = "live"
            return st
        return {"mode": "paper", "broker": "paper", "configured": True}

    # ---------- 决策 → 订单翻译 ----------
    def decide(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """把人格化 Agent 决策翻译为订单建议(不直接下单)。

        decision: {symbol, consensus(bullish/bearish/neutral/divergent),
                   consensus_score(0-100), risk_level(low/medium/high/extreme),
                   current_qty?(可选, 现持仓)}
        """
        symbol = str(decision.get("symbol") or "").strip()
        consensus = str(decision.get("consensus") or "neutral").lower()
        score = float(decision.get("consensus_score") or 50.0)
        risk_level = str(decision.get("risk_level") or "medium").lower()
        current_qty = float(decision.get("current_qty") or 0.0)

        if not symbol:
            return {"action": "hold", "reason": "缺少 symbol", "order": None}

        allow_open = _RISK_ALLOW_OPEN.get(risk_level, True)
        if not allow_open:
            return {
                "action": "hold",
                "reason": f"风险等级【{risk_level}】过高，禁止开仓/加仓(仅允许减仓以控风险)",
                "order": None,
                "can_reduce": current_qty > 0,
            }

        if consensus == "bullish" and score >= 55:
            # 保守建仓：单次不超过账户现金的 10%(由调用方结合价格换算手数)
            return {
                "action": "buy",
                "reason": f"共识看多(评分{score:.1f})且风险可控，建议分批建仓",
                "order": {"symbol": symbol, "side": "buy", "quantity": None,
                          "note": "按风险预算换算手数后通过 /trading/orders 下单"},
                "can_reduce": False,
            }
        if consensus == "bearish" and score <= 45 and current_qty > 0:
            return {
                "action": "reduce",
                "reason": f"共识看空(评分{score:.1f})，建议减仓控风险",
                "order": {"symbol": symbol, "side": "sell", "quantity": None,
                          "note": "建议减仓 1/3~1/2，具体经 /trading/orders 执行"},
                "can_reduce": True,
            }
        return {
            "action": "hold",
            "reason": f"共识【{consensus}】评分{score:.1f}，信号不足，维持观望",
            "order": None,
            "can_reduce": current_qty > 0,
        }


# 单例
_GATEWAY: Optional[TradingGateway] = None


def get_gateway() -> TradingGateway:
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = TradingGateway()
    return _GATEWAY
