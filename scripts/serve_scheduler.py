# -*- coding: utf-8 -*-
"""
轻量验证服务：只挂载真实的 /api/v1/scheduler/* 路由（隔离重型 api.v1 链），
验证「请求 → 数据」链路。

用法：
  python scripts/serve_scheduler.py                 # 进程内 TestClient 演示
  python scripts/serve_scheduler.py --serve --port 8014   # 真实 HTTP，可 curl
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


def _load_scheduler_router():
    for name in ("api", "api.v1", "api.v1.endpoints"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod

    spec = importlib.util.spec_from_file_location(
        "api.v1.endpoints.scheduler",
        os.path.join(REPO_ROOT, "api", "v1", "endpoints", "scheduler.py"),
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "api.v1.endpoints"
    sys.modules["api.v1.endpoints.scheduler"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.router


def build_app():
    from fastapi import FastAPI

    app = FastAPI(title="new_dsa scheduler-verify")
    app.include_router(_load_scheduler_router(), prefix="/api/v1/scheduler")
    return app


def _demo():
    from fastapi.testclient import TestClient

    app = build_app()
    client = TestClient(app)

    r1 = client.get("/api/v1/scheduler/jobs")
    print("GET /jobs HTTP", r1.status_code)
    d1 = r1.json()
    assert d1["code"] == 0, d1
    jobs = d1["data"]["jobs"]
    assert len(jobs) >= 5, "任务数不足"
    print("jobs:", len(jobs))
    for j in jobs:
        print("  -", j["id"], "|", j["trigger_label"], "| enabled=", j["enabled"], "| next=", j["next_run_at"])

    # 启停一个任务
    jid = "crawl_morning_meeting"
    r2 = client.post(f"/api/v1/scheduler/jobs/{jid}/toggle", json={"enabled": False})
    d2 = r2.json()
    assert d2["code"] == 0, d2
    assert d2["data"]["enabled"] is False
    print("toggle", jid, "-> enabled:", d2["data"]["enabled"])

    # 恢复
    client.post(f"/api/v1/scheduler/jobs/{jid}/toggle", json={"enabled": True})

    # 手动触发
    r3 = client.post(f"/api/v1/scheduler/jobs/{jid}/run")
    d3 = r3.json()
    assert d3["code"] == 0, d3
    assert d3["data"]["run_count"] >= 1
    print("run", jid, "-> run_count:", d3["data"]["run_count"])

    print("REQUEST_TO_DATA_OK scheduler endpoints=3")
    return d1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="以真实 HTTP 服务运行")
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.serve:
        import uvicorn

        uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")
    else:
        _demo()


if __name__ == "__main__":
    main()
