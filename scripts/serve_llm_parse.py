# -*- coding: utf-8 -*-
"""
轻量验证服务：只挂载真实的 /api/v1/llm-parse/* 路由（隔离重型 api.v1 链），
用于在网络层面验证「请求 → 数据」链路。使用本地样例文本，避免真实外网/合规风险。

用法：
  python scripts/serve_llm_parse.py                 # 进程内 TestClient 演示
  python scripts/serve_llm_parse.py --serve --port 8013   # 真实 HTTP，可 curl
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


def _load_llm_parse_router():
    """以独立模块加载 llm_parse.py，避免触发 api.v1 重型 __init__。"""
    for name in ("api", "api.v1", "api.v1.endpoints"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod

    spec = importlib.util.spec_from_file_location(
        "api.v1.endpoints.llm_parse",
        os.path.join(REPO_ROOT, "api", "v1", "endpoints", "llm_parse.py"),
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "api.v1.endpoints"
    sys.modules["api.v1.endpoints.llm_parse"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.router


def build_app():
    from fastapi import FastAPI

    app = FastAPI(title="new_dsa llm-parse-verify")
    app.include_router(_load_llm_parse_router(), prefix="/api/v1/llm-parse")
    return app


_SAMPLE_POLICY = (
    "关于进一步扩大新能源汽车消费的通知：\n"
    "一、短期（即日起）对购买新能源乘用车的个人给予每辆1万元补贴，立即生效。\n"
    "二、中期（未来一个月）各地需出台地方性配套补贴细则，设定准入门槛，行业供需将明显改善。\n"
    "三、长期（未来半年）规划建设10个动力电池产业园，产能上限提升至年产500GWh，"
    "技术路线向固态电池倾斜，淘汰落后产能。\n"
    "附加条件：补贴对象须满足动力电池本地配套率不低于40%的前置条件，未达标企业退出补贴名单。"
)

_SAMPLE_REPORT = (
    "某券商半导体行业深度研报：\n"
    "短期看好设备国产化率提升带来的订单弹性；"
    "中期关注美国出口限制的苛刻前提，若限制加码则行业利润承压；"
    "长期半导体自主可控为确定性产业规划，技术路线向先进制程突破。"
    "风险提示：下游需求不及预期、库存减值风险。"
)


def _demo():
    from fastapi.testclient import TestClient

    app = build_app()
    client = TestClient(app)

    # 1) 单文档分层拆解
    r1 = client.post(
        "/api/v1/llm-parse/document",
        json={"text": _SAMPLE_POLICY, "doc_type": "policy", "mode": "deep"},
    )
    print("HTTP", r1.status_code)
    d1 = r1.json()
    assert d1["code"] == 0, d1
    assert d1["data"]["doc_id"], "缺少 doc_id"
    assert d1["data"]["short_term_1w"]["effect"], "缺少短期层"
    assert d1["data"]["long_term_halfyear"]["industry_plan"], "缺少长期层"
    print("document -> source:", d1["data"]["source"],
          "| reliability:", d1["data"]["reliability"])
    print("  短期:", d1["data"]["short_term_1w"]["effect"][:40])
    print("  长期:", d1["data"]["long_term_halfyear"]["industry_plan"][:40])
    print("  约束条数:", len(d1["data"].get("hidden_constraint", [])))

    # 2) 多文档对比
    r2 = client.post(
        "/api/v1/llm-parse/compare",
        json={"documents": [
            {"title": "政策A", "text": _SAMPLE_POLICY},
            {"title": "研报B", "text": _SAMPLE_REPORT},
        ]},
    )
    d2 = r2.json()
    assert d2["code"] == 0, d2
    assert d2["data"]["doc_count"] == 2
    print("compare -> doc_count:", d2["data"]["doc_count"], "| source:", d2["data"]["source"])

    # 3) 约束挖掘
    r3 = client.post("/api/v1/llm-parse/constraints", json={"text": _SAMPLE_POLICY})
    d3 = r3.json()
    assert d3["code"] == 0, d3
    print("constraints -> 条数:", len(d3["data"]["hidden_constraint"]))

    # 4) 长期规划
    r4 = client.post("/api/v1/llm-parse/long-term", json={"text": _SAMPLE_POLICY})
    d4 = r4.json()
    assert d4["code"] == 0, d4
    print("long-term -> plan:", d4["data"]["industry_plan"][:40])

    print("REQUEST_TO_DATA_OK llm_parse endpoints=4")
    return {"document": d1, "compare": d2, "constraints": d3, "long_term": d4}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="以真实 HTTP 服务运行")
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.serve:
        import uvicorn

        uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")
    else:
        _demo()


if __name__ == "__main__":
    main()
