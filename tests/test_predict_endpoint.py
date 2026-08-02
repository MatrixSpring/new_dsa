# -*- coding: utf-8 -*-
"""
多周期前瞻预测接口单元测试（构建最小 FastAPI 应用，不依赖完整 api.app）。

说明：api.v1 包的 __init__ 会拉起全量 endpoint 与 src.llm / src.config 等重型依赖，
本测试用 importlib 直接以独立模块加载 predict.py（其顶层仅依赖 fastapi / pydantic /
core.dsa_daily_pipeline），既测试真实端点代码，又避免污染最小测试环境。
"""

import importlib.util
import os
import sys
import types
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 以真实点分名加载 predict.py，但预先把 api* 父包塞成空桩，
# 阻止其重型 __init__（会拉起 src.llm / src.config 等）执行。
_PREDICT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "api", "v1", "endpoints", "predict.py"
)
for _pkg in ("api", "api.v1", "api.v1.endpoints"):
    sys.modules.setdefault(_pkg, types.ModuleType(_pkg))
_SPEC = importlib.util.spec_from_file_location("api.v1.endpoints.predict", _PREDICT_PATH)
_predict_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["api.v1.endpoints.predict"] = _predict_mod
_SPEC.loader.exec_module(_predict_mod)

router = _predict_mod.router
app = FastAPI()
app.include_router(router, prefix="/predict")
client = TestClient(app)


def _sample_graph():
    return {
        "nodes": [
            {"id": "up", "label": "原油开采"},
            {"id": "mid", "label": "化工中游"},
        ],
        "edges": [{"source": "up", "target": "mid", "coeff": 0.8, "lag": 0}],
        "companies": {"mid": [{"code": "600028", "name": "中国石化"}]},
    }


def test_multi_cycle_predict_ok():
    resp = client.post(
        "/predict/multi-cycle",
        json={"symbols": ["600519", "000001"], "mode": "synthetic", "seed": 42},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    syms = body["data"]["symbols"]
    assert set(syms.keys()) == {"600519", "000001"}
    for sym, obj in syms.items():
        assert set(obj["cycles"].keys()) == {"1w", "2w", "1m", "6m"}
        cyc = obj["cycles"]["6m"]
        assert 1 <= cyc["up_probability"] <= 99
        assert cyc["direction"] in ("up", "down", "oscillation")


def test_multi_cycle_predict_subset_cycles():
    resp = client.post(
        "/predict/multi-cycle",
        json={"symbols": ["600519"], "cycles": ["1w", "6m"], "seed": 1},
    )
    assert resp.status_code == 200
    cyc = resp.json()["data"]["symbols"]["600519"]["cycles"]
    assert set(cyc.keys()) == {"1w", "6m"}


def test_multi_cycle_predict_invalid_cycle():
    resp = client.post(
        "/predict/multi-cycle",
        json={"symbols": ["600519"], "cycles": ["1w", "非法周期"]},
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 400


def test_multi_cycle_predict_empty_symbols_rejected():
    resp = client.post("/predict/multi-cycle", json={"symbols": []})
    assert resp.status_code == 422  # pydantic 校验


def test_dsa_propagation_endpoint():
    resp = client.post(
        "/predict/dsa-propagation",
        json={"graph": _sample_graph(), "shock": {"node": "up", "magnitude": 0.2, "kind": "cost"}},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["summary"]["impacted_nodes"] >= 1
    codes = {c["code"] for c in data.get("company_impacts", [])}
    assert "600028" in codes
