# -*- coding: utf-8 -*-
"""#8/#9 验证：前瞻预测快照 + 调度运行日志（request -> data）。"""
import importlib.util
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_endpoint(mod_name: str):
    """按文件路径加载端点模块，绕开 api.v1.endpoints.__init__ 的级联导入。"""
    path = os.path.join(REPO_ROOT, "api", "v1", "endpoints", f"{mod_name}.py")
    spec = importlib.util.spec_from_file_location(f"ep_{mod_name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


forecast_snapshot = _load_endpoint("forecast_snapshot")
scheduler = _load_endpoint("scheduler")

from src.storage import DatabaseManager  # noqa: E402

app = FastAPI()
app.include_router(forecast_snapshot.router, prefix='/api/v1/forecast-snapshots')
app.include_router(scheduler.router, prefix='/api/v1/scheduler')


def main():
    DatabaseManager.get_instance()  # 触发建表（forecast_batch_snapshot / scheduler_job_run）

    client = TestClient(app)

    print('===== #8 前瞻预测快照 =====')
    seed = client.post('/api/v1/forecast-snapshots/seed', json={'force': True}).json()
    print('seed:', seed)
    assert seed['code'] == 0 and seed['data']['created'] == 20, seed

    lst = client.get('/api/v1/forecast-snapshots/').json()
    print('list total:', lst['total'], 'byCycle:', [(c['cycle'], c['total']) for c in lst['byCycle']])
    assert lst['code'] == 0 and lst['total'] == 20, lst
    cycles = {c['cycle'] for c in lst['byCycle']}
    assert cycles == {'1w', '2w', '1m', '6m'}, cycles

    filt = client.get('/api/v1/forecast-snapshots/', params={'scope_type': 'stock'}).json()
    print('filter stock total:', filt['total'])
    assert filt['total'] > 0 and all(i['scopeType'] == 'stock' for i in filt['items']), filt

    detail = client.get('/api/v1/forecast-snapshots/', params={'cycle': '6m'}).json()
    assert detail['total'] > 0 and all(i['cycle'] == '6m' for i in detail['items']), detail
    print('filter 6m total:', detail['total'])

    print('===== #9 调度运行日志 =====')
    jobs = client.get('/api/v1/scheduler/jobs').json()
    print('jobs count=', len(jobs['data']['jobs']))
    assert jobs['code'] == 0 and len(jobs['data']['jobs']) >= 6, jobs
    first_job_id = jobs['data']['jobs'][0]['id']
    print('first job id:', first_job_id)

    rec = client.post(f'/api/v1/scheduler/jobs/{first_job_id}/record',
                      json={'status': 'success', 'summary': '每日主分析完成'}).json()
    print('record:', rec)
    assert rec['code'] == 0 and rec['data']['jobKey'] == first_job_id, rec

    runs = client.get('/api/v1/scheduler/runs').json()
    print('runs total:', runs['total'], 'first:', runs['items'][0]['jobKey'], runs['items'][0]['status'])
    assert runs['code'] == 0 and runs['total'] >= 1, runs

    print('\nALL_REQUEST_DATA_OK')


if __name__ == '__main__':
    main()
