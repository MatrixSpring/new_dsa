# -*- coding: utf-8 -*-
"""可插拔 K 线技术面算力底座（DSA-KRONOS-V1.0 #35，外挂微服务，不改动 DSA 内核）。

把 Kronos（清华大学开源、AAAI2026 收录的全球首个金融 K 线专用时序基础大模型，
GitHub: shiyu-coder/Kronos，HuggingFace 权重 NeoQuasar）作为 DSA 反向归因系统的
【技术面统一算力底座】接入（用户「Kronos 完整解析 + 系统集成全方案」蓝图）：

  - 沙箱（默认）：走确定性 mock，按股票代码 hash 生成稳定的技术面信号，接口契约不变，
    全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_KRONOS=1 后，切换为 Kronos 模型推理
    （NeoQuasar 权重 + BSQ 球面量化 Tokenizer + 分层因果 Transformer 自回归架构，
    见蓝图 §一/§二）；若为部署模型权重 / torch / transformers 缺失，**优雅回退**
    mock 并记录原因，保证回溯闭环在任意环境都能运转。

与 #23~#34 信号源的本质区别（关键设计决策，见 docs/backtrace-kronos-architecture.md）：
  - #25 披露 / #28 头条舆情 / #31 微信舆情 / #34 短线快讯 都是「事件 / 情绪催化源」，
    在 watchlist=None 时把各自事件池标的**叠加（union）进闭环扫描候选池**；
  - Kronos 是**逐只股票的技术面算力底座**，不对扫描候选池做 union 扩张，而是对
    已扫描出的每只 alert **富化技术面信号（kronosInfo）**：趋势 / 拐点 /
    上涨·横盘·下跌三态概率 / 波动率 / 量能评分 / 持续性 / Alpha 因子；并独立输出
    三类选股池（短线强势池 / 趋势反转池 / 风险预警池）供业务层消费（蓝图 §四 能力1）。

设计原则（对齐蓝图 §七 风控硬性约束）：
  - Kronos 仅输出技术参考信号，**最终涨跌量化、中长期结论依旧由 DSA 数学模型决定**；
  - K 线信号权重设硬上限：短线最高 0.35、长线最高 0.15（KRONOS_WEIGHT_SHORT_CAP /
    KRONOS_WEIGHT_LONG_CAP），基本面与公告优先级恒最高；
  - 所有新增 Alpha 因子必须经历史回测验证方可入库（蓝图 §七 防过拟合），本模块只产出
    候选因子，不自动入库；
  - 不影响 DSA 内核 propagate_shock / run_closed_loop 任何逻辑；切换零代码改动，
    仅通过环境变量控制，向后兼容既有 mock 行为；
  - 极端政策 / 突发黑天鹅优先采信事件舆情，弱化 K 线预判（蓝图 §七）。

文档 §一/§二 模型底座与权重（接入 DSA，固定参数 / 上限）：
  - 模型家族：mini(4.1M)/small/base/large(499.2M)，权重族名 NeoQuasar；
  - 上下文窗口 512 根 K 线；BSQ 球面量化 Tokenizer（粗粒度大趋势 + 细粒度短期波动）；
  - 概率多路径预测：输出上涨 / 横盘 / 下跌三态概率分布，适配风控场景；
  - 短线 K 线信号权重上限 0.35、长线上限 0.15（§七）。
"""
from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import random
from typing import Any, Dict, List, Optional

from src.storage import BacktraceKronosSignal, BacktraceScreenPool, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

_ENV_KEY = 'DSA_REALTIME_KRONOS'

# §七 风控硬约束：K 线信号权重硬上限（不主导基本面 / 公告）
KRONOS_WEIGHT_SHORT_CAP = 0.35   # 短线 K 线信号权重最高 0.35
KRONOS_WEIGHT_LONG_CAP = 0.15    # 长线 K 线信号权重最高 0.15

