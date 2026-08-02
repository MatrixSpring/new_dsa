# -*- coding: utf-8 -*-
"""反向归因闭环预警 · 无头扫描入口（DSA-BACKTRACE-V1.0 #21）。

供 WorkBuddy 自动化 / 系统 cron / GitHub Actions 在收盘后调用：
读取当日大涨回溯池 → 逐只跑一键闭环（Agent 深挖 → 因子预判 → 内核传导）
→ 生成分级预警并落「批次聚合」记录 → 输出批次 JSON 摘要。

用法：
  python scripts/run_backtrace_scan.py [--run-type schedule|manual|event] [--watchlist 600519,hk00700]

退出码：0 成功；非 0 失败。输出为单行 JSON，便于自动化解析与汇报。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load(modname: str, path: str):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    parser = argparse.ArgumentParser(description='反向归因闭环预警无头扫描')
    parser.add_argument('--run-type', default='schedule', choices=['manual', 'schedule', 'event'])
    parser.add_argument('--watchlist', default=None, help='逗号分隔的标的代码；缺省回退当日大涨回溯池')
    args = parser.parse_args()

    scan_svc = _load('src_services_scan_cli', os.path.join(ROOT, 'src', 'services', 'closed_loop_scan_service.py'))
    sched_svc = _load('src_services_sched_cli', os.path.join(ROOT, 'src', 'services', 'closed_loop_scheduler_service.py'))
    bt_svc = _load('src_services_bt_cli', os.path.join(ROOT, 'src', 'services', 'backtrace_service.py'))

    watchlist = None
    if args.watchlist:
        watchlist = [c.strip() for c in args.watchlist.split(',') if c.strip()]

    # 若由自动化独立触发且回溯池为空（当日 screen 尚未跑），先补跑筛选，保证扫描有标的
    if watchlist is None:
        pool_resp = bt_svc.list_screen_pool()
        if not (pool_resp.get('data') or {}).get('items'):
            bt_svc.screen_big_rise()

    res = sched_svc.run_scheduled_scan(run_type=args.run_type, watchlist=watchlist)
    if res.get('code') != 0:
        print(json.dumps({'ok': False, 'msg': res.get('msg')}, ensure_ascii=False))
        return 1

    d = res['data']
    batch = d['batch']
    scan = d['scan']
    alerts = scan.get('alerts') or []
    strong = [a for a in alerts if a.get('level', '').startswith('强信号')]
    neutral = [a for a in alerts if a.get('level', '').startswith('中性')]

    out = {
        'ok': True,
        'batchId': batch['batchId'],
        'runType': batch['runType'],
        'totalScanned': batch['totalScanned'],
        'strongCount': batch['strongCount'],
        'neutralCount': batch['neutralCount'],
        'weakCount': batch['weakCount'],
        'topStock': batch['topStock'],
        'topStockName': batch['topStockName'],
        'topComposite': batch['topComposite'],
        'strongWatchlist': [
            {'stockCode': a['stockCode'], 'stockName': a.get('stockName'), 'compositeScore': a['compositeScore']}
            for a in strong
        ],
        'neutralWatchlist': [
            {'stockCode': a['stockCode'], 'stockName': a.get('stockName'), 'compositeScore': a['compositeScore']}
            for a in neutral
        ],
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
