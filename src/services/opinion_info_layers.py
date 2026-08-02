"""六层信息圈层模型（L0~L5，蓝图 §四）与多源交叉验证共享常量。

本模块是**共享契约**（架构文档 §3），供所有可插拔信号源打标与 DSA 推演规则引用。
区别于 #34~#37 的「信号源」实现，本模块是**元分析层**：把已落地的七路源归入可信圈层，
供交叉验证（`opinion_cross_validation`）消费，不扩张候选池、不改变内核决策权。

固定扩散链（蓝图 §四）：私密圈萌芽 → 券商/小众号发文 → 财联社快讯 → 雪球/淘股吧发酵 →
股吧/普通号转载 → 头条/抖音刷屏（见顶）。
"""
from __future__ import annotations

from typing import Any, Dict

# —— §3 六层信息圈层定义（L0~L5）——
INFO_LAYERS: Dict[str, Dict[str, Any]] = {
    'L0': {
        'name': '顶层产业知情',
        'audience': '高管 / 产业链核心',
        'horizon': '30~45 天',
        'stage': '底部缓建仓',
        'role': '异动观察池，长线参考',
        'tier': 0,
    },
    'L1': {
        'name': '机构专业层',
        'audience': '公募 / 私募 / 游资 / 研究员',
        'horizon': '7~15 天',
        'stage': '拉升初期',
        'role': '核心做多跟踪',
        'tier': 1,
    },
    'L2': {
        'name': '专业交易者',
        'audience': '短线高手 / 资深散户',
        'horizon': '3~7 天',
        'stage': '主升浪起点',
        'role': '短线重点预判',
        'tier': 2,
    },
    'L3': {
        'name': '深度散户层',
        'audience': '复盘爱好者',
        'horizon': '0~3 天',
        'stage': '上涨中段',
        'role': '谨慎追高',
        'tier': 3,
    },
    'L4': {
        'name': '普通散户层',
        'audience': '绝大多数股民',
        'horizon': '滞后 1~5 天',
        'stage': '高位狂热',
        'role': '风险预警减仓',
        'tier': 4,
    },
    'L5': {
        'name': '场外路人',
        'audience': '新手',
        'horizon': '滞后 1 周+',
        'stage': '行情尾声',
        'role': '强烈看空推演',
        'tier': 5,
    },
}

# 圈层分组（用于 §4 交叉验证）
AUTHORITATIVE_TIERS = {'L0', 'L1'}   # 官方公告 + 机构研报/海外权威：基本面与长线定价权
PROFESSIONAL_TIERS = {'L2'}           # 快讯 + 高质量社区：专业短线节奏
RETAIL_TIERS = {'L3', 'L4', 'L5'}     # 私域圈层 + 公域散户 + 场外：仅情绪参考

# 各可插拔源 → 圈层映射（#35 Kronos 技术面算力底座不属于信息圈层，单独标注为技术确认）
SOURCE_LAYER_MAP: Dict[str, Dict[str, Any]] = {
    'disclosure': {'layer': 'L0', 'label': '法定权威披露（巨潮 / 交易所）', 'tier': 'authoritative'},
    'overseas': {'layer': 'L1', 'label': '海外权威（彭博 / 路透 / WSJ / Seeking Alpha）', 'tier': 'authoritative'},
    'flash': {'layer': 'L2', 'label': '短线快讯（财联社 / 华尔街见闻 / 金十）', 'tier': 'professional'},
    'community': {'layer': 'L2/L3', 'label': '深度社区（雪球高质量=L2 / 股吧淘股吧噪音=L3）', 'tier': 'mixed'},
    'wechat': {'layer': 'L3', 'label': '微信私域圈层（#31）', 'tier': 'retail'},
    'opinion': {'layer': 'L4', 'label': '头条公域舆情（#28）', 'tier': 'retail'},
    'kronos': {'layer': None, 'label': 'K 线技术面算力底座（#35，非信息圈层 · 技术确认）', 'tier': 'technical'},
}

# §4 可信度量化阈值（蓝图文案固化）
CRED_SINGLE_RETAIL_CAP = 0.30   # 单一自媒体 / 散户爆料：可信度 ≤ 0.3，大幅降权
CRED_SINGLE_AUTH = 0.50         # 单一权威源：中等可信
CRED_MULTI_AUTH_FLOOR = 0.70    # 2+ 独立权威平台同步印证：可信度下限（§4 → 0.7~0.9）
CRED_MULTI_AUTH_CEIL = 0.90     # 2+ 独立权威平台同步印证：可信度上限

# 方向权重（共识计算时各圈层话语权：权威 > 专业 > 散户）
TIER_DIRECTION_WEIGHT = {'L0': 1.0, 'L1': 1.0, 'L2': 0.6, 'L3': 0.4, 'L4': 0.4, 'L5': 0.2}


def describe_info_layers() -> Dict[str, Any]:
    """返回 §3 六层信息圈层定义 + 各源映射 + §4 可信度阈值，供 API / 前端渲染圈层矩阵。"""
    return {
        'layers': INFO_LAYERS,
        'sourceLayerMap': SOURCE_LAYER_MAP,
        'authoritativeTiers': sorted(AUTHORITATIVE_TIERS),
        'retailTiers': sorted(RETAIL_TIERS),
        'credibilityThresholds': {
            'singleRetailCap': CRED_SINGLE_RETAIL_CAP,
            'singleAuth': CRED_SINGLE_AUTH,
            'multiAuthFloor': CRED_MULTI_AUTH_FLOOR,
            'multiAuthCeil': CRED_MULTI_AUTH_CEIL,
        },
    }
