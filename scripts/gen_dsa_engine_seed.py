# -*- coding: utf-8 -*-
"""生成前端 SSR 验证用的 DSA 引擎 seed JSON（真实调用后端 propagate + scenarios）。"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _camel(s: str) -> str:
    return re.sub(r'_([a-z0-9])', lambda m: m.group(1).upper(), s)


def _to_camel(obj):
    """递归 snake_case -> camelCase（前端 toCamelCase 等价）。"""
    if isinstance(obj, dict):
        return {_camel(k): _to_camel(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_camel(x) for x in obj]
    return obj

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load(modname: str, path: str):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


storage = _load('src_storage_g', os.path.join(ROOT, 'src', 'storage.py'))
ic_ep = _load('api_v1_endpoints_industry_chain_g', os.path.join(ROOT, 'api', 'v1', 'endpoints', 'industry_chain.py'))

app = FastAPI()
app.include_router(ic_ep.router, prefix='/api/v1')
client = TestClient(app)

# 产业链目录
r = client.get('/api/v1/industry-chains')
chains = r.json().get('items', [])
chain_list = [
    {'id': c['id'], 'name': c['name'], 'icon': c.get('icon', ''), 'color': c.get('color', ''),
     'category': c.get('category', ''), 'l1': c.get('l1', ''), 'l2': c.get('l2', ''),
     'summary': c.get('summary', ''), 'source': c.get('source', ''),
     'nodeCount': c.get('nodeCount', 0), 'companyCount': c.get('companyCount')}
    for c in chains
]

# 全局参数
gp = client.get('/api/v1/dsa-params').json().get('items', [])
params = [{'paramKey': p['paramKey'], 'paramValue': p['paramValue'], 'paramDesc': p.get('paramDesc')} for p in gp]

# 选 lithium 首个节点做冲击源
g = client.get('/api/v1/industry-chains/lithium').json()
shock_node = g['nodes'][0]['label']

propagate = client.post('/api/v1/industry-chains/lithium/propagate',
                        json={'node': shock_node, 'magnitude': 0.2, 'kind': 'cost'}).json()
scenarios_body = client.post('/api/v1/industry-chains/lithium/propagate-scenarios',
                             json={'node': shock_node, 'magnitude': 0.2, 'kind': 'cost'}).json()

seed = {
    'chains': chain_list,
    'params': params,
    'propagate': _to_camel(propagate),
    'scenarios': _to_camel(scenarios_body.get('data')),
    'shockNode': shock_node,
}

out_path = os.path.join(ROOT, 'apps', 'dsa-web', 'scripts', 'dsa_engine_seed.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(seed, f, ensure_ascii=False, indent=2)
print('wrote', out_path, 'chains=', len(chain_list), 'shockNode=', shock_node)
