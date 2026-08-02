# -*- coding: utf-8 -*-
"""可插拔短线快讯舆情数据源适配器（DSA-FLASH-OPINION-V1.0 #34，外挂微服务，不改动 DSA 内核）。

把闭环预警扫描（#20）与因子累积（#17/#24）的「短线快讯情绪面信号源」从确定性 mock 升级为
可切换的**真实快讯数据源适配器**（财联社 / 华尔街见闻 / 金十 + 垂直专业媒体爬虫 + FinBERT
情绪量化，见用户「全平台分类梳理」蓝图 §一.2 / §三.1 flash_spider）：

  - 沙箱（默认）：走确定性 mock，接口契约不变，全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_FLASH=1 后，切换为快讯爬虫
    （cls-crawler / Crawl4AI 异步新闻爬虫）+ FinBERT 本地推理 + 谣言降权链路；
    若依赖 / 网络 / 爬虫不可用，**优雅回退** mock 并记录原因，
    保证回溯闭环在任意环境都能运转。

与 #28 头条公域舆情（opinion_provider）、#31 微信私域舆情（wechat_provider）的关系：
  - 三者正交、平行——都是「情绪面催化事件源」，但快讯平台对 A 股**短线题材、盘中催化**
    影响力极强（财联社为 A 股短线第一舆情平台，游资 / 量化第一参考，题材炒作核心发酵推手）；
  - 快讯以「速度」取胜（7×24 电报式推送，政策 / 产业突发全网最快），但自媒体整合内容多、
    谣言 / 小道消息占比偏高（文档 §一.2 优缺点）；
  - 垂直专业媒体（财新 / 券商中国 / e公司）作为快讯源子集，承担「深度调查 / 独家专访 /
    突发利空爆料」，是个股闪崩高频源头，归入本源 media_type='深度媒体'。

设计原则（对齐蓝图 §五 / 七 风控底线）：
  - 所有打分 / 加权 / 分级仍为数学编排，快讯源只负责「喂什么短线情绪催化标的与事件」，
    不介入决策；LLM / FinBERT 不参与涨跌幅度、概率、中长期量化结论；
  - DSA 内核 propagate_shock 零改动；因子库仍由真实归因累积（#17/#24）替代 preset；
  - 切换零代码改动：仅通过环境变量控制，向后兼容既有 mock 行为；
  - 权重约束：始终官方公告 > 机构研报 > 圈层前瞻 > 自媒体公域舆情（文档 §七），
    快讯短线权重 0.22（短线合并模型中仅次于圈内前瞻 0.20 与公告落地 0.25），严禁主导长线；
  - 合规底线：只抓取公开合法快讯 / 媒体内容，不触碰私密群聊 / 朋友圈 / 隐私。

文档 §一.2 / §五.2 权重建议（接入 DSA 模型，固定参数）：
  - 短线（1~7 日）：财联社快讯 0.22（蓝图 §五.2 短线合并 = 财联社快讯 0.22，与 §一.2 一致）
  - 长线（中长期）：未纳入 §五.2 长线合并模型（长线外资维度只保留彭博 / 路透系），
    取 §一.2 参考值 0.09 仅作展示，标注「未纳入长线合并模型」。
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import BacktraceFlashOpinion, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

# 真实环境开关（默认关闭 → mock）。取值 '1' / 'true' / 'yes' 视为开启。
_ENV_KEY = 'DSA_REALTIME_FLASH'

# 文档 §一.2（财联社短线 0.22）/ §五.2（短线合并：财联社快讯 0.22）一致。
FLASH_WEIGHT_SHORT = 0.22   # 1~7 日短线预测权重（短线合并模型维度）
FLASH_WEIGHT_LONG = 0.09    # 长线参考值（§一.2），未纳入 §五.2 长线合并模型
# 谣言 / 低可信事件降权系数（文档 §一.2：快讯谣言占比偏高，需强降权）。
RUMOR_DOWNWEIGHT = 0.8       # 疑似谣言建议权重乘以该系数（即降到 20%）

# 文档 §一.2 / §七类 垂直专业媒体：快讯 vs 深度媒体分类（media_type）。
MEDIA_FLASH = '快讯'         # 财联社 / 华尔街见闻 / 金十 —— 电报式推送
MEDIA_DEEP = '深度媒体'      # 财新 / 券商中国 / e公司 —— 独家爆料 / 深度调查


class ProviderUnavailable(Exception):
    """快讯数据源暂不可用（未部署爬虫 / 缺依赖 / 网络限流 / FinBERT 不可用）。"""


def classify_stage(heat_score: float, sentiment_score: float) -> str:
    """文档 §三.2 扩散阶段模型：由热度与情绪推导扩散阶段。

    萌芽（低热度）→ 发酵（热度上行）→ 狂热（高热度且强情绪）→ 退潮（高热度转负）。

    快讯特征：早盘利好推送→当日冲高；尾盘集中吹风→次日冲高；连续分歧解读→题材见顶回落。
    """
    heat = float(heat_score or 0.0)
    sent = float(sentiment_score or 0.0)
    if heat >= 0.75 and sent <= -0.1:
        return '退潮'          # 高热度 + 负情绪：见顶回落 / 利空砸盘信号
    if heat >= 0.7:
        return '狂热'
    if heat >= 0.45:
        return '发酵'
    return '萌芽'


def _weight_for(has_rumor: bool) -> float:
    """文档 §五.1 权重落地规则：默认短线 0.22；谣言进一步降权。"""
    base = FLASH_WEIGHT_SHORT
    if has_rumor:
        base *= (1 - RUMOR_DOWNWEIGHT)  # 谣言降到 20%
    return round(base, 3)


class BaseFlashProvider:
    """统一快讯数据源接口：近期个股 / 行业短线快讯与深度媒体催化事件。

    所有方法返回「标准字段字典列表」，下游扫描与 UI 按字段消费，与具体数据源解耦。
    """

    #: 数据源可读名（前端展示用）
    label: str = 'base'

    def get_flashes(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        """近期短线快讯 / 深度媒体催化事件（财联社 / 华尔街见闻 / 金十 / 垂直媒体）。

        返回字段：stock_code, stock_name, pub_date, title, source,
        media_type(快讯/深度媒体), is_breaking(0/1 盘中突发), heat_score(0~1),
        sentiment_score(-1~1), sentiment(利好/中性/利空), stage(萌芽/发酵/狂热/退潮),
        summary, has_rumor(0/1), weight_suggest(建议 DSA 短线权重)
        """
        raise NotImplementedError


class MockFlashProvider(BaseFlashProvider):
    """确定性模拟快讯源：复用反向归因系统内置大涨池的已知标的，构造模板化快讯事件。

    用于沙箱验证与真实数据源不可用时的回退，保证接口契约稳定。覆盖文档 §一.2 / §三 全部
    字段，并刻意制造渠道 / media_type / 突发 / 情绪 / 阶段 / 谣言多样性以驱动前端着色与
    风控展示。所有返回对沙箱确定性。600519 为池外标的，用于触发闭环扫描 union 的
    screen-pool 登记（与 #28/#31 同源假设）。
    """

    label = '模拟快讯源（确定性 mock）'

    _FLASHES: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'pub_date': '2026-07-26',
         'title': '财联社盘中突发：先进制程订单能见度延伸至明年，国产替代加速', 'source': '财联社',
         'media_type': MEDIA_FLASH, 'is_breaking': 1,
         'heat_score': 0.74, 'sentiment_score': 0.62, 'sentiment': '利好', 'stage': '发酵',
         'summary': '财联社 7×24 电报式推送，游资与量化第一参考，盘中题材催化最强', 'has_rumor': 0},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'pub_date': '2026-07-27',
         'title': '财联社早盘利好推送：储能出海订单传闻刷屏，题材情绪进入高潮', 'source': '财联社',
         'media_type': MEDIA_FLASH, 'is_breaking': 1,
         'heat_score': 0.88, 'sentiment_score': 0.70, 'sentiment': '利好', 'stage': '狂热',
         'summary': '早盘利好推送→当日冲高；警惕全网刷屏后的狂热见顶与游资出货', 'has_rumor': 0},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'pub_date': '2026-07-25',
         'title': '华尔街见闻：智能化渗透率提升，外围与期货联动解读出海逻辑', 'source': '华尔街见闻',
         'media_type': MEDIA_FLASH, 'is_breaking': 0,
         'heat_score': 0.52, 'sentiment_score': 0.14, 'sentiment': '中性', 'stage': '发酵',
         'summary': '擅长全球宏观与外围联动，对大盘权重股影响大，短线节奏偏温和', 'has_rumor': 0},
        {'stock_code': '600519', 'stock_name': '贵州茅台', 'pub_date': '2026-07-24',
         'title': 'e公司突发利空爆料：网传消费税改革利空白酒，个股闪崩高频源头', 'source': 'e公司',
         'media_type': MEDIA_DEEP, 'is_breaking': 1,
         'heat_score': 0.66, 'sentiment_score': -0.58, 'sentiment': '利空', 'stage': '退潮',
         'summary': '垂直专业媒体独家负面爆料，按文档 §七 强制降权、不认定有效利好事件', 'has_rumor': 1},
        {'stock_code': '000725', 'stock_name': '京东方 A', 'pub_date': '2026-07-23',
         'title': '金十数据：面板景气回暖早期信号，期货联动大宗商品产业链', 'source': '金十数据',
         'media_type': MEDIA_FLASH, 'is_breaking': 0,
         'heat_score': 0.42, 'sentiment_score': 0.46, 'sentiment': '利好', 'stage': '萌芽',
         'summary': '欧美实时数据 + 期货联动，影响周期股、大宗商品产业链 A 股', 'has_rumor': 0},
        {'stock_code': '603799', 'stock_name': '华友钴业', 'pub_date': '2026-07-22',
         'title': '财联社资源品快讯：镍价波动拖累资源股，题材分歧加大', 'source': '财联社',
         'media_type': MEDIA_FLASH, 'is_breaking': 0,
         'heat_score': 0.55, 'sentiment_score': -0.40, 'sentiment': '利空', 'stage': '发酵',
         'summary': '产业链利空发酵，专业散户跟随减仓，情绪偏冷', 'has_rumor': 0},
    ]

    def get_flashes(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        out = []
        for f in self._FLASHES:
            item = dict(f)
            item['stage'] = f.get('stage') or classify_stage(f.get('heat_score'), f.get('sentiment_score'))
            item['weight_suggest'] = _weight_for(bool(f.get('has_rumor')))
            out.append(item)
        if stock_codes:
            wanted = {str(c) for c in stock_codes}
            out = [f for f in out if str(f['stock_code']) in wanted]
        return out


class ClsCrawlerProvider(BaseFlashProvider):
    """真实快讯数据源（财联社/华尔街见闻/金十爬虫 + 垂直媒体 + FinBERT，见文档 §三.1）：缺失或失败即抛 ProviderUnavailable。

    仅在 DSA_REALTIME_FLASH=1 时由工厂构造。真实部署需：
      - crawl_service.flash_spider（cls-crawler / Crawl4AI 异步新闻爬虫，财联社 / 华尔街见闻 /
        金十 / 财新 / 券商中国 / e公司 多源）；
      - FinBERT 本地推理（ProsusAI/finbert）输出 -1~+1 连续情感得分；
      - 谣言过滤：AI 溯源核查，无事实依据自媒体谣言自动降权 80%。
    沙箱内无网络 / 无爬虫 / 无 FinBERT，故方法内按需探测依赖，不可用时明确回退，
    避免在导入期即报错。
    """

    label = '实时快讯源（财联社/华尔街见闻/金十爬虫 + FinBERT）'

    def _crawler(self):
        """探测真实爬虫依赖（requests / aiohttp / 自有 flash_spider），缺失即不可用。"""
        try:
            return importlib.import_module('requests')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'真实快讯依赖未就绪（需部署 crawl_service.flash_spider + requests/aiohttp）：{e}')

    def get_flashes(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        self._crawler()  # 确保依赖存在；否则抛 ProviderUnavailable
        # 真实环境：调用 flash_spider 抓取 → 预处理 → FinBERT 情绪量化 → 谣言降权 → 结构化。
        # 该链路需网络、爬虫账号池与 FinBERT 推理服务，超出沙箱范围；此处显式声明部署要求。
        raise ProviderUnavailable(
            '真实快讯抓取需在部署环境启用 crawl_service.flash_spider（cls-crawler / Crawl4AI 异步新闻爬虫）'
            '并挂载 FinBERT 本地推理；沙箱不可用，请确认网络 / Cookie 池 / FinBERT 服务后重跑'
        )


def get_flash_provider() -> tuple[BaseFlashProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_FLASH → (Mock, mock, 原因)
    - 开启但依赖 / 爬虫不可用 → (Mock, mock, 回退原因)
    - 开启且可用 → (ClsCrawler, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockFlashProvider(), MODE_MOCK, '沙箱确定性快讯源（未开启 DSA_REALTIME_FLASH）'
    try:
        importlib.import_module('requests')
    except Exception:  # noqa: BLE001
        return (
            MockFlashProvider(),
            MODE_MOCK,
            '已请求实时快讯源，但爬虫依赖（requests/aiohttp）未部署，已回退模拟快讯源',
        )
    return ClsCrawlerProvider(), MODE_REAL, '实时快讯源（财联社/华尔街见闻/金十爬虫 + FinBERT）——需部署 flash_spider 与 FinBERT 推理服务'


def describe_flash_source() -> Dict[str, Any]:
    """描述当前活跃快讯数据源，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_flash_provider()
    try:
        flashes = provider.get_flashes(days=7)
    except Exception as e:  # noqa: BLE001
        logger.warning('快讯源探测失败：%s', e)
        flashes = []
    rumor = sum(1 for f in flashes if f.get('has_rumor'))
    breaking = sum(1 for f in flashes if f.get('is_breaking'))
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'flashCount': len(flashes),
        'rumorCount': rumor,
        'breakingCount': breaking,
        'weightShortSuggest': FLASH_WEIGHT_SHORT,
        'weightLongSuggest': FLASH_WEIGHT_LONG,
        'envKey': _ENV_KEY,
    }


