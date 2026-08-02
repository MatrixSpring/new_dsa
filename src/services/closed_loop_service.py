# -*- coding: utf-8 -*-
"""一键闭环编排（DSA-BACKTRACE-V1.0 收尾闭环，外挂微服务，不改动 DSA 内核）。

把已完成的三大增强模块编排为单次调用的一条龙链路：

  阶段一  Agent 自主深挖（#16）→ 拉升前隐藏早期信号（机构调研/产业链异动/舆情/游资）
  阶段二  因子正向预判（#17）→ 把深挖信号类型对齐因子库，输出置信度加权上涨概率
  阶段三  因子 → DSA 内核传导（#18）→ 把命中因子转为桥接权重，注入四周期正向传导

设计原则（对齐 §7 决策权坚守）：
  - 全部数学编排，不依赖 LLM 主观臆断；
  - 沙箱无外网 / 无 LLM key，信号源与因子统计走确定性 mock，接口契约不变；
  - DSA 内核 propagate_shock 零改动，传导增益经由既有幅度放大通道注入，向后兼容。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services.agent_signal_service import agent_dig, _find_pool_stock
from src.services.factor_library_service import predict_with_factors
from src.services.factor_propagation_service import forecast_with_factors

logger = logging.getLogger(__name__)

# 产业链沙盘数据路径（与 industry_chain 端点复用同一份内置链数据）。
_DATA_PATH = Path(__file__).resolve().parents[2] / 'src' / 'data' / 'industry_chain_sandbox_data.json'

# 行业关键词 → 内置产业链沙盘 id（闭环演示用；真实环境按标的申万行业匹配 xzsc 链）。
_CHAIN_KEYWORDS: Dict[str, List[str]] = {
    'semiconductor': ['半导体', '芯片', 'ic', '集成', '晶圆'],
    'photovoltaic': ['光伏', '太阳能', '逆变器'],
}


def _resolve_chain_id(stock_code: str, chain_id: Optional[str]) -> str:
    """确定闭环传导所用的产业链：显式指定优先；否则按标的行业关键词推断。"""
    if chain_id:
        return chain_id
    st = _find_pool_stock(stock_code)
    ind = (st or {}).get('industry', '') or ''
    low = ind.lower()
    for cid, kws in _CHAIN_KEYWORDS.items():
        if any(k.lower() in low for k in kws):
            return cid
    return 'lithium'  # 新能源 / 锂电 / 电池 / 储能 默认


def _load_graph(chain_id: str) -> Optional[Dict[str, Any]]:
    """读取内置产业链沙盘图谱（仅含节点 / 边 / 公司，供 forecast_with_factors 使用）。"""
    try:
        with open(_DATA_PATH, 'r', encoding='utf-8') as f:
            sandbox = json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.warning('读取产业链沙盘失败: %s', exc)
        return None
    c = sandbox.get('INDUSTRY_CHAINS', {}).get(chain_id)
    if not c:
        return None
    return {
        'id': chain_id,
        'name': c.get('name'),
        'nodes': c.get('nodes', []),
        'edges': c.get('edges', []),
        'companies': c.get('companies', {}),
    }


def _weights_from_matched(matched: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把命中因子转为桥接权重（按期望净收益归一化），直接 feed 进 forecast_with_factors。

    命中条目来自 predict_with_factors，已含 factorName/factorCategory/avgWinRate/
    confidence/expectancy1m，与 forecast_with_factors 的 weights_list 契约一致。
    """
    if not matched:
        # 兜底：无命中则不注入增益（退化为基线传导）
        return []
    raw = [max(0.0, float(m.get('expectancy1m', 0))) for m in matched]
    s = sum(raw) or 1.0
    out: List[Dict[str, Any]] = []
    for m, rw in zip(matched, raw):
        out.append({
            'factorName': m['factorName'],
            'factorCategory': m.get('factorCategory', '综合'),
            'weight': round(rw / s, 4),
            'avgWinRate': m.get('avgWinRate', 0),
            'confidence': m.get('confidence', 0),
            'expectancy1m': m.get('expectancy1m', 0),
        })
    return out


def run_closed_loop(stock_code: str, chain_id: Optional[str] = None,
                    persist_attribution: bool = True) -> Dict[str, Any]:
    """一键闭环：Agent 深耕 → 正向预判 → 内核传导 全自动链路。

    Returns: {code, msg, data:{ stockCode, stockName, chainId, shockNode,
              dig, predict, propagate, attribution, engine, generatedAt }}
      - dig:        Agent 深挖结果（#16）
      - predict:    正向预判结果（#17）
      - propagate:  因子 → DSA 内核正向传导结果（#18）
      - attribution: 本次闭环的真实反向归因（落库 BacktraceAttribution，喂给因子库）

    设计原则补充（#24 数据驱动）：
      - 闭环扫描（#20/#21）逐只跑闭环时，persist_attribution=True 会把真实归因沉淀进
        BacktraceAttribution；因子库 _db_mined_factors 据此从「仅预设基线」升级为
        「预设基线 + 生产真实归因累积」，实现高频因子自动沉淀（反向归因 → 因子沉淀闭环）。
      - 归因落库失败不影响主链路（兜底 warn）。
    """
    # 阶段一：Agent 自主深挖
    dig = agent_dig(stock_code)
    if dig.get('code') != 0:
        return dig  # 透传未找到标的等错误
    dig_data = dig['data']

    # 阶段二：因子正向预判（深挖信号类型直接作为 early signals 对齐因子库）
    signal_types = list(dig_data.get('typeDistribution', {}).keys())
    pred = predict_with_factors(signal_types, stock_code)
    pred_data = pred.get('data') or {}
    matched = pred_data.get('matched', []) or []

    # 阶段三：因子 → DSA 内核传导（命中因子转为桥接权重）
    cid = _resolve_chain_id(stock_code, chain_id)
    graph = _load_graph(cid)
    if graph is None:
        return {'code': 4, 'msg': f'未找到产业链: {cid}', 'data': None}
    weights = _weights_from_matched(matched)
    shock_node = graph['nodes'][0]['label'] if graph.get('nodes') else '锂矿'
    shock = {'node': shock_node, 'magnitude': 0.3, 'kind': 'demand'}
    fc = forecast_with_factors(graph, shock, weights_list=weights)
    fc_data = fc.get('data', {})

    # —— #24 数据驱动沉淀：把本次闭环的真实反向归因落库（喂给因子库 _db_mined_factors）——
    attribution_result = None
    if persist_attribution:
        try:
            from src.services.backtrace_service import attribute as _attribute
            attr_resp = _attribute(stock_code)
            if attr_resp.get('code') == 0:
                attribution_result = attr_resp.get('data')
        except Exception as exc:  # noqa: BLE001
            logger.warning('闭环归因落库失败（不影响主链路）: %s', exc)

    result = {
        'stockCode': stock_code,
        'stockName': dig_data.get('stockName'),
        'chainId': cid,
        'shockNode': shock_node,
        'dig': dig_data,
        'predict': pred_data,
        'propagate': fc_data,
        'attribution': attribution_result,
        'engine': 'backtrace-closed-loop',
        'generatedAt': datetime.now().isoformat(timespec='seconds'),
    }
    return {'code': 0, 'msg': 'ok', 'data': result}
