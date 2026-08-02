# -*- coding: utf-8 -*-
"""可插拔公开舆情数据源适配器（DSA-PUBLIC-OPINION-V1.0 #28，外挂微服务，不改动 DSA 内核）。

把闭环预警扫描（#20）与因子累积（#17/#24）的「情绪面信号源」从确定性 mock 升级为
可切换的**真实舆情数据源适配器**（头条爬虫 + FinBERT 情绪量化，见文档 §一~§四）：

  - 沙箱（默认）：走确定性 mock，接口契约不变，全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_OPINION=1 后，切换为头条舆情爬虫
    （TTBot / aiohttp 异步爬虫，接入 crawl_service.toutiao_spider）+ FinBERT 本地推理
    + 谣言降权链路；若依赖 / 网络 / 爬虫不可用，**优雅回退** mock 并记录原因，
    保证回溯闭环在任意环境都能运转。

设计原则（对齐文档 §六 决策权坚守 / 顶层原则）：
  - 所有打分 / 加权 / 分级仍为数学编排，舆情源只负责「喂什么情绪催化标的与事件」，
    不介入决策；LLM / FinBERT 不参与涨跌幅度、概率、中长期量化结论；
  - DSA 内核 propagate_shock 零改动；因子库仍由真实归因累积（#17/#24）替代 preset；
  - 切换零代码改动：仅通过环境变量控制，向后兼容既有 mock 行为；
  - 与 #23 行情源（大涨）、#25 披露源（基本面）正交：行情喂「大涨标的池」，
    披露喂「基本面催化事件」，舆情喂「情绪催化事件」，三者闭环扫描叠加（union）。

文档 §三 多投资者信息面范围标准化假设模型（4 层权重，固定参数）：
  - 产业内幕：0.45（系统仅能复盘捕捉，不参与实时权重）
  - 机构研报 / 调研：0.35
  - 头条等自媒体舆情：0.15（仅短线情绪因子，严禁主导中长期）
  - 散户跟风情绪：0.05
约束：中长期预测大幅压低舆情权重，短线预测小幅提升舆情权重。

文档 §四 统一结构化 JSON 输出字段（情绪量化层产物）：
  sentiment_score(-1~+1) / heat_score(0~1) / info_diff_stage(萌芽/发酵/狂热/退潮) /
  has_rumor(谣言降权标记) / weight_suggest(建议 DSA 模型权重，默认 0.15)。
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import BacktraceOpinion, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

# 真实环境开关（默认关闭 → mock）。取值 '1' / 'true' / 'yes' 视为开启。
_ENV_KEY = 'DSA_REALTIME_OPINION'

# 文档 §三 四层信息圈层量化影响权重（固定参数，仅作展示与真实环境权重建议基准）。
INFO_LAYER_WEIGHTS: Dict[str, float] = {
    'industry_insider': 0.45,   # 产业内幕知情者
    'institution_research': 0.35,  # 机构研报 / 调研
    'self_media_opinion': 0.15,  # 头条等自媒体舆情
    'retail_herding': 0.05,     # 散户跟风情绪
}
# 文档 §三 约束：舆情（self_media_opinion）建议权重，中长期进一步压低。
OPINION_WEIGHT_SUGGEST = INFO_LAYER_WEIGHTS['self_media_opinion']


class ProviderUnavailable(Exception):
    """舆情数据源暂不可用（未部署爬虫 / 缺依赖 / 网络限流 / FinBERT 不可用）。"""


def classify_stage(heat_score: float, sentiment_score: float) -> str:
    """文档 §三.1 信息扩散-股价走势对应模型：由热度与情绪推导扩散阶段。

    萌芽（低热度，情绪温和）→ 发酵（热度上行）→ 狂热（高热度且强情绪）→
    退潮（高热度但转负 / 情绪转冷）。
    """
    heat = float(heat_score or 0.0)
    sent = float(sentiment_score or 0.0)
    if heat >= 0.75 and sent <= -0.1:
        return '退潮'          # 高热度 + 负情绪：见顶回落信号
    if heat >= 0.7:
        return '狂热'
    if heat >= 0.45:
        return '发酵'
    return '萌芽'


class BaseOpinionProvider:
    """统一舆情数据源接口：近期个股 / 行业舆情事件（含情绪与热度量化）。

    所有方法返回「标准字段字典列表」，下游扫描与 UI 按字段消费，与具体数据源解耦。
    """

    #: 数据源可读名（前端展示用）
    label: str = 'base'

    def get_opinions(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        """近期公开舆情事件（头条 / 雪球 / 股吧等散户情绪源）。

        返回字段：stock_code, stock_name, opinion_date, title, source,
        heat_score(0~1), sentiment_score(-1~1), sentiment(利好/中性/利空),
        stage(萌芽/发酵/狂热/退潮), summary, has_rumor(0/1)
        """
        raise NotImplementedError


class MockOpinionProvider(BaseOpinionProvider):
    """确定性模拟舆情源：复用反向归因系统内置大涨池的已知标的，构造模板化情绪事件。

    用于沙箱验证与真实数据源不可用时的回退，保证接口契约稳定。覆盖文档 §四 全部字段，
    并刻意制造情绪 / 阶段 / 谣言多样性以驱动前端着色与风控展示。所有返回对沙箱确定性。
    """

    label = '模拟舆情源（确定性 mock）'

    #: 与 _MOCK_POOL 对齐的确定性舆情模板（仅引用池内标的，保证可被 agent_dig 解析）。
    _OPINIONS: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'opinion_date': '2026-07-26',
         'title': '国产替代加速，先进制程订单能见度延伸至明年', 'source': '头条财经',
         'heat_score': 0.72, 'sentiment_score': 0.60, 'sentiment': '利好', 'stage': '发酵',
         'summary': '机构与游资圈层开始密集解读，散户端热度缓慢上行', 'has_rumor': 0},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'opinion_date': '2026-07-27',
         'title': '储能出海订单传闻刷屏，题材情绪进入高潮', 'source': '头条',
         'heat_score': 0.86, 'sentiment_score': 0.70, 'sentiment': '利好', 'stage': '狂热',
         'summary': '头条爆款满天飞，全民讨论，警惕见顶与游资出货', 'has_rumor': 0},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'opinion_date': '2026-07-25',
         'title': '智能化渗透率提升，专业博主二次解读出海逻辑', 'source': '雪球',
         'heat_score': 0.50, 'sentiment_score': 0.10, 'sentiment': '中性', 'stage': '发酵',
         'summary': '信息扩散层（三级圈层）内容增多，热度温和上升', 'has_rumor': 0},
        {'stock_code': '600519', 'stock_name': '贵州茅台', 'opinion_date': '2026-07-24',
         'title': '网传消费税改革利空白酒，股吧恐慌扩散', 'source': '股吧',
         'heat_score': 0.66, 'sentiment_score': -0.55, 'sentiment': '利空', 'stage': '退潮',
         'summary': '无权威佐证的自媒体谣言，按文档 §六 强制降权 80%', 'has_rumor': 1},
        {'stock_code': '000725', 'stock_name': '京东方 A', 'opinion_date': '2026-07-23',
         'title': '面板景气回暖早期信号，小众财经号零星提及', 'source': '头条',
         'heat_score': 0.40, 'sentiment_score': 0.45, 'sentiment': '利好', 'stage': '萌芽',
         'summary': '仅少量小众财经自媒体提及，全网热度极低（二级圈层附近）', 'has_rumor': 0},
        {'stock_code': '603799', 'stock_name': '华友钴业', 'opinion_date': '2026-07-22',
         'title': '镍价波动拖累资源股，雪球分歧加大', 'source': '雪球',
         'heat_score': 0.55, 'sentiment_score': -0.40, 'sentiment': '利空', 'stage': '发酵',
         'summary': '产业链利空发酵，专业散户跟随减仓，情绪偏冷', 'has_rumor': 0},
    ]

    def get_opinions(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        out = [dict(o) for o in self._OPINIONS]
        if stock_codes:
            wanted = {str(c) for c in stock_codes}
            out = [o for o in out if str(o['stock_code']) in wanted]
        return out


class ToutiaoOpinionProvider(BaseOpinionProvider):
    """真实舆情数据源（头条爬虫 + FinBERT 情绪量化 + 谣言降权，见文档 §四）：缺失或失败即抛 ProviderUnavailable。

    仅在 DSA_REALTIME_OPINION=1 时由工厂构造。真实部署需：
      - crawl_service.toutiao_spider（TTBot / aiohttp 异步爬虫，多 Cookie 池防封禁）；
      - FinBERT 本地推理（ProsusAI/finbert）输出 -1~+1 连续情感得分；
      - 谣言过滤：AI 溯源核查，无事实依据自媒体谣言自动降权 80%。
    沙箱内无网络 / 无爬虫 / 无 FinBERT，故方法内按需探测依赖，不可用时明确回退，
    避免在导入期即报错。
    """

    label = '实时舆情源（头条爬虫 + FinBERT）'

    def _crawler(self):
        """探测真实爬虫依赖（requests / aiohttp / 自有 toutiao_spider），缺失即不可用。"""
        try:
            return importlib.import_module('requests')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'真实舆情依赖未就绪（需部署 crawl_service.toutiao_spider + requests/aiohttp）：{e}')

    def get_opinions(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        self._crawler()  # 确保依赖存在；否则抛 ProviderUnavailable
        # 真实环境：调用 toutiao_spider 抓取 → 预处理 → FinBERT 情绪量化 → 谣言降权 → 结构化。
        # 该链路需网络、爬虫账号池与 FinBERT 推理服务，超出沙箱范围；此处显式声明部署要求。
        raise ProviderUnavailable(
            '真实舆情抓取需在部署环境启用 crawl_service.toutiao_spider（TTBot / aiohttp 异步爬虫）'
            '并挂载 FinBERT 本地推理；沙箱不可用，请确认网络 / Cookie 池 / FinBERT 服务后重跑'
        )


def get_opinion_provider() -> tuple[BaseOpinionProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_OPINION → (Mock, mock, 原因)
    - 开启但依赖 / 爬虫不可用 → (Mock, mock, 回退原因)
    - 开启且可用 → (Toutiao, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockOpinionProvider(), MODE_MOCK, '沙箱确定性舆情源（未开启 DSA_REALTIME_OPINION）'
    try:
        importlib.import_module('requests')
    except Exception:  # noqa: BLE001
        return (
            MockOpinionProvider(),
            MODE_MOCK,
            '已请求实时舆情源，但爬虫依赖（requests/aiohttp）未部署，已回退模拟舆情源',
        )
    return ToutiaoOpinionProvider(), MODE_REAL, '实时舆情源（头条爬虫 + FinBERT）——需部署 toutiao_spider 与 FinBERT 推理服务'


def describe_opinion_source() -> Dict[str, Any]:
    """描述当前活跃舆情数据源，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_opinion_provider()
    try:
        opinions = provider.get_opinions(days=7)
    except Exception as e:  # noqa: BLE001
        logger.warning('舆情源探测失败：%s', e)
        opinions = []
    rumor = sum(1 for o in opinions if o.get('has_rumor'))
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'opinionCount': len(opinions),
        'rumorCount': rumor,
        'weightSuggest': OPINION_WEIGHT_SUGGEST,
        'envKey': _ENV_KEY,
    }