# 模型底座（蓝图 §一/§二）
KRONOS_REPO = 'shiyu-coder/Kronos'
KRONOS_WEIGHTS = 'NeoQuasar'
KRONOS_MODEL_FAMILY = 'NeoQuasar（AAAI2026 金融 K 线基础模型）'
KRONOS_MODEL_SPEC = 'small（P0 轻量化部署，4 档规格 mini/small/base/large）'
KRONOS_CONTEXT_WINDOW = 512      # 最大上下文窗口（根 K 线）


class ProviderUnavailable(Exception):
    """Kronos 模型推理暂不可用（未部署权重 / 缺 torch / transformers / 显存不足）。"""


# —— 确定性 mock 技术面信号生成（按股票代码 hash 稳定分布，保证沙箱可复现）——
_TRENDS = ['多头趋势', '空头趋势', '震荡']
_INFLECTIONS = ['无顶部拐点', '顶部拐点·高位见顶', '底部拐点·下跌末端反转']


def _seeded(code: str) -> random.Random:
    h = int(hashlib.md5(str(code).encode('utf-8')).hexdigest(), 16)
    return random.Random(h)


def _normalize_probs(a: float, b: float, c: float) -> List[float]:
    s = a + b + c
    if s <= 0:
        return [0.33, 0.34, 0.33]
    return [round(x / s, 3) for x in (a, b, c)]


def analyze_stock(stock_code: str, stock_name: Optional[str] = None) -> Dict[str, Any]:
    """对单只标的生成 K 线技术面信号（mock 确定性 / 真实环境由 Kronos 模型推理）。

    返回 camelCase 字典（与 BacktraceKronosSignal.to_dict 字段一致），下游 UI 直接消费：
      trend(多头趋势/空头趋势/震荡), momentum(0~1 趋势强度), inflectionPoint(拐点),
      riseProb/sidewayProb/downProb(三态概率分布，和≈1), volatility(0~1),
      volumeScore(0~1 量能评分), persistence(持续性文本),
      factorScores([{name, score}]) 由 BSQ Tokenizer 隐向量派生的候选 Alpha 因子。
    """
    rng = _seeded(stock_code)
    bucket = rng.randint(0, 2)   # 0=强势多头 / 1=高位顶部风险 / 2=底部反转
    if bucket == 0:
        trend = '多头趋势'
        inflection = '无顶部拐点'
        rp, sp, dp = _normalize_probs(0.62 + rng.random() * 0.25, 0.18 + rng.random() * 0.12, 0.05 + rng.random() * 0.1)
        persistence = '中期上升趋势，量价配合，可持续 1~2 周'
    elif bucket == 1:
        trend = '空头趋势' if rng.random() < 0.5 else '震荡'
        inflection = '顶部拐点·高位见顶'
        rp, sp, dp = _normalize_probs(0.12 + rng.random() * 0.12, 0.18 + rng.random() * 0.12, 0.55 + rng.random() * 0.25)
        persistence = '高位结构松动，警惕回落，建议减仓规避追涨'
    else:
        trend = '震荡'
        inflection = '底部拐点·下跌末端反转'
        rp, sp, dp = _normalize_probs(0.28 + rng.random() * 0.15, 0.32 + rng.random() * 0.12, 0.22 + rng.random() * 0.15)
        persistence = '下跌末端企稳，具备反转预期，关注试盘放量'

    momentum = round(0.35 + rng.random() * 0.55, 3)
    volatility = round(0.12 + rng.random() * 0.38, 3)
    volume_score = round(0.25 + rng.random() * 0.7, 3)

    factor_scores = [
        {'name': 'BSQ趋势强度因子', 'score': momentum},
        {'name': '分层量能因子', 'score': volume_score},
        {'name': '波动率压缩因子', 'score': round(1.0 - volatility, 3)},
        {'name': '拐点共振因子',
         'score': round(0.5 + (0.3 if ('顶部' in inflection or '底部' in inflection) else 0.0) + rng.random() * 0.2, 3)},
    ]
    return {
        'stockCode': str(stock_code),
        'stockName': stock_name,
        'trend': trend,
        'momentum': momentum,
        'inflectionPoint': inflection,
        'riseProb': rp,
        'sidewayProb': sp,
        'downProb': dp,
        'volatility': volatility,
        'volumeScore': volume_score,
        'persistence': persistence,
        'factorScores': factor_scores,
    }


