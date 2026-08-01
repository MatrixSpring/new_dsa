# -*- coding: utf-8 -*-
"""策略回测引擎 (P2-①, 对标 backtrader / 通达信公式回测)。

提供两类引擎，统一接口：
  - VectorStrategyBacktester：内置纯 numpy 向量化回测（默认，离线零依赖）
  - BacktraderAdapter：可选 backtrader 引擎（若已 pip install backtrader 则启用；
                       否则自动降级回 vector 并在结果中标注 backtrader_unavailable）

策略（均 long/flat，避免做空与杠杆，与系统既有 long-only 哲学一致）：
  - ma_cross        ：快慢均线金叉持仓
  - momentum        ：N 日动量为正持仓
  - mean_reversion  ：价格低于均值( z<-阈值 )持仓，回归均值后离场
  - factor          ：用 factor_mining 当前最优因子信号 >0 持仓

数据来源：src.market_data.fetch_ohlcv（在线 akshare / 离线合成降级）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from src.market_data import fetch_ohlcv

logger = logging.getLogger(__name__)

CAPITAL = 1_000_000.0


# --------------------------------------------------------------------------- #
# 信号生成
# --------------------------------------------------------------------------- #
def _rolling_mean(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    c = np.cumsum(np.nan_to_num(x, nan=0.0))
    for i in range(w - 1, len(x)):
        out[i] = (c[i] - (c[i - w] if i - w >= 0 else 0.0)) / w
    return out


def _build_signals(strategy: str, close: np.ndarray,
                   data: Dict[str, np.ndarray],
                   params: Optional[Dict[str, Any]] = None) -> np.ndarray:
    p = params or {}
    n = len(close)
    sig = np.zeros(n, dtype=int)

    if strategy == "ma_cross":
        fast = int(p.get("fast", 5))
        slow = int(p.get("slow", 20))
        ma_f = _rolling_mean(close, fast)
        ma_s = _rolling_mean(close, slow)
        sig = (ma_f > ma_s).astype(int)

    elif strategy == "momentum":
        lb = int(p.get("lookback", 20))
        ret = np.zeros(n)
        ret[lb:] = close[lb:] / close[:-lb] - 1.0
        sig = (ret > 0).astype(int)

    elif strategy == "mean_reversion":
        win = int(p.get("window", 20))
        thr = float(p.get("threshold", 1.0))
        ma = _rolling_mean(close, win)
        sd = np.zeros(n)
        for i in range(win - 1, n):
            sd[i] = close[i - win + 1:i + 1].std()
        z = (close - ma) / (sd + 1e-12)
        # 低于均值(超卖)持仓，回归均值(z>=0)离场
        sig = (z < -thr).astype(int)
        # 持仓状态下一直持有直到 z>=0
        holding = False
        for i in range(n):
            if holding:
                sig[i] = 1
                if z[i] >= 0:
                    holding = False
            elif sig[i] == 1:
                holding = True

    elif strategy == "factor":
        sig = _factor_signal(close, data, p)
    else:
        logger.warning("未知策略 %s，回退 momentum", strategy)
        sig = _build_signals("momentum", close, data, p)
    return sig


def _factor_signal(close: np.ndarray, data: Dict[str, np.ndarray],
                   params: Dict[str, Any]) -> np.ndarray:
    try:
        from src.alpha_factors import AlphaLibrary
        from src.storage import DatabaseManager, FactorMiningResult

        pool = {
            "ret_1d": AlphaLibrary.ret_1d(close),
            "ret_5d": AlphaLibrary.ret_5d(close),
            "ret_20d": AlphaLibrary.ret_20d(close),
            "ma_gap_5": AlphaLibrary.ma_gap(close, 5),
            "ma_gap_20": AlphaLibrary.ma_gap(close, 20),
            "ma_cross": AlphaLibrary.ma_cross(close, 5, 20),
            "vol_20d": AlphaLibrary.volatility_20d(close),
            "rsi_14d": AlphaLibrary.rsi_14d(close),
        }
        m = DatabaseManager.get_instance()
        with m.session_scope() as s:
            row = s.query(FactorMiningResult).filter_by(is_active=1).order_by(
                FactorMiningResult.ic.desc()).first()
            expr = row.factor_expr if row else None
        if not expr:
            return _build_signals("momentum", close, data, params)
        arr = eval(expr, {"__builtins__": {}}, {"np": np, **pool})  # noqa: S307
        arr = np.where(np.isfinite(arr), arr, 0.0)
        return (arr > 0).astype(int)
    except Exception as exc:  # noqa: BLE001
        logger.debug("factor 信号失败，回退 momentum: %s", exc)
        return _build_signals("momentum", close, data, params)


# --------------------------------------------------------------------------- #
# 内置向量化回测
# --------------------------------------------------------------------------- #
class VectorStrategyBacktester:
    @staticmethod
    def run(close: np.ndarray, signals: np.ndarray,
            data: Dict[str, np.ndarray], params: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
        n = len(close)
        ret = np.zeros(n)
        ret[1:] = close[1:] / close[:-1] - 1.0
        # 次日收盘价成交，避免未来函数
        pos = np.zeros(n)
        pos[1:] = signals[:-1]
        strat_ret = pos * ret

        equity = np.cumprod(1.0 + strat_ret) * CAPITAL
        total_return = float(equity[-1] / equity[0] - 1.0)
        ann = float((equity[-1] / equity[0]) ** (252.0 / n) - 1.0)
        sd = strat_ret[1:].std()
        sharpe = float(strat_ret[1:].mean() / (sd + 1e-12) * np.sqrt(252))
        peak = np.maximum.accumulate(equity)
        mdd = float((equity / peak - 1.0).min())

        hold = pos[1:] > 0
        if hold.sum() > 0:
            wins = int((strat_ret[1:][hold] > 0).sum())
            win_rate = round(wins / int(hold.sum()) * 100, 2)
        else:
            win_rate = None
        num_trades = int(np.sum(np.diff(pos) != 0))

        # 交易明细
        trades = _extract_trades(close, pos)
        # 权益曲线降采样（至多 60 点）便于前端绘图
        step = max(1, n // 60)
        eq_curve = [round(float(x), 2) for x in equity[::step].tolist()]
        if eq_curve[-1] != round(float(equity[-1]), 2):
            eq_curve.append(round(float(equity[-1]), 2))

        return {
            "total_return_pct": round(total_return * 100, 2),
            "annual_return_pct": round(ann * 100, 2),
            "sharpe": round(sharpe, 3),
            "max_drawdown_pct": round(mdd * 100, 2),
            "win_rate_pct": win_rate,
            "num_trades": num_trades,
            "final_equity": round(float(equity[-1]), 2),
            "bars": n,
            "source": data.get("source"),
            "equity_curve": eq_curve,
            "trades": trades,
        }


def _extract_trades(close: np.ndarray, pos: np.ndarray) -> List[Dict[str, Any]]:
    trades = []
    in_pos = False
    entry_i = 0
    for i in range(1, len(pos)):
        if pos[i] > 0 and not in_pos:
            in_pos = True
            entry_i = i
        elif pos[i] == 0 and in_pos:
            in_pos = False
            pnl = close[i] / close[entry_i] - 1.0
            trades.append({
                "entry_bar": int(entry_i), "exit_bar": int(i),
                "entry_price": round(float(close[entry_i]), 3),
                "exit_price": round(float(close[i]), 3),
                "pnl_pct": round(float(pnl) * 100, 2),
            })
    if in_pos:
        i = len(pos) - 1
        pnl = close[i] / close[entry_i] - 1.0
        trades.append({
            "entry_bar": int(entry_i), "exit_bar": int(i),
            "entry_price": round(float(close[entry_i]), 3),
            "exit_price": round(float(close[i]), 3),
            "pnl_pct": round(float(pnl) * 100, 2),
        })
    return trades[-20:]  # 仅返回最近 20 笔


# --------------------------------------------------------------------------- #
# 可选 backtrader 适配器
# --------------------------------------------------------------------------- #
class BacktraderAdapter:
    @classmethod
    def available(cls) -> bool:
        try:
            import backtrader  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    def run(cls, close: np.ndarray, signals: np.ndarray,
            data: Dict[str, np.ndarray], params: Optional[Dict[str, Any]] = None
            ) -> Dict[str, Any]:
        import backtrader as bt

        # 构造 feed
        class _Data(bt.feeds.PandasData):
            pass

        dates = np.arange(len(close))
        import pandas as pd
        df = pd.DataFrame({
            "open": data["open"], "high": data["high"], "low": data["low"],
            "close": close, "volume": data["volume"],
            "openinterest": 0.0,
        }, index=pd.date_range("2020-01-01", periods=len(close), freq="D"))
        df.index.name = "datetime"

        sig_shift = np.concatenate([[0], signals[:-1]])

        class _Strat(bt.Strategy):
            def __init__(self):
                self.sig = sig_shift
                self.idx = 0
                self.equity = []
                self.trades = 0
                self.inpos = False

            def next(self):
                self.equity.append(self.broker.getvalue())
                if self.idx >= len(self.sig):
                    return
                target = self.sig[self.idx]
                if target > 0 and not self.inpos:
                    self.buy(size=int(self.broker.getcash() / self.data.close[0] // 100) * 100)
                    self.inpos = True
                    self.trades += 1
                elif target == 0 and self.inpos:
                    self.close()
                    self.inpos = False
                self.idx += 1

        cerebro = bt.Cerebro()
        cerebro.addstrategy(_Strat)
        cerebro.adddata(_Data(dataname=df))
        cerebro.broker.setcash(CAPITAL)
        cerebro.broker.setcommission(commission=0.0003)
        res = cerebro.run()
        strat = res[0]
        eq = np.array(strat.equity)
        final = float(cerebro.broker.getvalue())
        total = final / CAPITAL - 1.0
        peak = np.maximum.accumulate(eq)
        mdd = float((eq / peak - 1.0).min()) if len(eq) else 0.0
        sd = np.diff(eq).std() if len(eq) > 1 else 0.0
        return {
            "total_return_pct": round(total * 100, 2),
            "annual_return_pct": round((final / CAPITAL) ** (252.0 / len(close)) * 100 - 100, 2),
            "sharpe": 0.0,
            "max_drawdown_pct": round(mdd * 100, 2),
            "win_rate_pct": None,
            "num_trades": strat.trades,
            "final_equity": round(final, 2),
            "bars": len(close),
            "source": data.get("source"),
            "equity_curve": [round(float(x), 2) for x in eq[::max(1, len(eq) // 60)]],
            "trades": [],
        }


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #
def list_engines() -> Dict[str, Any]:
    return {
        "default": "vector",
        "available": ["vector"] + (["backtrader"] if BacktraderAdapter.available() else []),
        "backtrader_installed": BacktraderAdapter.available(),
    }


def run_strategy_backtest(
    code: str,
    strategy: str = "ma_cross",
    params: Optional[Dict[str, Any]] = None,
    engine: str = "vector",
    online: bool = False,
    n: int = 250,
) -> Dict[str, Any]:
    data = fetch_ohlcv(code, n=n, online=online)
    close = data["close"]
    signals = _build_signals(strategy, close, data, params)
    base = {"code": code, "strategy": strategy, "params": params or {}}

    if engine == "backtrader" and BacktraderAdapter.available():
        try:
            res = BacktraderAdapter.run(close, signals, data, params)
            res.update(base)
            res["engine"] = "backtrader"
            return res
        except Exception as exc:  # noqa: BLE001
            logger.warning("backtrader 运行失败，回退 vector: %s", exc)
            res = VectorStrategyBacktester.run(close, signals, data, params)
            res.update(base)
            res["engine"] = "vector"
            res["backtrader_unavailable"] = True
            res["fallback_reason"] = str(exc)[:200]
            return res

    res = VectorStrategyBacktester.run(close, signals, data, params)
    res.update(base)
    res["engine"] = "vector"
    if engine == "backtrader":
        res["backtrader_unavailable"] = True
        res["fallback_reason"] = "backtrader 未安装，已使用内置 vector 引擎"
    return res
