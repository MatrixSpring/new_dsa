# -*- coding: utf-8 -*-
"""DSA 每日自动化流水线单元测试（离线 / 确定性）。"""

import json

import pandas as pd
import pytest
from sqlalchemy import Column, Float, Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.dsa_daily_pipeline import (
    ALL_CYCLES,
    ForecastPipeline,
    build_synthetic_kline,
    run_dsa_propagation,
)


# ---------------------------------------------------------------------------
# 合成 K 线
# ---------------------------------------------------------------------------
def test_synthetic_kline_deterministic():
    df1 = build_synthetic_kline("600519", seed=42)
    df2 = build_synthetic_kline("600519", seed=42)
    assert df1.shape == df2.shape
    assert df1["close"].round(6).tolist() == df2["close"].round(6).tolist()
    # 必须含引擎所需的 close/volume
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df1.columns
    assert len(df1) >= 20


# ---------------------------------------------------------------------------
# 四周期预测结构
# ---------------------------------------------------------------------------
def test_forecast_symbol_four_cycles():
    pipe = ForecastPipeline()
    fc = pipe.forecast_symbol("600519", seed=7)
    assert set(fc.keys()) == set(ALL_CYCLES)
    for cyc, r in fc.items():
        assert r["direction"] in ("up", "down", "oscillation")
        assert isinstance(r["up_probability"], int) and 1 <= r["up_probability"] <= 99
        assert 0.0 < r["confidence"] <= 1.0
        assert set(r["sub_model_scores"].keys()) == {"time_series", "capital", "sentiment"}
        # 价格区间合理
        pr = r["price_range"]
        assert pr["optimistic"] >= pr["base"] >= pr["pessimistic"] - 1e-6
        # 波动区间百分比字段存在
        assert "low" in r["volatility_range_pct"] and "high" in r["volatility_range_pct"]


def test_forecast_symbol_deterministic_same_seed():
    pipe = ForecastPipeline()
    a = pipe.forecast_symbol("000001", seed=99)
    b = pipe.forecast_symbol("000001", seed=99)
    assert a["6m"]["consensus_score"] == b["6m"]["consensus_score"]
    assert a["1w"]["up_probability"] == b["1w"]["up_probability"]


def test_forecast_cycle_subset():
    pipe = ForecastPipeline()
    fc = pipe.forecast_symbol("600519", cycles=["1w", "6m"], seed=3)
    assert set(fc.keys()) == {"1w", "6m"}


# ---------------------------------------------------------------------------
# 信号行映射
# ---------------------------------------------------------------------------
def test_to_signal_rows_alignment():
    pipe = ForecastPipeline()
    fc = pipe.forecast_symbol("600519", seed=5)
    rows = pipe.to_signal_rows("600519", "贵州茅台", "A", fc, segment="evening")
    assert len(rows) == len(ALL_CYCLES)
    for row in rows:
        assert row["stock_code"] == "600519"
        assert row["horizon"] in ALL_CYCLES
        assert row["action"] in ("buy", "sell", "hold")
        assert row["status"] == "active"
        assert row["trigger_source"].startswith("daily_loop:")
        # evidence_json 必须可解析
        ev = json.loads(row["evidence_json"])
        assert "sub_model_scores" in ev


# ---------------------------------------------------------------------------
# DSA 产业链传导（复用既有 propagate_shock）
# ---------------------------------------------------------------------------
def _sample_graph():
    return {
        "nodes": [
            {"id": "up", "label": "原油开采", "layer": "upstream"},
            {"id": "mid", "label": "化工中游", "layer": "midstream"},
            {"id": "down", "label": "下游制造", "layer": "downstream"},
        ],
        "edges": [
            {"source": "up", "target": "mid", "coeff": 0.8, "lag": 0},
            {"source": "mid", "target": "down", "coeff": 0.7, "lag": 10},
        ],
        "companies": {
            "mid": [{"code": "600028", "name": "中国石化"}],
            "down": [{"code": "000651", "name": "格力电器"}],
        },
    }


def test_dsa_propagation_basic():
    res = run_dsa_propagation(_sample_graph(), {"node": "up", "magnitude": 0.2, "kind": "cost"})
    assert "summary" in res
    # 上游涨价应传导到中游、下游公司
    codes = {c["code"] for c in res.get("company_impacts", [])}
    assert "600028" in codes
    assert res["summary"]["impacted_nodes"] >= 1


def test_dsa_propagation_empty_graph():
    res = run_dsa_propagation({"nodes": []}, {"node": "x", "magnitude": 0.1})
    assert res["summary"]["total_nodes"] == 0


# ---------------------------------------------------------------------------
# 持久化（用轻量内存模型，避免依赖完整 storage）
# ---------------------------------------------------------------------------
Base = declarative_base()


class _MiniSignal(Base):
    __tablename__ = "mini_decision_signals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16))
    stock_name = Column(String(64))
    market = Column(String(8))
    source_type = Column(String(32))
    trigger_source = Column(String(64))
    action = Column(String(16))
    action_label = Column(String(32))
    confidence = Column(Float)
    score = Column(Integer)
    horizon = Column(String(16))
    entry_low = Column(Float)
    entry_high = Column(Float)
    stop_loss = Column(Float)
    target_price = Column(Float)
    reason = Column(Text)
    risk_summary = Column(Text)
    catalyst_summary = Column(Text)
    evidence_json = Column(Text)
    status = Column(String(16))
    expires_at = Column(DateTime)


@pytest.fixture
def mini_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_persist_signals(mini_session):
    pipe = ForecastPipeline()
    fc = pipe.forecast_symbol("600519", seed=11)
    rows = pipe.to_signal_rows("600519", "贵州茅台", "A", fc, segment="evening")
    added = pipe.persist_signals(rows, mini_session, model_cls=_MiniSignal)
    assert added == len(rows)
    count = mini_session.query(_MiniSignal).filter_by(stock_code="600519").count()
    assert count == len(ALL_CYCLES)