class BaseKronosProvider:
    """统一 K 线技术面算力接口：对单只 / 批量标的输出技术面信号。"""

    label: str = 'base'

    def analyze(self, stock_code: str, stock_name: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def batch_analyze(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.analyze(i['stock_code'], i.get('stock_name')) for i in items]


class MockKronosProvider(BaseKronosProvider):
    """确定性模拟 Kronos：按代码 hash 生成稳定技术面信号，覆盖三类场景（强势/顶部风险/底部反转）。"""

    label = '模拟 Kronos 技术面底座（确定性 mock，无需模型权重）'

    def analyze(self, stock_code: str, stock_name: Optional[str] = None) -> Dict[str, Any]:
        return analyze_stock(stock_code, stock_name)


class KronosModelProvider(BaseKronosProvider):
    """真实 Kronos 模型推理（NeoQuasar 权重 + BSQ Tokenizer + 分层因果 Transformer）。

    仅在 DSA_REALTIME_KRONOS=1 时由工厂构造；缺失权重 / torch / transformers / 显存时
    明确抛 ProviderUnavailable，由调用方回退 Mock。沙箱无网络、无权重、无 GPU，故为 stub。
    """

    label = '实时 Kronos 模型推理（NeoQuasar 权重 + BSQ Tokenizer + 分层因果 Transformer）'

    def _model(self):
        try:
            importlib.import_module('torch')
            importlib.import_module('transformers')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'Kronos 模型依赖未就绪（需 torch + transformers + NeoQuasar 权重）：{e}')
        # 真实环境：加载 shiyu-coder/Kronos 权重 → 喂入 OHLCVA 序列 → BSQ 分词 →
        # 分层因果 Transformer 自回归预测 → 解析趋势 / 拐点 / 三态概率 / 波动率 / 因子。
        raise ProviderUnavailable('真实 Kronos 推理需在部署环境挂载 NeoQuasar 权重与 GPU；沙箱不可用')

    def analyze(self, stock_code: str, stock_name: Optional[str] = None) -> Dict[str, Any]:
        self._model()  # 确保依赖；否则抛 ProviderUnavailable
        raise ProviderUnavailable('真实 Kronos 推理需在部署环境挂载 NeoQuasar 权重与 GPU；沙箱不可用')


