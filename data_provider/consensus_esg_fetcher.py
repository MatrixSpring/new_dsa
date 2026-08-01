# -*- coding: utf-8 -*-
"""
==========================================================
一致预期 (Consensus) + ESG 数据接入层  (P0-①)
==========================================================

目标：补齐 Wind 核心壁垒能力之一——机构一致预期（盈利预测/评级/目标价）
      与 ESG（环境/社会/治理评级）。

降级链（绝不阻塞 ETL）：
  1) 在线 akshare
       - 一致预期: stock_profit_forecast_em(symbol) 盈利预测
                   stock_institute_recommend_detail(symbol) 机构评级记录
       - ESG:      stock_esg_rate_sina() 全市场 ESG 评级（无参，一次性拉取并落地缓存）
  2) 本地缓存 data/cache/esg_cache.json（在线成功后落地，离线可复用）
  3) 内部估算 internal_estimate（离线且无缓存时，仅做数学可推导项，
      其余留空；source 明确标注，绝不编造机构观点或 ESG 评分）

所有在线调用带 SIGALRM 超时 + 异常降级。
"""
from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_CACHE_DIR = _ROOT / "data" / "cache"
_ESG_CACHE = _CACHE_DIR / "esg_cache.json"
_CONSENSUS_CACHE = _CACHE_DIR / "consensus_cache.json"

_ONLINE_TIMEOUT = 45          # 单接口超时(秒)
_ESG_FETCH_TIMEOUT = 90       # 全量 ESG 拉取超时(秒)


def _call_to(sec: int, fn, *a, **k):
    """带 SIGALRM 超时包装（主线程调用）。"""
    def _h(signum, frame):
        raise TimeoutError("timeout")
    old = signal.signal(signal.SIGALRM, _h)
    signal.alarm(sec)
    try:
        return fn(*a, **k)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


# --------------------------------------------------------------------------- #
# 在线获取
# --------------------------------------------------------------------------- #
def _online_profit_forecast(code: str) -> Optional[Dict[str, Any]]:
    """个股盈利预测（研究报告一致预期）。返回 {eps, net_profit, revenue, growth, year} 或 None。"""
    try:
        import akshare as ak
        df = _call_to(_ONLINE_TIMEOUT, ak.stock_profit_forecast_em, symbol=code)
        if df is None or getattr(df, "empty", True):
            return None
        # 取最新一行（按年份/报告期降序）
        cols = [str(c) for c in df.columns]
        rec = df.iloc[0].to_dict()
        def _f(key_candidates):
            for k in key_candidates:
                for c in cols:
                    if k in c:
                        try:
                            return float(rec.get(c))
                        except (TypeError, ValueError):
                            return None
            return None
        year = None
        for c in cols:
            if "年度" in c or "年份" in c or "year" in c.lower():
                try:
                    year = int(float(rec.get(c)))
                except (TypeError, ValueError):
                    year = None
                if year:
                    break
        return {
            "eps": _f(["每股收益", "EPS", "预测EPS"]),
            "net_profit": _f(["净利润", "预测净利润"]),
            "revenue": _f(["营收", "营业收入", "预测营收"]),
            "growth": _f(["增长率", "增速", "同比增长"]),
            "year": year,
        }
    except Exception as e:  # noqa: BLE001
        logger.debug("profit_forecast %s failed: %s", code, e)
        return None


def _online_institute_rating(code: str) -> Optional[Dict[str, Any]]:
    """机构评级记录。返回 {rating, institutes, target_price} 或 None。"""
    try:
        import akshare as ak
        df = _call_to(_ONLINE_TIMEOUT, ak.stock_institute_recommend_detail, symbol=code)
        if df is None or getattr(df, "empty", True):
            return None
        cols = [str(c) for c in df.columns]
        recs = df.to_dict(orient="records")
        institutes = len(recs)
        # 综合评级：取出现频率最高的评级词
        rating_words = ["买入", "增持", "中性", "减持", "卖出", "推荐", "谨慎推荐"]
        rating_counter: Dict[str, int] = {}
        target_prices = []
        for r in recs:
            txt = " ".join(str(v) for v in r.values())
            for w in rating_words:
                if w in txt:
                    rating_counter[w] = rating_counter.get(w, 0) + 1
            for c in cols:
                if "目标价" in c or "价格" in c:
                    try:
                        target_prices.append(float(r.get(c)))
                    except (TypeError, ValueError):
                        pass
        rating = max(rating_counter, key=rating_counter.get) if rating_counter else None
        target = max(target_prices) if target_prices else None
        return {"rating": rating, "institutes": institutes, "target_price": target}
    except Exception as e:  # noqa: BLE001
        logger.debug("institute_rating %s failed: %s", code, e)
        return None


