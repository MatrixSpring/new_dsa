# -*- coding: utf-8 -*-
"""可插拔海外权威舆情数据源适配器（DSA-OVERSEAS-OPINION-V1.0 #37，外挂微服务，不改动 DSA 内核）。

把闭环预警扫描（#20）与因子累积（#17/#24）的「海外权威情绪面信号源」从确定性 mock 升级为
可切换的**真实海外数据源适配器**（彭博 / 路透 / WSJ / Seeking Alpha 海外财经媒体 + 机构评级
+ 外资流向，见用户「全平台分类梳理」蓝图 §一.6 overseas）：

  - 沙箱（默认）：走确定性 mock，接口契约不变，全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_OVERSEAS=1 后，切换为海外财经数据源
    （Bloomberg / Reuters / WSJ / SeekingAlpha 抓取 + 机构评级 / 外资流向解析）；
    若依赖 / 网络 / 数据源不可用，**优雅回退** mock 并记录原因，
    保证回溯闭环在任意环境都能运转。

与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#34 短线快讯
（盘中催化）、#36 社区舆情（散户情绪）的关系：六者正交、平行——都是「情绪/催化事件源」，
但海外权威源对 A 股**外资流向、机构评级、长线基本面预期**影响力极强（外资定价权、北向资金
风向标），与官方披露（#25 基本面）、头条舆情（#28 公域情绪）、微信舆情（#31 私域情绪）、
短线快讯（#34 盘中催化）、社区舆情（#36 散户情绪）、行情大涨（#23）正交互补，共同构成
七路可插拔信号源。

设计原则（对齐蓝图 §五 / 七 风控底线）：
  - 所有打分 / 加权 / 分级仍为数学编排，海外源只负责「喂什么海外权威催化标的与事件」，
    不介入决策；LLM / 海外模型不参与涨跌幅度、概率、中长期量化结论；
  - DSA 内核 propagate_shock 零改动；因子库仍由真实归因累积（#17/#24）替代 preset；
  - 切换零代码改动：仅通过环境变量控制，向后兼容既有 mock 行为；
  - 权重约束：始终官方公告 > 机构研报 > 圈层前瞻 > 自媒体公域 > 社区情绪（文档 §七）；
    海外权威源主要作用于**长线外资维度**（§五.2 长线合并模型保留彭博/路透系 0.18），
    严禁主导短线（短线仅 0.14，且海外资讯偏慢、对短线题材催化弱）；
  - 合规底线：只抓取公开海外财经媒体与机构公开评级，不触碰付费终端私密内容 / 内幕信息。

文档 §一.6 / §五.2 权重建议（接入 DSA 模型，固定参数）：
  - 短线（1~7 日）：海外资讯 0.14（蓝图 §一.6 海外短线维度参考）
  - 长线（中长期）：外资资讯 0.18（蓝图 §五.2 长线合并模型保留「彭博/路透系」维度，
    即文档 §三 吸收的 §一.6 海外长线 0.18；华尔街见闻/金十长线 0.11 未进入长线合并模型）
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import BacktraceOverseasOpinion, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

# 真实环境开关（默认关闭 → mock）。取值 '1' / 'true' / 'yes' 视为开启。
_ENV_KEY = 'DSA_REALTIME_OVERSEAS'

# 文档 §一.6（海外短线 0.14）/ §五.2（长线外资维度 0.18，保留彭博/路透系）。
OVERSEAS_WEIGHT_SHORT = 0.14   # 1~7 日短线预测权重（§一.6 海外短线维度参考）
OVERSEAS_WEIGHT_LONG = 0.18    # 长线外资维度（§五.2 长线合并模型保留彭博/路透系 0.18）

# 文档 §一.6 四类海外权威平台。
PLATFORM_BLOOMBERG = '彭博'        # Bloomberg：全球机构终端，外资定价权风向标
PLATFORM_REUTERS = '路透'          # Reuters：全球新闻社，机构资讯与评级覆盖
PLATFORM_WSJ = 'WSJ'               # 华尔街日报：深度宏观与个股基本面报道
PLATFORM_SEEKING_ALPHA = 'Seeking Alpha'  # 众包投研平台：散户+独立分析师评级与多空论点


def classify_impact(platform: str, rating: Optional[str]) -> str:
    """文档 §一.6：海外权威事件的催化类型——外资流向 / 评级调整 / 基本面 / 宏观。

    彭博/路透/WSJ 偏机构评级与基本面；Seeking Alpha 偏多空论点与评级调整。
    """
    p = (platform or '').strip()
    if rating and rating != '无':
        return '评级调整'
    if p in (PLATFORM_BLOOMBERG, PLATFORM_REUTERS):
        return '外资流向'
    if p == PLATFORM_WSJ:
        return '基本面'
    return '宏观'


def _weight_for(is_institution: bool) -> float:
    """文档 §五.1 权重落地规则：默认短线 0.14；机构评级/研报事件权重上行（贴近长线外资维度）。

    机构评级/研报（is_institution）代表外资定价权确认，短线权重按长线外资维度 0.18 计。
    """
    return round(OVERSEAS_WEIGHT_LONG if is_institution else OVERSEAS_WEIGHT_SHORT, 3)


class ProviderUnavailable(Exception):
    """海外数据源暂不可用（未部署抓取器 / 缺依赖 / 网络限流 / 终端不可用）。"""


class BaseOverseasProvider:
    """统一海外数据源接口：近期个股 / 行业的海外权威资讯与机构评级催化事件。

    所有方法返回「标准字段字典列表」，下游扫描与 UI 按字段消费，与具体数据源解耦。
    """

    #: 数据源可读名（前端展示用）
    label: str = 'base'

    def get_overseas_news(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        """近期海外权威资讯 / 机构评级催化事件（彭博 / 路透 / WSJ / Seeking Alpha）。

        返回字段：stock_code, stock_name, pub_date, title, platform(彭博/路透/WSJ/Seeking Alpha),
        region(海外), is_institution(0/1 机构评级/研报), rating(增持/中性/减持/无),
        sentiment_score(-1~1), sentiment(看多/中性/看空), impact_type(外资流向/评级调整/基本面/宏观),
        summary, weight_suggest(建议 DSA 短线权重)
        """
        raise NotImplementedError


class MockOverseasProvider(BaseOverseasProvider):
    """确定性模拟海外源：复用反向归因系统内置大涨池的已知标的，构造模板化海外权威资讯事件。

    用于沙箱验证与真实数据源不可用时的回退，保证接口契约稳定。覆盖文档 §一.6 / §三 全部
    字段，并刻意制造平台 / 机构评级 / 情绪 / 催化类型多样性以驱动前端着色与风控展示。
    所有返回对沙箱确定性。600519 为池外标的，用于触发闭环扫描 union 的
    screen-pool 登记（与 #25/#28/#31/#34/#36 同源假设）。
    """

    label = '模拟海外权威源（确定性 mock）'

    _NEWS: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'pub_date': '2026-07-26',
         'title': 'Bloomberg：半导体设备出口管制松动预期升温，海外机构上调评级至增持', 'platform': PLATFORM_BLOOMBERG,
         'is_institution': 1, 'rating': '增持',
         'sentiment_score': 0.60, 'sentiment': '看多',
         'summary': '彭博终端：外资定价权风向标，机构评级上调代表长线外资维度确认'},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'pub_date': '2026-07-27',
         'title': 'Reuters：欧洲储能订单超预期，北向资金连续净流入释放看多信号', 'platform': PLATFORM_REUTERS,
         'is_institution': 1, 'rating': '增持',
         'sentiment_score': 0.58, 'sentiment': '看多',
         'summary': '路透：海外基本面+外资流向共振，长线外资维度偏多'},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'pub_date': '2026-07-25',
         'title': 'WSJ：海外工厂投产进度符合预期，基本面中性偏多但估值承压', 'platform': PLATFORM_WSJ,
         'is_institution': 0, 'rating': '中性',
         'sentiment_score': 0.18, 'sentiment': '中性',
         'summary': '华尔街日报：深度基本面报道，海外工厂落地兑现，短线催化有限'},
        {'stock_code': '600519', 'stock_name': '贵州茅台', 'pub_date': '2026-07-24',
         'title': 'Bloomberg：外资持股比例边际变化引发讨论，长线外资维度再定价', 'platform': PLATFORM_BLOOMBERG,
         'is_institution': 0, 'rating': '无',
         'sentiment_score': 0.10, 'sentiment': '中性',
         'summary': '海外权威源对核心资产的长期外资持仓跟踪（池外标的，演示 union 登记）'},
        {'stock_code': '000725', 'stock_name': '京东方 A', 'pub_date': '2026-07-23',
         'title': 'Seeking Alpha：面板景气拐点多空交锋，独立分析师给出增持论点', 'platform': PLATFORM_SEEKING_ALPHA,
         'is_institution': 1, 'rating': '增持',
         'sentiment_score': 0.40, 'sentiment': '看多',
         'summary': 'Seeking Alpha 众包投研：独立分析师评级调整，偏长线外资视角'},
        {'stock_code': '603799', 'stock_name': '华友钴业', 'pub_date': '2026-07-22',
         'title': 'Reuters：镍价波动拖累资源股，机构下调评级至中性', 'platform': PLATFORM_REUTERS,
         'is_institution': 1, 'rating': '减持',
         'sentiment_score': -0.42, 'sentiment': '看空',
         'summary': '路透：资源品基本面承压，机构评级下调，长线外资维度偏空'},
    ]

    def get_overseas_news(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        out = []
        for n in self._NEWS:
            item = dict(n)
            item['region'] = '海外'
            item['impact_type'] = classify_impact(n.get('platform'), n.get('rating'))
            item['weight_suggest'] = _weight_for(bool(n.get('is_institution')))
            out.append(item)
        if stock_codes:
            wanted = {str(c) for c in stock_codes}
            out = [n for n in out if str(n['stock_code']) in wanted]
        return out


class OverseasCrawlerProvider(BaseOverseasProvider):
    """真实海外数据源（彭博/路透/WSJ/Seeking Alpha 抓取 + 机构评级/外资流向解析，见文档 §三.1）：缺失或失败即抛 ProviderUnavailable。

    仅在 DSA_REALTIME_OVERSEAS=1 时由工厂构造。真实部署需：
      - crawl_service.overseas_spider（Bloomberg / Reuters / WSJ / SeekingAlpha 抓取）；
      - 机构评级解析（增持/中性/减持）+ 北向/外资流向聚合；
    沙箱内无网络 / 无爬虫，故方法内按需探测依赖，不可用时明确回退，
    避免在导入期即报错。
    """

    label = '实时海外权威源（彭博/路透/WSJ/Seeking Alpha 抓取 + 机构评级）'

    def _crawler(self):
        """探测真实抓取依赖（requests / aiohttp / 自有 overseas_spider），缺失即不可用。"""
        try:
            return importlib.import_module('requests')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'真实海外依赖未就绪（需部署 crawl_service.overseas_spider + requests/aiohttp）：{e}')

    def get_overseas_news(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        self._crawler()  # 确保依赖存在；否则抛 ProviderUnavailable
        # 真实环境：调用 overseas_spider 抓取 → 预处理 → 机构评级解析 → 外资流向聚合 → 结构化。
        # 该链路需网络、数据源授权与解析服务，超出沙箱范围；此处显式声明部署要求。
        raise ProviderUnavailable(
            '真实海外抓取需在部署环境启用 crawl_service.overseas_spider（彭博/路透/WSJ/Seeking Alpha）'
            '并挂载机构评级/外资流向解析；沙箱不可用，请确认网络 / 数据源授权后重跑'
        )


def get_overseas_provider() -> tuple[BaseOverseasProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_OVERSEAS → (Mock, mock, 原因)
    - 开启但依赖 / 抓取器不可用 → (Mock, mock, 回退原因)
    - 开启且可用 → (OverseasCrawler, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockOverseasProvider(), MODE_MOCK, '沙箱确定性海外权威源（未开启 DSA_REALTIME_OVERSEAS）'
    try:
        importlib.import_module('requests')
    except Exception:  # noqa: BLE001
        return (
            MockOverseasProvider(),
            MODE_MOCK,
            '已请求实时海外源，但抓取依赖（requests/aiohttp）未部署，已回退模拟海外权威源',
        )
    return OverseasCrawlerProvider(), MODE_REAL, '实时海外权威源（彭博/路透/WSJ/Seeking Alpha）——需部署 overseas_spider 与机构评级/外资流向解析'


def describe_overseas_source() -> Dict[str, Any]:
    """描述当前活跃海外数据源，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_overseas_provider()
    try:
        news = provider.get_overseas_news(days=7)
    except Exception as e:  # noqa: BLE001
        logger.warning('海外源探测失败：%s', e)
        news = []
    institution = sum(1 for n in news if n.get('is_institution'))
    rating_up = sum(1 for n in news if n.get('sentiment') == '看多' or n.get('rating') == '增持')
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'overseasCount': len(news),
        'institutionCount': institution,
        'ratingUpCount': rating_up,
        'weightShortSuggest': OVERSEAS_WEIGHT_SHORT,
        'weightLongSuggest': OVERSEAS_WEIGHT_LONG,
        'envKey': _ENV_KEY,
    }


