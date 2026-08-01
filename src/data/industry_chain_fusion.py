# -*- coding: utf-8 -*-
"""
========================================================
产业链数据融合 — 新质生产力(xzsc) ↔ 申万(252 L3) 交叉映射与增强
========================================================

背景：
- xzsc（新质生产力，58 条）：主题赛道分类(no/name/l1/l2/summary/segments 上下游环节拓扑)，
  本身不含上市公司，仅 3 条内置沙盘链自带 companies。
- 申万（252 条 L3）：官方行业分类(code/l1/l2/l3/upstream/downstream/leaders 龙头公司名/factors 因子)，
  含真实龙头公司名（仅 29 条 L3 带 leaders），但无股票代码、无上下游环节拓扑。
- 两套分类体系完全不同、无共享主键，故采用「关键词/环节名子串匹配」建立桥接，而非按主键 union。

本模块职责（L2 融合）：
1. 加载 data/cache/stocks.index.json（名称/别名 → 6 位代码），把申万龙头公司名解析成代码；
2. 用 xzsc 链的 名称/l2/环节名 作为关键词，子串匹配申万 L3 的 l3_name/upstream/downstream，建立 xzsc → 申万 映射；
3. 把匹配到的申万龙头公司（已解析代码）挂到 xzsc 图谱中 label 相匹配的节点，给 xzsc 链补真实上市公司；
4. 反向：给申万 L3 标注其所属 xzsc 主题（shenwan_xzsc）；
5. 提供中文感知的 match_shenwan_by_text，修复 impact_analyzer 原 shenwan_chains 断链。
"""
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 股票名称 → 代码 索引（data/cache/stocks.index.json）
#    数组结构: [full_code, code(6位), name, pinyin, abbr, [aliases], "CN", "stock", bool, int]
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_stock_name_index() -> Dict[str, str]:
    """返回 {股票名称/别名: 6 位代码} 映射。"""
    path = Path(__file__).resolve().parents[2] / 'data' / 'cache' / 'stocks.index.json'
    index: Dict[str, str] = {}
    try:
        arr = json.load(open(path, 'r', encoding='utf-8'))
    except Exception as exc:  # noqa: BLE001
        logger.warning('加载 stocks.index.json 失败: %s', exc)
        return index
    for row in arr:
        if not isinstance(row, list) or len(row) < 3:
            continue
        code = str(row[1])
        name = row[2]
        aliases = row[5] if len(row) > 5 and isinstance(row[5], list) else []
        if name and name not in index:
            index[name] = code
        for al in aliases:
            if al and al not in index:
                index[al] = code
    return index


def resolve_company_codes(names: List[str]) -> List[Dict[str, Any]]:
    """把公司名称列表解析为 [{name, code}]；code 为 None 表示未解析到。"""
    idx = load_stock_name_index()
    out: List[Dict[str, Any]] = []
    seen = set()
    for n in names:
        n = (n or '').strip()
        if not n:
            continue
        code = idx.get(n)
        key = code or n
        if key in seen:
            continue
        seen.add(key)
        out.append({'name': n, 'code': code})
    return out


# ---------------------------------------------------------------------------
# 2. 申万 L3 数据（全量，来自 sw_industry_chain_dict）
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_shenwan_items() -> List[Dict[str, Any]]:
    from src.data.sw_industry_chain_dict import SW_CHAIN_DICT, LEADERS_FACTORS

    items: List[Dict[str, Any]] = []
    for it in SW_CHAIN_DICT['items']:
        lf = LEADERS_FACTORS.get(it.get('l3_name', ''), {}) or {}
        items.append({
            'code': it.get('code'),
            'l1': it.get('l1_name'),
            'l2': it.get('l2_name'),
            'l3': it.get('l3_name'),
            'upstream': it.get('upstream') or [],
            'downstream': it.get('downstream') or [],
            'leaders': [x.strip() for x in (lf.get('leaders') or '').split(',') if x.strip()],
            'factors': [x.strip() for x in (lf.get('factors') or '').split(',') if x.strip()],
        })
    return items


