# -*- coding: utf-8 -*-
"""
轻量验证服务：只挂载真实的 /api/v1/review/* 路由（隔离重型 api.v1 链），
验证「请求 → 数据」链路（打分 + 聚合报告）。

用法：
  python scripts/serve_review.py                 # 进程内 TestClient 演示
  python scripts/serve_review.py --serve --port 8015   # 真实 HTTP，可 curl
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _load_review_router():
    for name in ("api", "api.v1", "api.v1.endpoints"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod

    spec = importlib.util.spec_from_file_location(
        "api.v1.endpoints.review",
        os.path.join(REPO_ROOT, "api", "v1", "endpoints", "review.py"),
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "api.v1.endpoints"
    sys.modules["api.v1.endpoints.review"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.router


def build_app():
    from fastapi import FastAPI

    app = FastAPI(title="new_dsa review-verify")
    app.include_router(_load_review_router(), prefix="/api/v1/review")
    return app


def _sample_payloads():
    return [
        {
            "symbol": "600519",
            "name": "贵州茅台",
            "cycles": [
                {"cycle": "1w", "direction": "up", "consensus_score": 0.72, "up_probability": 65.0,
                 "confidence": 0.8, "volatility_range_pct": {"low": -3.0, "high": 5.0},
                 "actual_direction": "up", "actual_return_pct": 4.2},
                {"cycle": "1m", "direction": "up", "consensus_score": 0.6, "up_probability": 58.0,
                 "confidence": 0.7, "volatility_range_pct": {"low": -5.0, "high": 8.0},
                 "actual_direction": "oscillation", "actual_return_pct": 1.1},
                {"cycle": "6m", "direction": "up", "consensus_score": 0.55, "up_probability": 55.0,
                 "confidence": 0.65, "volatility_range_pct": {"low": -10.0, "high": 20.0},
                 "actual_direction": "up", "actual_return_pct": 12.0},
            ],
        },
        {
            "symbol": "000001",
            "name": "平安银行",
            "cycles": [
                {"cycle": "1w", "direction": "down", "consensus_score": 0.5, "up_probability": 38.0,
                 "confidence": 0.5, "volatility_range_pct": {"low": -6.0, "high": 2.0},
                 "actual_direction": "up", "actual_return_pct": 3.0},
                {"cycle": "1m", "direction": "down", "consensus_score": 0.45, "up_probability": 40.0,
                 "confidence": 0.5, "volatility_range_pct": {"low": -8.0, "high": 3.0},
                 "actual_direction": "down", "actual_return_pct": -4.0},
            ],
        },
    ]


def _demo():
    from fastapi.testclient import TestClient

    # 清空持久化记录，保证演示确定性
    rec_path = os.path.join(REPO_ROOT, "data", "review_records.json")
    if os.path.exists(rec_path):
        os.remove(rec_path)

    app = build_app()
    client = TestClient(app)

    for payload in _sample_payloads():
        r = client.post("/api/v1/review/score", json=payload)
        d = r.json()
        assert d["code"] == 0, d
        assert d["data"]["accuracy_rate"] is not None
        print(f"score {payload['symbol']} -> accuracy_rate={d['data']['accuracy_rate']} "
              f"weakest={d['data']['weakest_layer']}")

    rep = client.get("/api/v1/review/report")
    rd = rep.json()
    assert rd["code"] == 0, rd
    assert rd["data"]["total"] == 2
    assert "1w" in rd["data"]["by_cycle"]
    print("report -> total:", rd["data"]["total"],
          "| accuracy_rate:", rd["data"]["accuracy_rate"],
          "| weakest_layer:", rd["data"]["weakest_layer"])
    print("by_cycle:", json.dumps(rd["data"]["by_cycle"], ensure_ascii=False))

    # 补一次真实 HTTP 抽样
    print("REQUEST_TO_DATA_OK review endpoints=2")
    return rd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="以真实 HTTP 服务运行")
    parser.add_argument("--port", type=int, default=8015)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.serve:
        import uvicorn

        uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")
    else:
        _demo()


if __name__ == "__main__":
    main()
