# -*- coding: utf-8 -*-
"""可插拔公开披露源无头刷新入口（DSA-BACKTRACE-V1.0 #26，cron/CI 友好）。

为 #25 真实环境适配提供无头（headless）CLI：在不启动 Web 服务的前提下，
刷新公开披露事件池（mock / cninfo 经 AkShare），并可选联动闭环扫描验证披露叠加。

设计原则（对齐 #25 / §7）：
  - 全链路复用后端 disclosure_provider，不重复实现数据源逻辑；
  - 切换零代码改动：仅通过环境变量 DSA_REALTIME_DISCLOSURE 控制；
  - 真实环境缺失 akshare / 调用失败 → 优雅回退 mock，并以退出码 2 提示运维关注；
  - 扫描叠加为可选（--scan），默认只刷新披露池，避免 cron 高频跑重计算。

用法：
  python scripts/run_disclosure_refresh.py                      # 刷新披露池（沙箱默认 mock）
  python scripts/run_disclosure_refresh.py --days 7             # 指定公告窗口天数
  python scripts/run_disclosure_refresh.py --stock-codes 688981,300750
  python scripts/run_disclosure_refresh.py --scan               # 刷新后联动闭环扫描（验证披露叠加）
  python scripts/run_disclosure_refresh.py --dry-run            # 仅探测数据源，不写库
  python scripts/run_disclosure_refresh.py --json               # 机器可读 JSON 输出
  DSA_REALTIME_DISCLOSURE=1 python scripts/run_disclosure_refresh.py   # 实时披露源（缺失则回退）

退出码：
  0  成功（含沙箱默认 mock 与真实源就绪）
  1  运行期错误（异常 / 写库失败）
  2  已请求实时披露源（env 置位）但回退到 mock（akshare 缺失或调用失败），需运维关注
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
    """用 importlib 加载模块，绕开包 __init__ 级联导入（对齐 gen_backtrace_seed.py）。"""
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def _requested_real() -> bool:
    return os.environ.get('DSA_REALTIME_DISCLOSURE', '').strip().lower() in ('1', 'true', 'yes')


def _build_result(disc, args, refresh, pool, scan_result=None, scan_error=None) -> dict:
    src = disc.describe_disclosure_source()
    d = refresh['data'] if refresh else {}
    res = {
        'ok': True,
        'mode': d.get('mode') or src.get('mode'),
        'provider': d.get('provider') or src.get('provider'),
        'reason': d.get('reason') or src.get('reason'),
        'disclosureDate': d.get('disclosureDate'),
        'count': d.get('count', pool['data']['count'] if pool else 0),
        'financialCount': d.get('financialCount', 0),
        'researchCount': d.get('researchCount', 0),
        'source': {
            'provider': src.get('provider'),
            'label': src.get('label'),
            'mode': src.get('mode'),
            'disclosureCount': src.get('disclosureCount'),
            'financialCount': src.get('financialCount'),
            'researchCount': src.get('researchCount'),
            'envKey': src.get('envKey'),
        },
    }
    if pool is not None:
        res['items'] = pool['data']['items']
    if scan_result is not None:
        sd = scan_result['data']
        res['scan'] = {
            'scanBatch': sd.get('scanBatch'),
            'totalScanned': sd.get('totalScanned'),
            'disclosureCandidates': sd.get('disclosureCandidates'),
            'engine': sd.get('engine'),
            'alerts': sd.get('alerts'),
        }
    if scan_error is not None:
        res['scanError'] = scan_error
    return res


def _print_human(res: dict) -> None:
    print('=' * 64)
    print('DSA 公开披露源无头刷新（#26）')
    print('=' * 64)
    print(f"数据源模式     : {res['mode']}")
    print(f"数据源实现     : {res['provider']}")
    print(f"披露事件数     : {res['count']}")
    print(f"  其中财报     : {res['financialCount']}")
    print(f"  其中研报点评 : {res['researchCount']}")
    print(f"刷新日期       : {res['disclosureDate']}")
    print(f"说明           : {res['reason']}")
    if res.get('items'):
        print('-' * 64)
        print('披露事件池（前 12 条）：')
        for it in res['items'][:12]:
            print(f"  [{it.get('category')}/{it.get('sentiment')}] "
                  f"{it.get('stockCode')} {it.get('stockName')} "
                  f"{it.get('disclosureDate')} {it.get('title')}")
    if 'scan' in res:
        sc = res['scan']
        print('-' * 64)
        print(f"闭环扫描       : 总计 {sc['totalScanned']} 只，"
              f"披露叠加候选 {sc['disclosureCandidates']} 只")
        print(f"  批次         : {sc['scanBatch']}")
    if res.get('scanError'):
        print(f"  [warn] 扫描叠加未执行：{res['scanError']}")
    print('=' * 64)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='DSA 可插拔公开披露源无头刷新（#26）',
    )
    parser.add_argument('--days', type=int, default=7, help='公告事件窗口天数（默认 7）')
    parser.add_argument('--stock-codes', type=str, default=None,
                        help='限定标的代码，逗号分隔（默认全部）')
    parser.add_argument('--scan', action='store_true',
                        help='刷新后联动闭环预警扫描，验证披露叠加（union）')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅探测当前数据源并输出概况，不写库')
    parser.add_argument('--json', action='store_true',
                        help='以 JSON 输出机器可读结果（便于 CI 解析）')
    args = parser.parse_args(argv)

    try:
        storage = _load('src_storage_cli', os.path.join(ROOT, 'src', 'storage.py'))
        disc = _load('src_services_disc_cli',
                     os.path.join(ROOT, 'src', 'services', 'disclosure_provider.py'))

        if args.dry_run:
            # 仅探测：不刷新、不写库
            src = disc.describe_disclosure_source()
            res = {
                'ok': True,
                'dryRun': True,
                'mode': src.get('mode'),
                'provider': src.get('provider'),
                'label': src.get('label'),
                'reason': src.get('reason'),
                'disclosureCount': src.get('disclosureCount'),
                'financialCount': src.get('financialCount'),
                'researchCount': src.get('researchCount'),
                'envKey': src.get('envKey'),
            }
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                _print_human({
                    'mode': res['mode'], 'provider': res['provider'],
                    'reason': res['reason'], 'count': res.get('disclosureCount', 0),
                    'financialCount': res.get('financialCount', 0),
                    'researchCount': res.get('researchCount', 0),
                    'disclosureDate': None, 'items': [],
                })
                print('[dry-run] 未写库。')
            # 退出码：请求实时源却回退 mock → 2
            if _requested_real() and res['mode'] != 'real':
                return 2
            return 0

        stock_codes = None
        if args.stock_codes:
            stock_codes = [c.strip() for c in args.stock_codes.split(',') if c.strip()]

        refresh = disc.refresh_disclosure_pool(stock_codes=stock_codes, days=args.days)
        if refresh.get('code') != 0:
            print(f'[error] 刷新披露池失败：{refresh.get("msg")}', file=sys.stderr)
            return 1
        pool = disc.list_disclosure_pool()

        scan_result = None
        scan_error = None
        if args.scan:
            try:
                scan_svc = _load(
                    'src_services_scan_cli',
                    os.path.join(ROOT, 'src', 'services', 'closed_loop_scan_service.py'),
                )
                scan_result = scan_svc.scan_alerts()
                if scan_result.get('code') != 0:
                    scan_error = scan_result.get('msg')
                    scan_result = None
            except Exception as e:  # noqa: BLE001
                scan_error = f'{type(e).__name__}: {e}'

        res = _build_result(disc, args, refresh, pool, scan_result, scan_error)

        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            _print_human(res)

        # 退出码：请求实时源却回退 mock → 2（运维需关注）；否则 0
        if _requested_real() and res['mode'] != 'real':
            return 2
        return 0

    except Exception as e:  # noqa: BLE001
        err = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
        if args and args.json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f'[error] 运行失败：{err["error"]}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
