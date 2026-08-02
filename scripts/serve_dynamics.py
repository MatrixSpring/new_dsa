# -*- coding: utf-8 -*-
"""
轻量验证服务：挂载真实的 dashboard 路由（/api/v1/* 7 组端点，惰性加载、缺依赖自动降级）
+ 一个契约镜像的 /api/v1/intelligence/items 端点（真实 IntelligenceService 依赖 DB/爬虫，
离线验证用等价结构替代），用于在网络层验证「请求 → 数据」链路。

用法：
  python scripts/serve_dynamics.py              # 进程内 TestClient 演示
  python scripts/serve_dynamics.py --serve --port 8012   # 真实 HTTP，随后可 curl
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 受管 venv（含 fastapi/uvicorn/httpx）
VENV = os.path.join(os.path.expanduser("~"), ".workbuddy", "binaries", "python", "envs", "default")
if os.path.isdir(VENV):
    site = os.path.join(VENV, "lib", "python3.13", "site-packages")
    if site not in sys.path:
        sys.path.insert(0, site)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _load_dashboard_router():
    """独立加载 dashboard.py（仅触发 fastapi + 惰性 src 依赖，避免 api.v1 重型 __init__）。"""
    for name in ("api", "api.v1", "api.v1.endpoints"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod
    spec = importlib.util.spec_from_file_location(
        "api.v1.endpoints.dashboard",
        os.path.join(REPO_ROOT, "api", "v1", "endpoints", "dashboard.py"),
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "api.v1.endpoints"
    sys.modules["api.v1.endpoints.dashboard"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.router


def _demo_intelligence_router():
    """契约镜像：等价 IntelligenceItemList 结构，供离线验证前端请求/解析/展示。"""
    from fastapi import APIRouter, Query

    router = APIRouter()

    SAMPLE = [
        {"id": 1, "sourceType": "policy", "title": "美联储维持利率不变，点阵图暗示年内两次降息",
         "summary": "海外宏观政策落地，对全球流动性与港股科技估值形成支撑。", "url": "https://example.com/1",
         "source": "Reuters", "publishedAt": "2026-08-01T20:00:00", "scopeType": "market", "scopeValue": "us", "market": "us"},
        {"id": 2, "sourceType": "industry", "title": "工信部发布人形机器人产业中长期发展规划",
         "summary": "明确 2027/2030 产能目标与技术路线，利好核心零部件环节。", "url": "https://example.com/2",
         "source": "工信部", "publishedAt": "2026-08-01T09:30:00", "scopeType": "sector", "scopeValue": "robotics", "market": "cn"},
        {"id": 3, "sourceType": "event", "title": "中东地缘冲突升级，原油供给收紧预期升温",
         "summary": "地缘事件驱动，关注油气开采与化工成本传导。", "url": "https://example.com/3",
         "source": "Bloomberg", "publishedAt": "2026-07-31T22:10:00", "scopeType": "market", "scopeValue": "global", "market": "global"},
    ]

    @router.get("/intelligence/items")
    def list_items(
        market: str = Query("global"),
        scopeType: str = Query(None),
        query: str = Query(None),
        days: int = Query(7),
        page: int = Query(1),
        pageSize: int = Query(50),
    ):
        items = SAMPLE
        if market and market != "all":
            items = [i for i in items if i["market"] == market]
        if query:
            q = query.lower()
            items = [i for i in items if q in i["title"].lower() or q in (i["summary"] or "").lower()]
        total = len(items)
        start = (page - 1) * pageSize
        return {"items": items[start:start + pageSize], "total": total, "page": page, "pageSize": pageSize}

    return router


def build_app():
    from fastapi import FastAPI

    app = FastAPI(title="new_dsa dynamics-verify")
    app.include_router(_load_dashboard_router(), prefix="/api/v1")
    app.include_router(_demo_intelligence_router(), prefix="/api/v1")
    return app


def _demo():
    from fastapi.testclient import TestClient

    app = build_app()
    client = TestClient(app)

    # 1) 情报（契约镜像）
    r = client.get("/api/v1/intelligence/items", params={"market": "cn", "days": 7})
    assert r.status_code == 200, r.status_code
    body = r.json()
    assert "items" in body and "total" in body, body
    assert any(i["market"] == "cn" for i in body["items"]), "market 过滤失效"
    print("intelligence/items -> 200, total=%d, cn_items=%d" % (body["total"], len(body["items"])))

    # 2) dashboard 端点（真实路由）
    dashboard_paths = [
        "/api/v1/market/trend",
        "/api/v1/policy/track",
        "/api/v1/stock/recent",
        "/api/v1/game/short",
        "/api/v1/game/long",
        "/api/v1/risk/overview",
    ]
    for p in dashboard_paths:
        rr = client.get(p)
        assert rr.status_code == 200, (p, rr.status_code, rr.text[:200])
        d = rr.json()
        assert d.get("code") == 200, (p, d)
        assert "data" in d, (p, d)
        print("dashboard %s -> 200, data.keys=%s" % (p, list(d["data"].keys()) if isinstance(d["data"], dict) else type(d["data"]).__name__))

    print("REQUEST_TO_DATA_OK endpoints=%d" % (1 + len(dashboard_paths)))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="以真实 HTTP 服务运行")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.serve:
        import uvicorn

        uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")
    else:
        _demo()


if __name__ == "__main__":
    main()
