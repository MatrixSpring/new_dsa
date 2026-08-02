# -*- coding: utf-8 -*-
"""#10 验证：情报结构化 5 字段 + AI 分级（request -> data）。"""
import importlib.util
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_endpoint(mod_name: str):
    path = os.path.join(REPO_ROOT, "api", "v1", "endpoints", f"{mod_name}.py")
    spec = importlib.util.spec_from_file_location(f"ep_{mod_name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


intel_impact = _load_endpoint("intelligence_impact")
from src.storage import DatabaseManager  # noqa: E402

app = FastAPI()
app.include_router(intel_impact.router, prefix='/api/v1/intelligence-impact')


def main():
    DatabaseManager.get_instance()  # 触发建表 intelligence_item_impact

    client = TestClient(app)

    print('===== #10 情报结构化 5 字段 + AI 分级 =====')
    items = [
        {'id': 'itm_1', 'title': '央行超预期降准，流动性利好', 'summary': '重大货币政策', 'industry': 'sw_bank'},
        {'id': 'itm_2', 'title': '某龙头减产，行业供给收缩利空中小厂', 'summary': '风险事件', 'industry': 'sw_chemical'},
        {'id': 'itm_3', 'title': '日常行业惯例公告', 'summary': '常规', 'industry': None},
    ]
    g = client.post('/api/v1/intelligence-impact/grade', json={'items': items}).json()
    print('grade:', g['data']['graded'], 'items:', [(i['itemId'], i['impactDirection'], i['impactLevel'], i['impactCycle']) for i in g['data']['items']])
    assert g['code'] == 0 and g['data']['graded'] == 3, g
    # 方向判定：itm_1 利好 / itm_2 利空 / itm_3 中性
    by_id = {i['itemId']: i for i in g['data']['items']}
    assert by_id['itm_1']['impactDirection'] == '利好', by_id['itm_1']
    assert by_id['itm_2']['impactDirection'] == '利空', by_id['itm_2']
    assert by_id['itm_3']['impactDirection'] == '中性', by_id['itm_3']
    assert by_id['itm_1']['impactLevel'] == '高', by_id['itm_1']
    assert 0 < by_id['itm_1']['transmitWeight'] <= 1, by_id['itm_1']

    # 读取 + 过滤
    all_i = client.get('/api/v1/intelligence-impact/impacts').json()
    print('impacts total:', all_i['total'])
    assert all_i['code'] == 0 and all_i['total'] == 3, all_i

    bull = client.get('/api/v1/intelligence-impact/impacts', params={'direction': '利好'}).json()
    assert bull['total'] == 1 and bull['items'][0]['itemId'] == 'itm_1', bull

    # 幂等 upsert：重复 grade 同一批，impacts 总数不变
    g2 = client.post('/api/v1/intelligence-impact/grade', json={'items': items}).json()
    assert g2['data']['graded'] == 3, g2
    all2 = client.get('/api/v1/intelligence-impact/impacts').json()
    assert all2['total'] == 3, all2

    print('\nALL_REQUEST_DATA_OK')


if __name__ == '__main__':
    main()
