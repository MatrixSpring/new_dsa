# -*- coding: utf-8 -*-
"""
轻量验证服务：挂载 #5/#6/#7 的真实路由（industry_chain / company / dsa_params），
验证「请求 → 数据」链路。

用法：
  python scripts/serve_maintenance.py                  # 进程内 TestClient 演示
  python scripts/serve_maintenance.py --serve --port 8017   # 真实 HTTP，可 curl
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


def _stub_pkg(name: str):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod


def _load_router(modname: str, path_parts: list):
    for name in ("api", "api.v1", "api.v1.endpoints"):
        _stub_pkg(name)
    spec = importlib.util.spec_from_file_location(
        f"api.v1.endpoints.{modname}",
        os.path.join(REPO_ROOT, *path_parts),
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "api.v1.endpoints"
    sys.modules[f"api.v1.endpoints.{modname}"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.router


def build_app():
    from fastapi import FastAPI

    app = FastAPI(title="new_dsa maintenance-verify")
    app.include_router(_load_router("industry_chain", ["api", "v1", "endpoints", "industry_chain.py"]), prefix="/api/v1")
    app.include_router(_load_router("company", ["api", "v1", "endpoints", "company.py"]), prefix="/api/v1")
    app.include_router(_load_router("dsa_params", ["api", "v1", "endpoints", "dsa_params.py"]), prefix="/api/v1/dsa-params")
    return app


def _demo():
    from fastapi.testclient import TestClient

    app = build_app()
    client = TestClient(app)

    print("===== #5 产业链维护 =====")
    # 选第一条 xzsc 链
    lst = client.get("/api/v1/industry-chains").json()
    assert lst.get("total", 0) >= 1, lst
    chain = lst["items"][0]
    cid = chain["id"]
    print("chain:", cid, chain["name"], "nodeCount=", chain.get("nodeCount"))

    # 自定义传导系数
    r = client.put(f"/api/v1/industry-chains/{cid}/edge-override", json={
        "source_node": "锂矿", "target_node": "正极材料", "coeff": 0.85, "lag": 3,
    }).json()
    assert r["code"] == 0, r
    assert abs(r["data"]["coeff"] - 0.85) < 1e-6, r
    print("edge-override saved:", r["data"])

    # 列表
    ov = client.get(f"/api/v1/industry-chains/{cid}/edge-overrides").json()
    assert ov["code"] == 0 and ov["total"] >= 1, ov
    print("edge-overrides total:", ov["total"])

    # 风险标记
    rf = client.post(f"/api/v1/industry-chains/{cid}/risk-flag", json={
        "node": "碳酸锂", "risk_type": "price_up", "severity": "高", "note": "价格上涨超阈值",
    }).json()
    assert rf["code"] == 0, rf
    print("risk-flag:", rf["data"])

    # 风险列表
    rfl = client.get(f"/api/v1/industry-chains/{cid}/risk-flags").json()
    assert rfl["code"] == 0 and rfl["total"] >= 1, rfl
    print("risk-flags total:", rfl["total"])

    # 模板导出
    ex = client.get(f"/api/v1/industry-chains/{cid}/export-template").json()
    assert ex["code"] == 0, ex
    tpl = ex["data"]
    assert tpl["meta"]["chainId"] == cid, ex
    print("export-template nodes/edges:", len(tpl["nodes"]), "/", len(tpl["edges"]))

    print("===== #6 公司维护 =====")
    cl = client.get("/api/v1/companies").json()
    assert cl.get("total", 0) > 0, cl
    code = cl["items"][0]["code"]
    print("company:", code, cl["items"][0]["name"])

    # 自动识别风险标签（写库）
    cr = client.post(f"/api/v1/companies/{code}/risk-tags").json()
    assert cr["code"] == 0, cr
    total = cr["data"]["total"]
    print("risk-tags computed:", total)

    # 重新读取
    gr = client.get(f"/api/v1/companies/{code}/risk-tags").json()
    assert gr["code"] == 0 and gr["total"] == total, gr
    print("risk-tags re-read:", gr["total"])

    # detail 合并 riskTags
    det = client.get(f"/api/v1/companies/{code}").json()
    assert "riskTags" in det, det
    print("detail.riskTags merged:", len(det.get("riskTags", [])))

    print("===== #7 DSA 全局参数 =====")
    seed = client.post("/api/v1/dsa-params/seed").json()
    assert seed["code"] == 0, seed
    print("seed created:", seed["data"]["created"])

    lp = client.get("/api/v1/dsa-params/").json()
    assert lp["code"] == 0 and lp["total"] >= 1, lp
    print("dsa-params total:", lp["total"])

    # 修改一个参数
    sp = client.put("/api/v1/dsa-params/coeff_threshold", json={"paramValue": 0.9, "paramDesc": "双向传导系数阈值(改)"}).json()
    assert sp["code"] == 0, sp
    assert abs(sp["data"]["paramValue"] - 0.9) < 1e-6, sp
    print("set coeff_threshold ->", sp["data"]["paramValue"])

    print("REQUEST_TO_DATA_OK endpoints=9")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="以真实 HTTP 服务运行")
    parser.add_argument("--port", type=int, default=8017)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.serve:
        import uvicorn
        uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")
    else:
        _demo()


if __name__ == "__main__":
    main()