def _shenwan_terms(it: Dict[str, Any]) -> List[str]:
    """用于 xzsc→申万 匹配的术语集合（l3 + 上下游 + 龙头公司名）。"""
    return [t for t in ([it['l3']] + it['upstream'] + it['downstream'] + it['leaders']) if t]


# ---------------------------------------------------------------------------
# 3. xzsc → 申万 融合（映射 + 公司增强）
# ---------------------------------------------------------------------------
def _xzsc_keywords(chain: Dict[str, Any]) -> List[str]:
    """从 xzsc 链抽取匹配关键词：名称 + l2 + 全部环节名。"""
    kws: List[str] = [chain.get('name') or '', chain.get('l2') or '']
    segs = chain.get('segments')
    if isinstance(segs, str):
        try:
            segs = json.loads(segs)
        except (ValueError, TypeError):
            segs = None
    if isinstance(segs, dict):
        for v in segs.values():
            if isinstance(v, list):
                kws.extend(str(x) for x in v)
    return [k.strip() for k in kws if k and k.strip()]


# ---------------------------------------------------------------------------
# 3.1 Curated 主题链公司映射（L2 增强：补全 0 公司主题链）
# ---------------------------------------------------------------------------
# 19 条主题型 xzsc 链，其匹配的申万 L3 未带 leaders 标签，故无法经自动匹配获得上市公司。
# 此处人工梳理「链 no -> [(公司名, 环节提示)]」，环节提示对应该链图谱中真实存在的节点 label，
# 使公司能精确挂到对应环节节点；名称经 stocks.index.json 解析为代码（见 resolve_company_codes）。
CURATED_XZSC_COMPANIES: Dict[str, List[Any]] = {
    '1': [  # 元宇宙
        ('歌尔股份', '显示面板'), ('水晶光电', '光学器件'), ('中科创达', '引擎'),
        ('蓝色光标', '社交'), ('昆仑万维', '游戏'), ('三七互娱', '游戏'),
        ('芒果超媒', '社交'), ('风语筑', '数字孪生平台'),
    ],
    '2': [  # 算力
        ('中科曙光', '服务器'), ('工业富联', '服务器'), ('浪潮信息', '服务器'),
        ('寒武纪', 'CPU/GPU/DPU'), ('海光信息', 'CPU/GPU/DPU'), ('紫光股份', '交换机'),
        ('新易盛', '光模块'), ('中际旭创', '光模块'), ('天孚通信', '光模块'),
    ],
    '3': [  # 数商（数据要素）
        ('广电运通', '数据交易所'), ('深桑达A', '数据存储'), ('太极股份', '行业应用'),
        ('人民网', '数据资产化'), ('新华网', '数据资产化'), ('上海钢联', '行业应用'),
        ('每日互动', '数据采集'),
    ],
    '5': [  # 人工智能
        ('科大讯飞', '大模型'), ('三六零', '大模型'), ('昆仑万维', '大模型'),
        ('寒武纪', '算力'), ('虹软科技', '算法'), ('拓维信息', '行业应用'),
        ('金山办公', '行业应用'),
    ],
    '7': [  # 类器官芯片
        ('药明康德', '药物筛选'), ('泰格医药', '药物筛选'), ('昭衍新药', '毒理'),
        ('康龙化成', '药物筛选'), ('美迪西', '药物筛选'), ('华大智造', '微流控芯片'),
        ('义翘神州', '生物材料'),
    ],
    '9': [  # 量子通信
        ('国盾量子', 'QKD设备'), ('亨通光电', '量子中继'), ('神州信息', '专网安全'),
        ('光迅科技', '探测器'), ('迪普科技', '专网安全'),
    ],
    '13': [  # 抽蓄电站
        ('东方电气', '水轮机'), ('广东建工', 'EPC建设'), ('浙富控股', '水轮机'),
        ('国电南瑞', '电网调峰'),
    ],
    '16': [  # 航空发动机零部件
        ('航发动力', '整机厂'), ('航发控制', '整机厂'), ('航发科技', '精密铸造'),
        ('应流股份', '叶片'), ('钢研高纳', '高温合金'), ('图南股份', '高温合金'),
        ('中航重机', '精密铸造'), ('抚顺特钢', '高温合金'),
    ],
    '17': [  # 化妆品
        ('珀莱雅', '品牌'), ('贝泰妮', '品牌'), ('上海家化', '品牌'),
        ('丸美生物', '品牌'), ('水羊股份', '品牌'), ('青松股份', '代工/OEM'),
        ('华熙生物', '原料'), ('科思股份', '原料'),
    ],
    '19': [  # 锂电池涂覆材料
        ('壹石通', '勃姆石'), ('璞泰来', '涂覆加工'), ('恩捷股份', '隔膜'),
        ('星源材质', '隔膜'), ('昊华科技', 'PVDF'), ('东阳光', 'PVDF'),
        ('巨化股份', 'PVDF'),
    ],
    '34': [  # 食品饮料
        ('贵州茅台', '渠道'), ('五粮液', '渠道'), ('伊利股份', '加工'),
        ('海天味业', '加工'), ('泸州老窖', '渠道'), ('洋河股份', '渠道'),
        ('山西汾酒', '渠道'), ('东鹏饮料', '加工'),
    ],
    '41': [  # 新零售
        ('永辉超市', '全渠道'), ('王府井', '全渠道'), ('红旗连锁', '即时零售'),
        ('家家悦', '即时零售'), ('百联股份', '全渠道'), ('壹网壹创', '数字化中台'),
    ],
    '44': [  # 新基建-特高压
        ('特变电工', '变压器'), ('许继电气', '换流阀'), ('国电南瑞', '换流阀'),
        ('中国西电', '变压器'), ('平高电气', '工程建设'), ('保变电气', '变压器'),
        ('思源电气', '套管'), ('东方电缆', '线缆'),
    ],
    '45': [  # 新基建-工业互联网
        ('用友网络', '工业软件'), ('宝信软件', '平台'), ('东方国信', '工业软件'),
        ('工业富联', '平台'), ('中控技术', '工业软件'), ('赛意信息', '工业软件'),
        ('汉得信息', '工业软件'),
    ],
    '46': [  # 新基建-大数据
        ('数据港', '存储'), ('奥飞数据', '存储'), ('宝信软件', '行业应用'),
        ('云赛智联', '存储'), ('拓尔思', '行业应用'), ('太极股份', '行业应用'),
        ('海量数据', '计算'),
    ],
    '47': [  # 新基建-人工智能
        ('科大讯飞', '大模型平台'), ('寒武纪', '算力'), ('中科曙光', '算力'),
        ('海光信息', '算力'), ('虹软科技', '行业赋能'), ('拓维信息', '行业赋能'),
        ('金山办公', '行业赋能'),
    ],
    '53': [  # 3D玻璃
        ('蓝思科技', '热弯'), ('凯盛科技', '玻璃基板'), ('长信科技', '手机'),
        ('沃格光电', '玻璃基板'), ('信濠光电', '玻璃基板'),
    ],
    '54': [  # 触摸屏
        ('莱宝高科', 'ITO'), ('长信科技', '触控模组'), ('欧菲光', '触控模组'),
        ('超声电子', '触控模组'), ('蓝思科技', '盖板'),
    ],
    '56': [  # 航空发动机
        ('航发动力', '总装'), ('航发控制', '控制系统'), ('航发科技', '叶片'),
        ('钢研高纳', '高温合金'), ('图南股份', '高温合金'), ('抚顺特钢', '高温合金'),
        ('万泽股份', '高温合金'), ('应流股份', '叶片'),
    ],
}


