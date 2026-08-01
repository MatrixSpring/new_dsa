# -*- coding: utf-8 -*-
"""可插拔行情数据源（在线 akshare / 离线合成），供回测与策略模块复用。

设计原则（与全系统一致）：
  - 在线优先：akshare 拉真实日线（stock_zh_a_hist, qfq 前复权）
  - 离线降级：合成随机游走 OHLCV，绝不抛异常、绝不编造
  - 可复现：离线 seed 由代码稳定派生，并支持注入共享 market_ret 以便
           多资产合成序列具备相关性（用于图网络/组合研究）
"""
from __future__ import annotations

import logging
import signal
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)
_ONLINE_TIMEOUT = 30


def _call_to(sec: int, fn, *a, **k):
    def _h(signum, frame):
        raise TimeoutError("timeout")

    old = signal.signal(signal.SIGALRM, _h)
    signal.alarm(sec)
    try:
        return fn(*a, **k)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _stable_seed(code: str) -> int:
    if code.isdigit():
        return int(code) % (2 ** 31)
    return (sum(ord(c) for c in code) * 2654435761) % (2 ** 31)


def _synth_ohlcv(n: int, code: str,
                 market_ret: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    rng = np.random.default_rng(_stable_seed(code))
    if market_ret is None:
        market_ret = rng.normal(0, 0.012, n)
    beta = 0.6 + rng.random() * 0.3
    idio = rng.normal(0, 0.016, n)
    ret = beta * market_ret + idio
    close = 100 * np.cumprod(1 + ret)
    op = close * (1 + rng.normal(0, 0.005, n))
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.01, n)))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.01, n)))
    vo = rng.integers(int(1e5), int(1e6), n).astype(float)
    return {"open": op, "high": hi, "low": lo, "close": close, "volume": vo,
            "source": "synthetic"}


def fetch_ohlcv(code: str, n: int = 250, online: bool = False,
                market_ret: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """返回 dict: {open, high, low, close, volume, source}（均为 np.ndarray）。

    online=True 时尝试 akshare；任何失败自动降级到合成数据（不抛异常）。
    market_ret 若提供，则离线合成序列会与其相关（用于多资产图网络研究）。
    """
    if online:
        try:
            import akshare as ak
            df = _call_to(_ONLINE_TIMEOUT, ak.stock_zh_a_hist,
                          symbol=code, period="daily", adjust="qfq")
            if df is not None and not getattr(df, "empty", True) and len(df) >= 60:
                close = df["收盘"].astype(float).to_numpy()
                op = df["开盘"].astype(float).to_numpy()
                hi = df["最高"].astype(float).to_numpy()
                lo = df["最低"].astype(float).to_numpy()
                vo = df["成交量"].astype(float).to_numpy()
                take = min(n, len(close))
                return {
                    "open": op[-take:], "high": hi[-take:], "low": lo[-take:],
                    "close": close[-take:], "volume": vo[-take:], "source": "akshare",
                }
        except Exception as exc:  # noqa: BLE001
            logger.debug("在线行情 %s 失败，降级合成: %s", code, exc)
    return _synth_ohlcv(n, code, market_ret)


def fetch_returns_matrix(symbols: list[str], n: int = 250, online: bool = False
                         ) -> Dict[str, np.ndarray]:
    """批量拉取多资产日收益矩阵（T,N），注入共享 market_ret 保证相关性。

    Returns: {symbols, close:(T,N), returns:(T,N), source}
    """
    rng = np.random.default_rng(20260601)
    shared_market = rng.normal(0, 0.012, n)
    closes: Dict[str, np.ndarray] = {}
    sources = set()
    for s in symbols:
        d = fetch_ohlcv(s, n=n, online=online, market_ret=shared_market)
        closes[s] = d["close"]
        sources.add(d.get("source", "synthetic"))
    T = min(len(c) for c in closes.values())
    mat = np.column_stack([closes[s][-T:] for s in symbols])
    ret = np.zeros_like(mat, dtype=float)
    ret[1:] = mat[1:] / mat[:-1] - 1.0
    src = "akshare" if sources == {"akshare"} else ("synthetic" if sources == {"synthetic"} else ",".join(sorted(sources)))
    return {"symbols": list(symbols), "close": mat[-T:], "returns": ret[-T:], "source": src}
