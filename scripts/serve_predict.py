# -*- coding: utf-8 -*-
"""
轻量验证服务：只挂载真实的 /api/v1/predict/* 路由（隔离重型 api.v1 链），
用于在网络层面验证「请求 → 数据」链路。

用法：
  # 进程内 TestClient 演示（默认）
  python scripts/serve_predict.py

  # 真实 HTTP 服务（随后可 curl）
  python scripts/serve_predict.py --serve --port 8011
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _load_predict_router():
    """以独立模块加载 predict.py，仅触发 core/src 依赖，避免 api.v1 重型 __init__。"""
    # 桩出父包，防止 Python 把该模块当作 api.v1.endpoints 子包去执行父 __init__
    for name in ("api", "api.v1", "api.v1.endpoints"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []  # 标记为包
            sys.modules[name] = mod

    spec = importlib.util.spec_from_file_location(
        "api.v1.endpoints.predict",
        os.path.join(REPO_ROOT, "api", "v1", "endpoints", "predict.py"),
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "api.v1.endpoints"
    sys.modules["api.v1.endpoints.predict"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.router


def build_app():
    from fastapi import FastAPI

    app = FastAPI(title="new_dsa predict-verify")
    app.include_router(_load_predict_router(), prefix="/api/v1/predict")
    return app


def _demo():
    from fastapi.testclient import TestClient

    app = build_app()
    client = TestClient(app)
    payload = {"symbols": ["600519", "AAPL"], "market": "A", "mode": "synthetic", "seed": 42}
    resp = client.post("/api/v1/predict/multi-cycle", json=payload)
    print("HTTP", resp.status_code)
    data = resp.json()
    assert data["code"] == 200, data
    assert "600519" in data["data"]["symbols"], "缺少 600519"
    assert "AAPL" in data["data"]["symbols"], "缺少 AAPL"
    c1w = data["data"]["symbols"]["600519"]["cycles"]["1w"]
    print("code:", data["code"], "mode:", data["data"]["mode"])
    print("cycles_requested:", data["data"]["cycles_requested"])
    print("600519 / 1w -> direction_label:", c1w["direction_label"],
          "| up_probability:", c1w["up_probability"],
          "| confidence:", c1w["confidence"])
    print("REQUEST_TO_DATA_OK symbols=%d" % len(data["data"]["symbols"]))
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="以真实 HTTP 服务运行")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.serve:
        import uvicorn

        uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")
    else:
        _demo()


if __name__ == "__main__":
    main()