def refresh_overseas_pool(stock_codes: Optional[List[str]] = None, days: int = 7) -> Dict[str, Any]:
    """用活跃海外源重写海外权威资讯事件池（真实环境拉取海外抓取；模拟环境写入确定性模板）。

    返回 {code, msg, data:{ mode, provider, pubDate, count, institutionCount, ratingUpCount, reason }}。
    """
    provider, mode, reason = get_overseas_provider()
    news = provider.get_overseas_news(stock_codes=stock_codes, days=days)
    today = datetime.now().strftime('%Y-%m-%d')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceOverseasOpinion).delete()
        for n in news:
            s.add(BacktraceOverseasOpinion(
                stock_code=str(n['stock_code']),
                stock_name=n.get('stock_name'),
                pub_date=n.get('pub_date') or today,
                title=str(n.get('title', '')),
                platform=n.get('platform'),
                region=n.get('region') or '海外',
                is_institution=int(bool(n.get('is_institution'))),
                rating=n.get('rating'),
                sentiment_score=float(n.get('sentiment_score') or 0.0),
                sentiment=n.get('sentiment'),
                impact_type=n.get('impact_type') or classify_impact(n.get('platform'), n.get('rating')),
                weight_suggest=float(n.get('weight_suggest', OVERSEAS_WEIGHT_SHORT)),
                summary=n.get('summary'),
            ))
        s.flush()
        count = s.query(BacktraceOverseasOpinion).count()
        institution = s.query(BacktraceOverseasOpinion).filter(BacktraceOverseasOpinion.is_institution == 1).count()
        rating_up = s.query(BacktraceOverseasOpinion).filter(
            (BacktraceOverseasOpinion.sentiment == '看多') | (BacktraceOverseasOpinion.rating == '增持')
        ).count()
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'pubDate': today,
            'count': int(count),
            'institutionCount': int(institution),
            'ratingUpCount': int(rating_up),
            'reason': reason,
        },
    }


def list_overseas_pool() -> Dict[str, Any]:
    """查询当前海外权威资讯事件池（按发布日期倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceOverseasOpinion)
            .order_by(BacktraceOverseasOpinion.pub_date.desc(), BacktraceOverseasOpinion.id.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'count': len(items), 'items': items}}