def get_kronos_provider() -> tuple[BaseKronosProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_KRONOS → (Mock, mock, 原因)
    - 开启但 torch/transformers 未部署 → (Mock, mock, 回退原因)
    - 开启且可用 → (KronosModel, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockKronosProvider(), MODE_MOCK, '沙箱确定性 Kronos 技术面底座（未开启 DSA_REALTIME_KRONOS）'
    try:
        importlib.import_module('torch')
    except Exception:  # noqa: BLE001
        return (
            MockKronosProvider(),
            MODE_MOCK,
            '已请求实时 Kronos，但 torch/transformers 未部署，已回退模拟技术面底座',
        )
    return KronosModelProvider(), MODE_REAL, '实时 Kronos 模型推理（NeoQuasar 权重 + BSQ Tokenizer + 分层因果 Transformer）——需挂载权重与 GPU'


def describe_kronos_source() -> Dict[str, Any]:
    """描述当前活跃 Kronos 技术面底座，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_kronos_provider()
    analyzed = 0
    try:
        m = DatabaseManager.get_instance()
        with m.session_scope() as s:
            analyzed = s.query(BacktraceKronosSignal).count()
    except Exception:  # noqa: BLE001
        analyzed = 0
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'modelFamily': KRONOS_MODEL_FAMILY,
        'modelSpec': KRONOS_MODEL_SPEC,
        'contextWindow': KRONOS_CONTEXT_WINDOW,
        'weightShortCap': KRONOS_WEIGHT_SHORT_CAP,
        'weightLongCap': KRONOS_WEIGHT_LONG_CAP,
        'analyzedCount': int(analyzed),
        'envKey': _ENV_KEY,
    }


def _screen_pool_codes() -> List[Dict[str, Any]]:
    """读取大涨回溯池标的（供批量技术面分析），缺失则返回空。"""
    m = DatabaseManager.get_instance()
    out: List[Dict[str, Any]] = []
    try:
        with m.session_scope() as s:
            for r in s.query(BacktraceScreenPool).all():
                out.append({'stock_code': str(r.stock_code), 'stock_name': r.stock_name})
    except Exception as e:  # noqa: BLE001
        logger.warning('读取大涨回溯池失败：%s', e)
    return out


def refresh_kronos(stock_codes: Optional[List[str]] = None) -> Dict[str, Any]:
    """批量技术面分析（真实环境 Kronos 模型 / 模拟环境确定性 mock），写入 BacktraceKronosSignal。

    返回 {code, msg, data:{ mode, provider, model, analyzed, shortTermStrong, reversal, riskWarning, reason }}。
    """
    provider, mode, reason = get_kronos_provider()
    if stock_codes:
        items = [{'stock_code': str(c), 'stock_name': None} for c in stock_codes]
    else:
        items = _screen_pool_codes()
    signals = provider.batch_analyze(items)
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceKronosSignal).delete()
        for sig in signals:
            s.add(BacktraceKronosSignal(
                stock_code=sig['stockCode'],
                stock_name=sig.get('stockName'),
                trend=sig.get('trend'),
                momentum=float(sig.get('momentum') or 0.0),
                inflection_point=sig.get('inflectionPoint'),
                rise_prob=float(sig.get('riseProb') or 0.0),
                sideway_prob=float(sig.get('sidewayProb') or 0.0),
                down_prob=float(sig.get('downProb') or 0.0),
                volatility=float(sig.get('volatility') or 0.0),
                volume_score=float(sig.get('volumeScore') or 0.0),
                persistence=sig.get('persistence'),
                factor_scores=json.dumps(sig.get('factorScores') or [], ensure_ascii=False),
            ))
        s.flush()
    # 选股池统计（蓝图 §四 能力1）
    strong = sum(1 for x in signals if x.get('trend') == '多头趋势' and (x.get('riseProb') or 0) >= 0.7)
    reversal = sum(1 for x in signals if '底部' in (x.get('inflectionPoint') or ''))
    risk = sum(1 for x in signals if '顶部' in (x.get('inflectionPoint') or '') or (x.get('downProb') or 0) >= 0.5)
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'model': KRONOS_WEIGHTS,
            'analyzed': len(signals),
            'shortTermStrong': int(strong),
            'reversal': int(reversal),
            'riskWarning': int(risk),
            'reason': reason,
        },
    }


def list_kronos() -> Dict[str, Any]:
    """查询当前 Kronos 技术面信号（按 id 倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = s.query(BacktraceKronosSignal).order_by(BacktraceKronosSignal.id.desc()).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'count': len(items), 'items': items}}


def kronos_pools() -> Dict[str, Any]:
    """输出三类选股池（蓝图 §四 能力1）：短线强势池 / 趋势反转池 / 风险预警池。"""
    m = DatabaseManager.get_instance()
    strong: List[Dict[str, Any]] = []
    reversal: List[Dict[str, Any]] = []
    risk: List[Dict[str, Any]] = []
    with m.session_scope() as s:
        rows = s.query(BacktraceKronosSignal).all()
        for r in rows:
            d = r.to_dict()
            if d.get('trend') == '多头趋势' and (d.get('riseProb') or 0) >= 0.7:
                strong.append(d)
            if '底部' in (d.get('inflectionPoint') or ''):
                reversal.append(d)
            if '顶部' in (d.get('inflectionPoint') or '') or (d.get('downProb') or 0) >= 0.5:
                risk.append(d)
    return {'code': 0, 'msg': 'ok', 'data': {'shortTermStrong': strong, 'reversal': reversal, 'riskWarning': risk}}