def refresh_flash_pool(stock_codes: Optional[List[str]] = None, days: int = 7) -> Dict[str, Any]:
    """用活跃快讯源重写快讯事件池（真实环境拉取快讯爬虫；模拟环境写入确定性模板）。

    返回 {code, msg, data:{ mode, provider, pubDate, count, rumorCount, breakingCount, reason }}。
    """
    provider, mode, reason = get_flash_provider()
    flashes = provider.get_flashes(stock_codes=stock_codes, days=days)
    today = datetime.now().strftime('%Y-%m-%d')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceFlashOpinion).delete()
        for f in flashes:
            s.add(BacktraceFlashOpinion(
                stock_code=str(f['stock_code']),
                stock_name=f.get('stock_name'),
                pub_date=f.get('pub_date') or today,
                title=str(f.get('title', '')),
                source=f.get('source'),
                media_type=f.get('media_type'),
                is_breaking=int(bool(f.get('is_breaking'))),
                heat_score=float(f.get('heat_score') or 0.0),
                sentiment_score=float(f.get('sentiment_score') or 0.0),
                sentiment=f.get('sentiment'),
                stage=f.get('stage') or classify_stage(f.get('heat_score'), f.get('sentiment_score')),
                has_rumor=int(bool(f.get('has_rumor'))),
                weight_suggest=float(f.get('weight_suggest', FLASH_WEIGHT_SHORT)),
                summary=f.get('summary'),
            ))
        s.flush()
        count = s.query(BacktraceFlashOpinion).count()
        rumor = s.query(BacktraceFlashOpinion).filter(BacktraceFlashOpinion.has_rumor == 1).count()
        breaking = s.query(BacktraceFlashOpinion).filter(BacktraceFlashOpinion.is_breaking == 1).count()
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'pubDate': today,
            'count': int(count),
            'rumorCount': int(rumor),
            'breakingCount': int(breaking),
            'reason': reason,
        },
    }


def list_flash_pool() -> Dict[str, Any]:
    """查询当前快讯事件池（按发布日期倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceFlashOpinion)
            .order_by(BacktraceFlashOpinion.pub_date.desc(), BacktraceFlashOpinion.id.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'count': len(items), 'items': items}}
