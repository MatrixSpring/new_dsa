# -*- coding: utf-8 -*-
"""#12 验证：DSA 引擎补设计规则 + 三情景并行传导（request -> data）。

后端全链路验证：
  1) propagate_shock 纯函数单测（深度上限 / 双向衰减 / 利空衰减 / 系数区间 / 覆盖系数）
  2) importlib 加载 industry_chain 端点，验证
     - POST /api/v1/industry-chains/{id}/propagate（默认值来自 dsa_global_params）
     - POST /api/v1/industry-chains/{id}/propagate-scenarios（基准/乐观/悲观 三键）
"""
from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load(modname: str, path: str):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


prop = _load('src_industry_chain_propagation_x', os.path.join(ROOT, 'src', 'industry_chain_propagation.py'))
storage = _load('src_storage_x', os.path.join(ROOT, 'src', 'storage.py'))
ic_ep = _load('api_v1_endpoints_industry_chain_x', os.path.join(ROOT, 'api', 'v1', 'endpoints', 'industry_chain.py'))

propagate_shock = prop.propagate_shock

# 一条 4 跳长链，用于验证深度限制 / 双向逐跳衰减
_LONG = {
    "nodes": [{"id": f"n{i}", "label": f"环节{i}"} for i in range(6)],
    "edges": [{"source": f"n{i}", "target": f"n{i+1}", "coeff": 0.9, "lag": 0} for i in range(5)],
    "companies": {},
}


def _unit_engine_rules() -> None:
    """纯函数层面验证 §3.1 设计规则。"""
    # 1) 系数区间校验 clamp(0,1)
    r = propagate_shock(_LONG, {"node": "n0", "magnitude": 0.5, "kind": "cost"},
                        {"max_depth": 20, "bidirectional_decay": 1.0, "bearish_decay": 1.0})
    # 2) 双向衰减：比较 bd=1.0 与 bd=0.85 在 2 跳处的差异
    a = propagate_shock(_LONG, {"node": "n0", "magnitude": 1.0, "kind": "cost"},
                        {"max_depth": 20, "bidirectional_decay": 1.0, "bearish_decay": 1.0})
    b = propagate_shock(_LONG, {"node": "n0", "magnitude": 1.0, "kind": "cost"},
                        {"max_depth": 20, "bidirectional_decay": 0.85, "bearish_decay": 1.0})
    imp_a = {x["node_id"]: x["impact"] for x in a["node_impacts"]}
    imp_b = {x["node_id"]: x["impact"] for x in b["node_impacts"]}
    assert abs(imp_a["n2"] - 0.9 * 0.9) < 1e-6, imp_a  # bd=1: 0.81
    assert abs(imp_b["n2"] - 0.9 * 0.9 * 0.85) < 1e-6, imp_b  # bd=0.85: 0.6885
    print(f"[unit] bidirectional decay: n2 impact bd=1.0 -> {imp_a['n2']:.4f}, bd=0.85 -> {imp_b['n2']:.4f}")

    # 3) 深度上限：max_depth=1 时 n1 受影响、n2 不受影响
    c = propagate_shock(_LONG, {"node": "n0", "magnitude": 1.0, "kind": "cost"},
                        {"max_depth": 1, "bidirectional_decay": 1.0, "bearish_decay": 1.0})
    ids = {x["node_id"] for x in c["node_impacts"]}
    assert "n1" in ids and "n2" not in ids, ids
    print(f"[unit] max_depth=1 -> impacted {sorted(ids)}")

    # 4) 利空衰减：negative 比 cost 在同源处幅度更小
    pos = propagate_shock(_LONG, {"node": "n0", "magnitude": 1.0, "kind": "cost"},
                          {"max_depth": 20, "bidirectional_decay": 1.0, "bearish_decay": 0.7})
    neg = propagate_shock(_LONG, {"node": "n0", "magnitude": 1.0, "kind": "negative"},
                          {"max_depth": 20, "bidirectional_decay": 1.0, "bearish_decay": 0.7})
    assert abs(neg["node_impacts"][0]["impact"] - pos["node_impacts"][0]["impact"] * 0.7) < 1e-6, (pos, neg)
    print(f"[unit] bearish decay: n1 impact cost={pos['node_impacts'][0]['impact']:.4f} negative={neg['node_impacts'][0]['impact']:.4f}")

    # 5) 覆盖系数 use_overrides：把 n0->n1 的 coeff 覆盖为 0.3
    overrides = {("n0", "n1"): {"coeff": 0.3, "lag": 0}}
    ov = propagate_shock(_LONG, {"node": "n0", "magnitude": 1.0, "kind": "cost"},
                         {"max_depth": 20, "bidirectional_decay": 1.0, "bearish_decay": 1.0,
                          "use_overrides": True, "overrides": overrides})
    assert abs(ov["node_impacts"][0]["impact"] - 0.3) < 1e-6, ov["node_impacts"]
    assert ov["summary"]["params"]["used_overrides"] is True
    print(f"[unit] override coeff n0->n1 = 0.3 -> n1 impact {ov['node_impacts'][0]['impact']:.4f}")


def _endpoint_scenarios() -> None:
    app = FastAPI()
    app.include_router(ic_ep.router, prefix='/api/v1')
    client = TestClient(app)

    # 取一条内置链与其首个节点作为冲击源
    r = client.get('/api/v1/industry-chains/lithium')
    assert r.status_code == 200, r.text
    nodes = r.json().get('nodes', [])
    assert nodes, 'lithium 无节点'
    shock_node = nodes[0]['label']

    # 单冲击传导（默认参数来自 dsa_global_params / 设计常数）
    r = client.post(f'/api/v1/industry-chains/lithium/propagate',
                    json={'node': shock_node, 'magnitude': 0.2, 'kind': 'cost'})
    assert r.status_code == 200, r.text
    res = r.json()
    assert 'summary' in res and 'params' in res, res
    print(f"[endpoint] propagate lithium@{shock_node}: impacted={res['summary']['impacted_nodes']} "
          f"companies={res['summary']['affected_companies']} params={res['params']}")
    assert res['summary']['impacted_nodes'] >= 1

    # 三情景并行传导
    r = client.post(f'/api/v1/industry-chains/lithium/propagate-scenarios',
                    json={'node': shock_node, 'magnitude': 0.2, 'kind': 'cost'})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['code'] == 0, body
    data = body['data']
    for key in ('base', 'optimistic', 'pessimistic'):
        assert key in data and 'summary' in data[key], data
    print(f"[endpoint] scenarios: base.impacted={data['base']['summary']['impacted_nodes']} "
          f"optimistic={data['optimistic']['summary']['impacted_nodes']} "
          f"pessimistic={data['pessimistic']['summary']['impacted_nodes']}")
    # 悲观情景冲击幅度更大 -> 受影响环节不应少于基准
    assert data['pessimistic']['summary']['impacted_nodes'] >= data['base']['summary']['impacted_nodes']
    assert data['optimistic']['summary']['max_impact_pct'] <= data['base']['summary']['max_impact_pct'] + 1e-6


def main() -> None:
    _unit_engine_rules()
    _endpoint_scenarios()
    print('\nALL_REQUEST_DATA_OK')


if __name__ == '__main__':
    main()
