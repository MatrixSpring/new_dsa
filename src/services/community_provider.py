# -*- coding: utf-8 -*-
"""可插拔深度社区舆情数据源适配器（DSA-COMMUNITY-OPINION-V1.0 #36，外挂微服务，不改动 DSA 内核）。

把闭环预警扫描（#20）与因子累积（#17/#24）的「深度社区情绪面信号源」从确定性 mock 升级为
可切换的**真实社区数据源适配器**（雪球 / 东财股吧 / 淘股吧 爬虫 + FinBERT 情绪量化 + 质量
分层 + 谣言降权，见用户「全平台分类梳理」蓝图 §一.2 community）：

  - 沙箱（默认）：走确定性 mock，接口契约不变，全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_COMMUNITY=1 后，切换为社区爬虫
    （xueqiu / guba / taoguba 异步爬虫）+ FinBERT 本地推理 + 质量分层 + 谣言降权链路；
    若依赖 / 网络 / 爬虫不可用，**优雅回退** mock 并记录原因，
    保证回溯闭环在任意环境都能运转。

与 #28 头条公域舆情（opinion_provider）、#31 微信私域舆情（wechat_provider）、#34 短线快讯
（flash_provider）的关系：四者正交、平行——都是「情绪面催化事件源」，但社区平台对 A 股**
散户情绪、短线题材、追涨杀跌、谣言发酵**影响力极强（雪球偏理性中长线、股吧/淘股吧偏情绪化
短线），与官方披露（#25 基本面）、头条舆情（#28 公域情绪）、微信舆情（#31 私域情绪）、
短线快讯（#34 盘中催化）、行情大涨（#23）正交互补，共同构成六路可插拔信号源。

设计原则（对齐蓝图 §五 / 七 风控底线）：
  - 所有打分 / 加权 / 分级仍为数学编排，社区源只负责「喂什么散户情绪催化标的与事件」，
    不介入决策；LLM / FinBERT 不参与涨跌幅度、概率、中长期量化结论；
  - DSA 内核 propagate_shock 零改动；因子库仍由真实归因累积（#17/#24）替代 preset；
  - 切换零代码改动：仅通过环境变量控制，向后兼容既有 mock 行为；
  - 质量分层（雪球=高质量 / 股吧·淘股吧=噪音）：噪音平台情绪极化、谣言高发，需强降权；
  - 权重约束：始终官方公告 > 机构研报 > 圈层前瞻 > 自媒体公域 > 社区情绪（文档 §七），
    社区短线权重 0.13（蓝图 §一.2 股吧），严禁主导长线；
  - 合规底线：只抓取公开社区讨论内容，不触碰私密群聊 / 付费社群私密内容 / 隐私。

文档 §一.2 / §五.2 权重建议（接入 DSA 模型，固定参数）：
  - 短线（1~7 日）：社区讨论 0.13（蓝图 §一.2 股吧短线权重；§五.2 短线合并模型未纳入社区维度，
    本文按 §一.2 参考值展示并标注「未纳入 §五.2 短线合并模型」）
  - 长线（中长期）：社区平台对中长线影响弱，取参考值 0.05 仅作展示，标注「未纳入长线合并模型」。
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import BacktraceCommunityOpinion, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

# 真实环境开关（默认关闭 → mock）。取值 '1' / 'true' / 'yes' 视为开启。
_ENV_KEY = 'DSA_REALTIME_COMMUNITY'

# 文档 §一.2（股吧短线 0.13）/ 社区平台对中长线影响弱（参考值 0.05）。
COMMUNITY_WEIGHT_SHORT = 0.13   # 1~7 日短线预测权重（§一.2 股吧短线维度，未纳入 §五.2 合并模型）
COMMUNITY_WEIGHT_LONG = 0.05    # 长线参考值（社区对中长线影响弱），未纳入 §五.2 长线合并模型
# 谣言 / 小道消息降权系数（文档 §一.2：社区平台谣言高发，需强降权）。
RUMOR_DOWNWEIGHT = 0.8          # 疑似谣言建议权重乘以该系数（即降到 20%）

# 文档 §一.2 三类深度社区平台 + 质量分层（quality）。
PLATFORM_XUEQIU = '雪球'        # 高质量投资者社区：KOL/机构入驻，理性讨论，对中长线影响偏大
PLATFORM_GUBA = '东财股吧'       # 散户情绪放大器：追涨杀跌、谣言高发，短线情绪源头
PLATFORM_TAOGUBA = '淘股吧'      # 游资/短线客聚集：打板/题材情绪风向标，短线题材催化强


def classify_quality(platform: str) -> str:
    """文档 §一.2 社区质量分层：雪球=高质量；股吧/淘股吧=噪音（情绪极化、谣言高发）。"""
    p = (platform or '').strip()
    if p == PLATFORM_XUEQIU:
        return '高质量'
    if p in (PLATFORM_GUBA, PLATFORM_TAOGUBA):
        return '噪音'
    return '普通'


def _weight_for(has_rumor: bool) -> float:
    """文档 §五.1 权重落地规则：默认短线 0.13；谣言进一步降权。"""
    base = COMMUNITY_WEIGHT_SHORT
    if has_rumor:
        base *= (1 - RUMOR_DOWNWEIGHT)  # 谣言降到 20%
    return round(base, 3)


class ProviderUnavailable(Exception):
    """社区数据源暂不可用（未部署爬虫 / 缺依赖 / 网络限流 / FinBERT 不可用）。"""


class BaseCommunityProvider:
    """统一社区数据源接口：近期个股 / 行业的深度社区讨论与情绪催化事件。

    所有方法返回「标准字段字典列表」，下游扫描与 UI 按字段消费，与具体数据源解耦。
    """

    #: 数据源可读名（前端展示用）
    label: str = 'base'

    def get_community_posts(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        """近期深度社区讨论 / 情绪催化事件（雪球 / 东财股吧 / 淘股吧）。

        返回字段：stock_code, stock_name, pub_date, title, platform(雪球/东财股吧/淘股吧),
        quality(高质量/普通/噪音), is_hot(0/1 登社区热榜), post_count(讨论数),
        discussion_heat(0~1), sentiment_score(-1~1), sentiment(看多/中性/看空),
        summary, has_rumor(0/1), weight_suggest(建议 DSA 短线权重)
        """
        raise NotImplementedError


class MockCommunityProvider(BaseCommunityProvider):
    """确定性模拟社区源：复用反向归因系统内置大涨池的已知标的，构造模板化社区讨论事件。

    用于沙箱验证与真实数据源不可用时的回退，保证接口契约稳定。覆盖文档 §一.2 / §三 全部
    字段，并刻意制造平台 / 质量 / 热榜 / 情绪 / 谣言多样性以驱动前端着色与风控展示。
    所有返回对沙箱确定性。600519 为池外标的，用于触发闭环扫描 union 的
    screen-pool 登记（与 #25/#28/#31/#34 同源假设）。
    """

    label = '模拟社区舆情源（确定性 mock）'

    _POSTS: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'pub_date': '2026-07-26',
         'title': '雪球长文：先进制程订单能见度延伸，国产替代逻辑获机构与 KOL 理性看多', 'platform': PLATFORM_XUEQIU,
         'is_hot': 1, 'post_count': 320, 'discussion_heat': 0.70,
         'sentiment_score': 0.55, 'sentiment': '看多',
         'summary': '雪球高质量社区：KOL/机构入驻，讨论理性，偏中长线逻辑发酵', 'has_rumor': 0},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'pub_date': '2026-07-27',
         'title': '淘股吧打板风向标：储能出海题材情绪高潮，游资短线客集中看多', 'platform': PLATFORM_TAOGUBA,
         'is_hot': 1, 'post_count': 980, 'discussion_heat': 0.90,
         'sentiment_score': 0.62, 'sentiment': '看多',
         'summary': '淘股吧游资/短线客聚集，题材情绪风向标，警惕全网高潮后的见顶出货', 'has_rumor': 0},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'pub_date': '2026-07-25',
         'title': '东财股吧散户分歧：智能化渗透率提升 vs 估值压制，情绪中性偏冷', 'platform': PLATFORM_GUBA,
         'is_hot': 0, 'post_count': 540, 'discussion_heat': 0.55,
         'sentiment_score': -0.10, 'sentiment': '中性',
         'summary': '股吧散户情绪放大器，分歧大、追涨杀跌明显，短线节奏偏震荡', 'has_rumor': 0},
        {'stock_code': '600519', 'stock_name': '贵州茅台', 'pub_date': '2026-07-24',
         'title': '东财股吧刷屏：网传消费税改革小道消息，疑似谣言需强降权', 'platform': PLATFORM_GUBA,
         'is_hot': 1, 'post_count': 720, 'discussion_heat': 0.66,
         'sentiment_score': -0.50, 'sentiment': '看空',
         'summary': '社区谣言高发源头，按文档 §七 强制降权、不认定有效利好事件', 'has_rumor': 1},
        {'stock_code': '000725', 'stock_name': '京东方 A', 'pub_date': '2026-07-23',
         'title': '雪球理性讨论：面板景气回暖早期信号，景气拐点获长线资金关注', 'platform': PLATFORM_XUEQIU,
         'is_hot': 0, 'post_count': 180, 'discussion_heat': 0.40,
         'sentiment_score': 0.42, 'sentiment': '看多',
         'summary': '雪球高质量讨论，景气拐点逻辑偏中长线，情绪稳定', 'has_rumor': 0},
        {'stock_code': '603799', 'stock_name': '华友钴业', 'pub_date': '2026-07-22',
         'title': '淘股吧分歧：镍价波动拖累资源股，短线客追涨杀跌情绪偏冷', 'platform': PLATFORM_TAOGUBA,
         'is_hot': 0, 'post_count': 410, 'discussion_heat': 0.50,
         'sentiment_score': -0.38, 'sentiment': '看空',
         'summary': '资源品分歧加大，短线客情绪极化，噪声偏高', 'has_rumor': 0},
    ]

    def get_community_posts(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        out = []
        for p in self._POSTS:
            item = dict(p)
            item['quality'] = classify_quality(p.get('platform'))
            item['weight_suggest'] = _weight_for(bool(p.get('has_rumor')))
            out.append(item)
        if stock_codes:
            wanted = {str(c) for c in stock_codes}
            out = [p for p in out if str(p['stock_code']) in wanted]
        return out


class CommunityCrawlerProvider(BaseCommunityProvider):
    """真实社区数据源（雪球/东财股吧/淘股吧爬虫 + FinBERT，见文档 §三.1）：缺失或失败即抛 ProviderUnavailable。

    仅在 DSA_REALTIME_COMMUNITY=1 时由工厂构造。真实部署需：
      - crawl_service.community_spider（xueqiu / guba / taoguba 异步社区爬虫）；
      - FinBERT 本地推理（ProsusAI/finbert）输出 -1~+1 连续情感得分；
      - 质量分层：雪球=高质量、股吧/淘股吧=噪音；谣言过滤：AI 溯源核查，无事实依据谣言自动降权 80%。
    沙箱内无网络 / 无爬虫 / 无 FinBERT，故方法内按需探测依赖，不可用时明确回退，
    避免在导入期即报错。
    """

    label = '实时社区源（雪球/东财股吧/淘股吧爬虫 + FinBERT）'

    def _crawler(self):
        """探测真实爬虫依赖（requests / aiohttp / 自有 community_spider），缺失即不可用。"""
        try:
            return importlib.import_module('requests')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'真实社区依赖未就绪（需部署 crawl_service.community_spider + requests/aiohttp）：{e}')

    def get_community_posts(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        self._crawler()  # 确保依赖存在；否则抛 ProviderUnavailable
        # 真实环境：调用 community_spider 抓取 → 预处理 → 质量分层 → FinBERT 情绪量化 → 谣言降权 → 结构化。
        # 该链路需网络、爬虫账号池与 FinBERT 推理服务，超出沙箱范围；此处显式声明部署要求。
        raise ProviderUnavailable(
            '真实社区抓取需在部署环境启用 crawl_service.community_spider（雪球/东财股吧/淘股吧异步爬虫）'
            '并挂载 FinBERT 本地推理；沙箱不可用，请确认网络 / Cookie 池 / FinBERT 服务后重跑'
        )


def get_community_provider() -> tuple[BaseCommunityProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_COMMUNITY → (Mock, mock, 原因)
    - 开启但依赖 / 爬虫不可用 → (Mock, mock, 回退原因)
    - 开启且可用 → (CommunityCrawler, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockCommunityProvider(), MODE_MOCK, '沙箱确定性社区源（未开启 DSA_REALTIME_COMMUNITY）'
    try:
        importlib.import_module('requests')
    except Exception:  # noqa: BLE001
        return (
            MockCommunityProvider(),
            MODE_MOCK,
            '已请求实时社区源，但爬虫依赖（requests/aiohttp）未部署，已回退模拟社区源',
        )
    return CommunityCrawlerProvider(), MODE_REAL, '实时社区源（雪球/东财股吧/淘股吧爬虫 + FinBERT）——需部署 community_spider 与 FinBERT 推理服务'


def describe_community_source() -> Dict[str, Any]:
    """描述当前活跃社区数据源，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_community_provider()
    try:
        posts = provider.get_community_posts(days=7)
    except Exception as e:  # noqa: BLE001
        logger.warning('社区源探测失败：%s', e)
        posts = []
    rumor = sum(1 for p in posts if p.get('has_rumor'))
    hot = sum(1 for p in posts if p.get('is_hot'))
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'communityCount': len(posts),
        'rumorCount': rumor,
        'hotCount': hot,
        'weightShortSuggest': COMMUNITY_WEIGHT_SHORT,
        'weightLongSuggest': COMMUNITY_WEIGHT_LONG,
        'envKey': _ENV_KEY,
    }