def build_esg_cache(force: bool = False) -> bool:
    """全市场 ESG 评级拉取并落地缓存。成功返回 True。"""
    if _ESG_CACHE.exists() and not force:
        return True
    try:
        import akshare as ak
        df = _call_to(_ESG_FETCH_TIMEOUT, ak.stock_esg_rate_sina)
        if df is None or getattr(df, "empty", True):
            logger.warning("esg_rate_sina returned empty")
            return False
        cols = [str(c) for c in df.columns]
        code_col = next((c for c in cols if "代码" in c or "code" in c.lower()), cols[0])
        cache: Dict[str, Dict[str, Any]] = {}
        for r in df.to_dict(orient="records"):
            code = str(r.get(code_col, "")).strip().upper()
            code = code.split(".")[0]
            if not code.isdigit():
                continue
            norm = code[:6]
            item = {str(k): r.get(k) for k in cols}
            cache[norm] = item
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _ESG_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        logger.info("ESG cache built: %d stocks -> %s", len(cache), _ESG_CACHE)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("build_esg_cache failed: %s", e)
        return False


def _load_esg_cache() -> Dict[str, Any]:
    if _ESG_CACHE.exists():
        try:
            return json.loads(_ESG_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _online_esg_from_cache(code: str) -> Optional[Dict[str, Any]]:
    cache = _load_esg_cache()
    item = cache.get(code[:6])
    if not item:
        return None
    cols = list(item.keys())
    def _f(cands):
        for k in cands:
            for c in cols:
                if k in c:
                    try:
                        return float(item.get(c))
                    except (TypeError, ValueError):
                        return None
        return None
    score = _f(["综合得分", "评分", "得分", "score"])
    rating = None
    for c in cols:
        if "评级" in c or "等级" in c or "rate" in c.lower():
            rating = item.get(c)
            if rating:
                break
    year = None
    for c in cols:
        if "年份" in c or "年度" in c or "year" in c.lower():
            try:
                year = int(float(item.get(c)))
            except (TypeError, ValueError):
                year = None
            if year:
                break
    return {
        "score": score,
        "rating": str(rating) if rating else None,
        "environment": _f(["环境", "E分", "E得分"]),
        "social": _f(["社会", "S分", "S得分"]),
        "governance": _f(["治理", "G分", "G得分"]),
        "year": year,
    }


# --------------------------------------------------------------------------- #
# 内部估算（离线兜底，仅做数学可推导项，明确标注来源）
# --------------------------------------------------------------------------- #
def _estimate_consensus(profile: Dict[str, Any]) -> Dict[str, Any]:
    """离线兜底：仅用 净利润/总股本 推导 TTM EPS（历史），其余留空。"""
    net_profit = profile.get("net_profit")
    total_shares = profile.get("total_shares")
    eps = None
    if net_profit and total_shares:
        try:
            eps = round(net_profit / total_shares, 3)
        except Exception:  # noqa: BLE001
            eps = None
    return {
        "year": datetime.now().year + 1,
        "eps": eps,
        "eps_growth": None,
        "net_profit": None,
        "revenue": None,
        "rating": None,
        "institutes": None,
        "target_price": None,
        "source": "internal_estimate_ttm",  # 历史每股盈利，非机构预期
    }


def _estimate_esg(_profile: Dict[str, Any]) -> Dict[str, Any]:
    """离线兜底：不编造 ESG 评分，全部留空，仅标注来源。"""
    return {
        "score": None, "rating": None, "environment": None,
        "social": None, "governance": None, "year": None,
        "source": "internal_proxy_unavailable",
    }


# --------------------------------------------------------------------------- #
# 对外统一接口
# --------------------------------------------------------------------------- #
def get_consensus(code: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """返回一致预期 dict，含 source 字段。"""
    profile = profile or {}
    # 1) 在线
    pf = _online_profit_forecast(code)
    ir = _online_institute_rating(code)
    if pf or ir:
        merged = {
            "year": (pf or {}).get("year"),
            "eps": (pf or {}).get("eps"),
            "eps_growth": (pf or {}).get("growth"),
            "net_profit": (pf or {}).get("net_profit"),
            "revenue": (pf or {}).get("revenue"),
            "rating": (ir or {}).get("rating"),
            "institutes": (ir or {}).get("institutes") or 0,
            "target_price": (ir or {}).get("target_price"),
            "source": "akshare_online",
        }
        if any(merged[k] is not None for k in ("eps", "rating", "institutes", "target_price")):
            return merged
    # 2) 兜底估算
    est = _estimate_consensus(profile)
    return est


def get_esg(code: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """返回 ESG dict，含 source 字段。"""
    # 1) 在线缓存
    cached = _online_esg_from_cache(code)
    if cached and (cached.get("score") is not None or cached.get("rating")):
        cached["source"] = "akshare_esg_cache"
        return cached
    # 2) 兜底
    return _estimate_esg(profile or {})


def get_consensus_esg(code: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """合并返回 {consensus:{...}, esg:{...}}。"""
    return {
        "consensus": get_consensus(code, profile),
        "esg": get_esg(code, profile),
    }
