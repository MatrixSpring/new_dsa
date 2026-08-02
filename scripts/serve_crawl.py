# -*- coding: utf-8 -*-
"""#11 验证：自动爬虫 + 长文本解析流水线（request -> data）。

用 importlib 直接按文件路径加载端点模块，绕开包 __init__ 的级联导入，
聚焦验证 crawl -> llm_parse -> crawled_documents 全链路。
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


storage = _load('src_storage_x', os.path.join(ROOT, 'src', 'storage.py'))
crawl_ep = _load('api_v1_endpoints_crawl_x', os.path.join(ROOT, 'api', 'v1', 'endpoints', 'crawl.py'))

app = FastAPI()
app.include_router(crawl_ep.router, prefix='/api/v1/crawl')

client = TestClient(app)


def _reset_db() -> None:
    """清空 crawled_documents，保证验证幂等（不依赖历史运行残留）。"""
    m = storage.DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(storage.CrawledDocument).delete()


def main() -> None:
    _reset_db()

    # 1) 列出抓取源
    r = client.get('/api/v1/crawl/sources')
    assert r.status_code == 200, r.text
    sources = r.json()['data']
    print('sources:', [(s['key'], s['docType'], s['adapter']) for s in sources])
    assert len(sources) == 3, sources

    # 2) 运行每个源：抓取 -> 解析 -> 入库
    for sc in sources:
        r = client.post('/api/v1/crawl/run', json={'source_key': sc['key']})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['code'] == 0 and body['data'] is not None, body
        d = body['data']
        print(f"run {sc['key']}: status={d['status']} title={d['title']!r} rawLength={d['rawLength']} parsed={'parsed' in (d or {})}")
        assert d['status'] == 'parsed', d
        assert d['rawLength'] > 0, d
        assert d['parsed'] is not None, d
        assert 'shortTerm1w' in d['parsed'], d['parsed']

    # 3) 文档列表（含结构化结果）
    r = client.get('/api/v1/crawl/documents', params={'limit': 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['code'] == 0, body
    items = body['items']
    print('documents total:', body['total'])
    assert body['total'] == 3, body
    assert all(it['parsed'] is not None for it in items), items

    print('ALL_REQUEST_DATA_OK')


if __name__ == '__main__':
    main()