def build_xzsc_shenwan_fusion(xzsc_chains: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    建立 xzsc 链 ↔ 申万 L3 链的融合结果。

    Returns:
        {
          "chains": {
             str(no): {
                "matches": [{"code","l1","l2","l3","terms":[...],"companies":[{name,code}]}],
                "allCompanies": [{name,code}],          # 去重后的全链公司
                "shenwanRefs": [{code,l1,l2,l3}],
                "matchCount": int
             }
          },
          "shenwan_xzsc": { shenwan_code: [{"no","name"}, ...] }   # 反向标注
        }
    """
    sw_items = load_shenwan_items()
    sw_terms_cache = [(it, _shenwan_terms(it)) for it in sw_items]

    chains_out: Dict[str, Any] = {}
    shenwan_xzsc: Dict[str, List[Dict[str, Any]]] = {}

    for ch in xzsc_chains:
        no = str(ch.get('no'))
        kws = _xzsc_keywords(ch)
        matches: List[Dict[str, Any]] = []
        for it, terms in sw_terms_cache:
            if any(kw and kw in ' '.join(terms) for kw in kws):
                companies = resolve_company_codes(it['leaders'])
                matches.append({
                    'code': it['code'],
                    'l1': it['l1'],
                    'l2': it['l2'],
                    'l3': it['l3'],
                    'terms': terms,
                    'companies': companies,
                })
        # ---- curated 补充：把人工梳理的主题链公司作为独立 match 注入 ----
        for (cname, hint) in CURATED_XZSC_COMPANIES.get(no, []):
            resolved = resolve_company_codes([cname])
            if resolved and resolved[0].get('code'):
                matches.append({
                    'code': 'CURATED',
                    'l1': ch.get('l1'), 'l2': ch.get('l2'), 'l3': ch.get('name'),
                    'terms': [hint] if hint else [],
                    'companies': resolved,
                    'curated': True,
                })

        all_companies = resolve_company_codes(
            [c['name'] for m in matches for c in m['companies']]
        )
        real_matches = [m for m in matches if not m.get('curated')]
        curated_matches = [m for m in matches if m.get('curated')]
        chains_out[no] = {
            'matches': matches,
            'allCompanies': all_companies,
            'shenwanRefs': [{'code': m['code'], 'l1': m['l1'], 'l2': m['l2'], 'l3': m['l3']} for m in real_matches],
            'curatedRefs': [{'no': ch.get('no'), 'name': ch.get('name'), 'count': len(m['companies'])} for m in curated_matches],
            'matchCount': len(real_matches),
            'curatedCount': len(curated_matches),
        }
        for m in real_matches:
            shenwan_xzsc.setdefault(m['code'], []).append({'no': ch.get('no'), 'name': ch.get('name')})

    return {'chains': chains_out, 'shenwan_xzsc': shenwan_xzsc}


# ---------------------------------------------------------------------------
# 4. 中文感知的申万匹配（修复 impact_analyzer 的 shenwan_chains 断链）
# ---------------------------------------------------------------------------
def match_shenwan_by_text(text: str, top_n: int = 5) -> List[Dict[str, Any]]:
    """
    给定文章正文，返回命中的申万 L3 链（按命中术语数降序）。

    匹配方式：申万链的 l3_name / upstream / downstream / 龙头公司名 是否作为子串出现在 text 中
    （中文无需空格分词）。命中术语过短(单字)的忽略以降低噪声。
    """
    text = text or ''
    scored: List[tuple] = []
    for it in load_shenwan_items():
        terms = [it['l3']] + it['upstream'] + it['downstream'] + it['leaders']
        hits = sum(1 for t in terms if len(t) >= 2 and t in text)
        if hits:
            scored.append((hits, it))
    scored.sort(key=lambda x: -x[0])
    return [
        {
            'code': it['code'], 'l1': it['l1'], 'l2': it['l2'], 'l3': it['l3'],
            'leaders': it['leaders'], 'factors': it['factors'], 'match': h,
        }
        for h, it in scored[:top_n]
    ]


if __name__ == '__main__':
    # 简易自测
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.data.xzsc_chain import XZSC_CHAINS
    fusion = build_xzsc_shenwan_fusion(XZSC_CHAINS)
    n_with = sum(1 for v in fusion['chains'].values() if v['allCompanies'])
    print(f'xzsc 链总数: {len(fusion["chains"])}')
    print(f'获得上市公司的链: {n_with}')
    for no, v in list(fusion['chains'].items())[:6]:
        names = [c['name'] for c in v['allCompanies']]
        print(f'  no={no} 匹配申万 {v["matchCount"]} 条 -> 公司 {names[:6]}')