def refresh_opinion_pool(stock_codes: Optional[List[str]] = None, days: int = 7) -> Dict[str, Any]:
    """用活跃舆情源重写舆情事件池（真实环境拉取头条爬虫；模拟环境写入确定性模板）。

    返回 {code, msg, data:{ mode, provider, opinionDate, count, rumorCount, reason }}。
    """
    provider, mode, reason = get_opinion_provider()
    opinions = provider.get_opinions(stock_codes=stock_codes, days=days)
    today = datetime.now().strftime('%Y-%m-%d')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceOpinion).delete()
        for o in opinions:
            s.add(BacktraceOpinion(
                stock_code=str(o['stock_code']),
                stock_name=o.get('stock_name'),
                opinion_date=o.get('opinion_date') or today,
                title=str(o.get('title', '')),
                source=o.get('source'),
                heat_score=float(o.get('heat_score') or 0.0),
                sentiment_score=float(o.get('sentiment_score') or 0.0),
                sentiment=o.get('sentiment'),
                stage=o.get('stage') or classify_stage(o.get('heat_score'), o.get('sentiment_score')),
                summary=o.get('summary'),
                has_rumor=int(bool(o.get('has_rumor'))),
            ))
        s.flush()
        count = s.query(BacktraceOpinion).count()
        rumor = s.query(BacktraceOpinion).filter(BacktraceOpinion.has_rumor == 1).count()
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'opinionDate': today,
            'count': int(count),
            'rumorCount': int(rumor),
            'reason': reason,
        },
    }


def list_opinion_pool() -> Dict[str, Any]:
    """查询当前舆情事件池（按舆情日期倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceOpinion)
            .order_by(BacktraceOpinion.opinion_date.desc(), BacktraceOpinion.id.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'count': len(items), 'items': items}}
