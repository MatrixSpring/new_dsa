"""合并系统已有公司信息到 company_profile 全维度表。

数据来源：
  - data/cache/stocks.index.json      全市场股票主表(代码/名称/拼音/别名) -> 身份解析
  - fundamental_snapshot              已有估值快照(pe/pb/总市值/流通市值) -> 估值维度
  - industry_chain_fusion             产业链融合产出的 xzsc/申万/curated 公司 -> linked_chains
  - industry_chain_sandbox_data.json  产业沙盘内置链(lithium/semiconductor/photovoltaic) 公司 -> linked_chains

公司主键统一归一化为 6 位代码；同名多来源做幂等 upsert；JSON 字段以字符串入库。

用法：
  python -m scripts.build_company_profiles [--reset]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 允许以脚本方式运行
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text as sa_text  # noqa: E402

from src.storage import Base, CompanyProfile, DatabaseManager  # noqa: E402

_JSON_FIELDS = {
    'aliases', 'executives', 'big_goodwill', 'restricted_unlock',
    'top_float_shareholders', 'equity_pledges',
    'revenue_composition', 'profit_composition',
    'performance_drivers', 'customer_concentration', 'supplier_concentration',
    'tech_layout', 'data_sources', 'linked_chains',
}


def norm_code(c: Any) -> Optional[str]:
    """归一化为 6 位股票代码；无法识别返回 None。"""
    if not c:
        return None
    s = str(c).strip().upper()
    base = s.split('.')[0]
    if base.isdigit() and len(base) >= 6:
        return base[:6]
    return None


def exchange_of(code: str, raw: str = '') -> str:
    raw = str(raw).upper()
    if '.SZ' in raw:
        return 'SZ'
    if '.SH' in raw:
        return 'SH'
    if '.BJ' in raw:
        return 'BJ'
    if code.startswith(('60', '68', '90', '99')):
        return 'SH'
    if code.startswith(('00', '30', '20', '39')):
        return 'SZ'
    if code.startswith(('8', '4')):
        return 'BJ'
    return ''


def load_index_map() -> Dict[str, Dict[str, Any]]:
    """code(含.市场 与 6位) -> {name,pinyin,aliases}。"""
    p = ROOT / 'data' / 'cache' / 'stocks.index.json'
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding='utf-8'))
    out: Dict[str, Dict[str, Any]] = {}
    for it in data:
        if not isinstance(it, list):
            continue
        raw_code = it[0]
        six = it[1] if len(it) > 1 else raw_code
        name = it[2] if len(it) > 2 else ''
        pinyin = it[3] if len(it) > 3 else ''
        aliases = it[5] if len(it) > 5 and isinstance(it[5], list) else []
        rec = {'name': name, 'pinyin': pinyin, 'aliases': aliases, 'raw': raw_code}
        n6 = norm_code(six)
        if n6:
            out.setdefault(n6, rec)
            out.setdefault(raw_code, rec)
    return out


def extract_fundamental() -> Dict[str, Dict[str, Any]]:
    """code(6位) -> 估值字段 + 原始 code。取每 code 最新一行。"""
    out: Dict[str, Dict[str, Any]] = {}
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = s.execute(sa_text(
            'SELECT code, payload, created_at FROM fundamental_snapshot ORDER BY id'
        )).fetchall()
    for code_raw, payload, _created in rows:
        n6 = norm_code(code_raw)
        if not n6:
            continue
        try:
            pl = json.loads(payload)
        except (ValueError, TypeError):
            continue
        val = (pl.get('valuation') or {}).get('data') or {}
        rec = out.setdefault(n6, {
            'price': val.get('price') or val.get('close'),
            'total_market_cap': val.get('total_mv'),
            'float_market_cap': val.get('circ_mv'),
            'pe': val.get('pe_ratio'),
            'pb': val.get('pb_ratio'),
            'ps': val.get('ps'),
        })
        # 若已有估值则保留（保持首条/最新）
        if rec.get('pe') is None and val.get('pe_ratio') is not None:
            rec.update({
                'price': val.get('price') or val.get('close'),
                'total_market_cap': val.get('total_mv'),
                'float_market_cap': val.get('circ_mv'),
                'pe': val.get('pe_ratio'),
                'pb': val.get('pb_ratio'),
                'ps': val.get('ps'),
            })
    return out


def gather_fusion_linked() -> Dict[str, List[Dict[str, Any]]]:
    """code(6位) -> [{'chain_id','chain_name','role'}...] 来自 xzsc/申万/curated。"""
    from src.data.industry_chain_fusion import build_xzsc_shenwan_fusion
    from src.data.xzsc_chain import XZSC_CHAINS

    fusion = build_xzsc_shenwan_fusion(XZSC_CHAINS)
    no2name = {str(c['no']): c['name'] for c in XZSC_CHAINS}
    linked: Dict[str, List[Dict[str, Any]]] = {}
    for no, v in fusion['chains'].items():
        chain_name = no2name.get(no, no)
        for m in v.get('matches', []):
            role = 'curated' if m.get('curated') else 'shenwan'
            for comp in m.get('companies', []):
                n6 = norm_code(comp.get('code'))
                if not n6:
                    continue
                linked.setdefault(n6, []).append({
                    'chain_id': f'xzsc:{no}', 'chain_name': chain_name, 'role': role,
                })
    return linked


def gather_builtin_linked() -> Dict[str, List[Dict[str, Any]]]:
    """code(6位) -> [{'chain_id','chain_name','role':'builtin'}] 来自产业沙盘内置链。"""
    p = ROOT / 'src' / 'data' / 'industry_chain_sandbox_data.json'
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding='utf-8'))
    chains = data.get('INDUSTRY_CHAINS', {})
    linked: Dict[str, List[Dict[str, Any]]] = {}
    for cid, ch in chains.items():
        cname = ch.get('name', cid)
        companies = ch.get('companies', {})
        # companies 结构: {nodeId: [comp...]}
        comp_list: List[Dict[str, Any]] = []
        if isinstance(companies, dict):
            for lst in companies.values():
                if isinstance(lst, list):
                    comp_list.extend(lst)
        elif isinstance(companies, list):
            comp_list = companies
        for comp in comp_list:
            n6 = norm_code(comp.get('code'))
            if not n6:
                continue
            linked.setdefault(n6, []).append({
                'chain_id': f'builtin:{cid}', 'chain_name': cname, 'role': 'builtin',
            })
    return linked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--reset', action='store_true', help='先清空 company_profile 再重建')
    ap.add_argument('--online-consensus', action='store_true',
                    help='联网回填真实机构一致预期（默认仅离线估算兜底，速度快）')
    args = ap.parse_args()

    # 确保表存在（表由 DatabaseManager 初始化时自动建；此处仅补建二级索引）
    m = DatabaseManager.get_instance()
    ensure_consensus_esg_columns()
    with m._engine.begin() as _conn:
        _conn.execute(sa_text(
            'CREATE INDEX IF NOT EXISTS ix_company_profile_name ON company_profile (name)'))
        _conn.execute(sa_text(
            'CREATE INDEX IF NOT EXISTS ix_company_profile_pinyin ON company_profile (pinyin)'))

    if args.reset:
        with m.session_scope() as s:
            s.execute(sa_text('DELETE FROM company_profile'))
        print('cleared company_profile')

    index_map = load_index_map()
    fundamental = extract_fundamental()
    fusion_linked = gather_fusion_linked()
    builtin_linked = gather_builtin_linked()

    # 汇总所有出现的公司代码
    all_codes = set(index_map.keys()) | set(fundamental.keys()) | \
        set(fusion_linked.keys()) | set(builtin_linked.keys())

    # 仅纳入"系统已有公司信息"：由 fundamental / fusion / builtin 至少一处出现；
    # 纯 index 条目(无任何其他来源)不进入，保证是已合并的已知公司集合。
    seed_codes = (set(fundamental.keys()) | set(fusion_linked.keys()) | set(builtin_linked.keys()))

    stats = {'total': 0, 'with_valuation': 0, 'with_linked': 0, 'with_name': 0}

    with m.session_scope() as s:
        for code in seed_codes:
            idx = index_map.get(code, {})
            name = idx.get('name') or ''
            # 若不存在于 index，尝试从 fusion/builtin 名称回填
            if not name:
                for src in (fusion_linked, builtin_linked):
                    for lc in src.get(code, []):
                        pass  # 名称在 payload 里未直接存，保留空，后续可由行情补充
            pinyin = idx.get('pinyin') or ''
            aliases = idx.get('aliases') or []
            exchange = exchange_of(code, idx.get('raw', ''))

            # 合并 linked_chains（去重）
            linked: List[Dict[str, Any]] = []
            seen = set()
            for lc in fusion_linked.get(code, []) + builtin_linked.get(code, []):
                key = (lc['chain_id'], lc['role'])
                if key not in seen:
                    seen.add(key)
                    linked.append(lc)

            data_sources = set()
            if code in fundamental:
                data_sources.add('fundamental_snapshot')
            if code in fusion_linked:
                data_sources.add('industry_chain_fusion')
            if code in builtin_linked:
                data_sources.add('builtin_sandbox')
            if idx:
                data_sources.add('stock_index')

            val = fundamental.get(code, {})

            # upsert
            existing = s.get(CompanyProfile, code)
            row = existing or CompanyProfile(code=code)
            row.name = name or (row.name or '')
            row.pinyin = pinyin or (row.pinyin or '')
            row.aliases = json.dumps(aliases, ensure_ascii=False)
            row.exchange = exchange or (row.exchange or '')

            # 估值（仅当新值存在时覆盖，保留既有）
            if val.get('pe') is not None:
                row.pe = val.get('pe')
            if val.get('pb') is not None:
                row.pb = val.get('pb')
            if val.get('ps') is not None:
                row.ps = val.get('ps')
            if val.get('price') is not None:
                row.price = val.get('price')
            if val.get('total_market_cap') is not None:
                row.total_market_cap = val.get('total_market_cap')
            if val.get('float_market_cap') is not None:
                row.float_market_cap = val.get('float_market_cap')

            row.linked_chains = json.dumps(linked, ensure_ascii=False)
            # 合并 data_sources（保留历史）
            prev = set()
            if existing and existing.data_sources:
                try:
                    prev = set(json.loads(existing.data_sources))
                except (ValueError, TypeError):
                    prev = set()
            row.data_sources = json.dumps(sorted(prev | data_sources), ensure_ascii=False)

            if existing is None:
                s.add(row)

            stats['total'] += 1
            if row.pe is not None or row.pb is not None or row.total_market_cap is not None:
                stats['with_valuation'] += 1
            if linked:
                stats['with_linked'] += 1
            if row.name:
                stats['with_name'] += 1

    print('=== company_profile 合并完成 ===')
    print(f"  公司总数: {stats['total']}")
    print(f"  含名称:   {stats['with_name']}")
    print(f"  含估值:   {stats['with_valuation']}")
    print(f"  含产业链关联: {stats['with_linked']}")
    print(f"  来源覆盖: fundamental={len(fundamental)} fusion_linked={len(fusion_linked)} builtin_linked={len(builtin_linked)}")

    # P0-① 一致预期 + ESG 补充（默认离线估算兜底；--online-consensus 联网回填真实机构数据）
    enrich_consensus_esg(online_consensus=args.online_consensus)


def ensure_consensus_esg_columns() -> None:
    """为已存在的 company_profile 表补齐一致预期/ESG 新列（create_all 不会自动 ALTER）。"""
    new_cols = {
        'consensus_year': 'INTEGER', 'consensus_eps': 'REAL', 'consensus_eps_growth': 'REAL',
        'consensus_net_profit': 'REAL', 'consensus_revenue': 'REAL', 'consensus_rating': 'TEXT',
        'consensus_institutes': 'INTEGER', 'consensus_target_price': 'REAL',
        'esg_score': 'REAL', 'esg_rating': 'TEXT', 'esg_environment': 'REAL',
        'esg_social': 'REAL', 'esg_governance': 'REAL', 'esg_year': 'INTEGER',
    }
    m = DatabaseManager.get_instance()
    with m._engine.connect() as conn:
        existing = {r[1] for r in conn.execute(sa_text("PRAGMA table_info(company_profile)")).fetchall()}
        for col, ctype in new_cols.items():
            if col not in existing:
                conn.execute(sa_text(f"ALTER TABLE company_profile ADD COLUMN {col} {ctype}"))
        conn.commit()
    logger = logging.getLogger(__name__)
    logger.info("ensured consensus/esg columns; missing added=%d", sum(1 for c in new_cols if c not in existing))


def enrich_consensus_esg(online_consensus: bool = False) -> None:
    """对公司表补充一致预期与 ESG。仅填充 None 字段，避免覆盖已有真值。

    离线默认：consensus_eps 用 净利润/总股本 推导(TTM，标注内部估算)；ESG 留空。
    联网(--online-consensus)：真在线拉取机构盈利预测/评级；ESG 走全量缓存。
    """
    from data_provider.consensus_esg_fetcher import (
        build_esg_cache, get_consensus, get_esg, _estimate_consensus,
    )
    if online_consensus:
        build_esg_cache()  # 在线拉全市场 ESG 并落地缓存（失败静默，离线走估算）
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = s.query(CompanyProfile).all()
        total = len(rows)
        done = 0
        for row in rows:
            prof = row.to_dict()
            c = get_consensus(row.code, prof) if online_consensus else _estimate_consensus(prof)
            for fld, key in (
                ('consensus_year', 'year'), ('consensus_eps', 'eps'), ('consensus_eps_growth', 'eps_growth'),
                ('consensus_net_profit', 'net_profit'), ('consensus_revenue', 'revenue'),
                ('consensus_rating', 'rating'), ('consensus_institutes', 'institutes'),
                ('consensus_target_price', 'target_price'),
            ):
                if getattr(row, fld) is None and c.get(key) is not None:
                    setattr(row, fld, c.get(key))
            e = get_esg(row.code, prof)
            for fld, key in (
                ('esg_score', 'score'), ('esg_rating', 'rating'), ('esg_environment', 'environment'),
                ('esg_social', 'social'), ('esg_governance', 'governance'), ('esg_year', 'year'),
            ):
                if getattr(row, fld) is None and e.get(key) is not None:
                    setattr(row, fld, e.get(key))
            done += 1
            if done % 50 == 0:
                print(f"  enrich {done}/{total}")
        s.commit()
    print(f"=== 一致预期/ESG 补充完成: {done} 家 (online_consensus={online_consensus}) ===")


if __name__ == '__main__':
    main()