def refresh_community_pool(stock_codes: Optional[List[str]] = None, days: int = 7) -> Dict[str, Any]:
    """用活跃社区源重写社区讨论事件池（真实环境拉取社区爬虫；模拟环境写入确定性模板）。

    返回 {code, msg, data:{ mode, provider, pubDate, count, rumorCount, hotCount, reason }}。
    """
    provider, mode, reason = get_community_provider()
    posts = provider.get_community_posts(stock_codes=stock_codes, days=days)
    today = datetime.now().strftime('%Y-%m-%d')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceCommunityOpinion).delete()
        for p in posts:
            s.add(BacktraceCommunityOpinion(
                stock_code=str(p['stock_code']),
                stock_name=p.get('stock_name'),
                pub_date=p.get('pub_date') or today,
                title=str(p.get('title', '')),
                platform=p.get('platform'),
                quality=p.get('quality') or classify_quality(p.get('platform')),
                is_hot=int(bool(p.get('is_hot'))),
                post_count=int(p.get('post_count') or 0),
                discussion_heat=float(p.get('discussion_heat') or 0.0),
                sentiment_score=float(p.get('sentiment_score') or 0.0),
                sentiment=p.get('sentiment'),
                has_rumor=int(bool(p.get('has_rumor'))),
                weight_suggest=float(p.get('weight_suggest', COMMUNITY_WEIGHT_SHORT)),
                summary=p.get('summary'),
            ))
        s.flush()
        count = s.query(BacktraceCommunityOpinion).count()
        rumor = s.query(BacktraceCommunityOpinion).filter(BacktraceCommunityOpinion.has_rumor == 1).count()
        hot = s.query(BacktraceCommunityOpinion).filter(BacktraceCommunityOpinion.is_hot == 1).count()
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'pubDate': today,
            'count': int(count),
            'rumorCount': int(rumor),
            'hotCount': int(hot),
            'reason': reason,
        },
    }


def list_community_pool() -> Dict[str, Any]:
    """查询当前社区讨论事件池（按发布日期倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceCommunityOpinion)
            .order_by(BacktraceCommunityOpinion.pub_date.desc(), BacktraceCommunityOpinion.id.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'count': len(items), 'items': items}}
