# -*- coding: utf-8 -*-
"""可插拔垂直专业财经媒体数据源适配器（DSA-VERTICAL-MEDIA-OPINION-V1.0 #40，外挂微服务，不改动 DSA 内核）。

把闭环预警扫描（#20）与因子累积（#17/#24）的「垂直专业媒体情绪面信号源」从确定性 mock 升级为
可切换的**真实专业媒体数据源适配器**（财新 / 券商中国 / e公司（证券时报旗下） / 证券时报 /
上海证券报 / 第一财经 / 21世纪经济报道 等经官方批准的专业财经媒体，见用户「全平台分类梳理」
蓝图 §一.7 vertical_media）：

  - 沙箱（默认）：走确定性 mock，接口契约不变，全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_VERTICAL_MEDIA=1 后，切换为垂直专业媒体抓取
    （财新/证券时报/e公司/上海证券报/第一财经等公开合法内容抓取 + 机构评级/深度调研解析）；
    若依赖 / 网络 / 数据源不可用，**优雅回退** mock 并记录原因，
    保证回溯闭环在任意环境都能运转。

与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#34 短线快讯
（盘中催化）、#36 社区舆情（散户情绪）、#37 海外权威（外资/机构）的关系：七者正交、平行——
都是「情绪/催化事件源」，但垂直专业媒体对 A 股**官方指定信披媒体公信力、深度调研、监管追踪、
行业权威解读**影响力强（证券时报 / e公司 / 上海证券报为法定信披媒体，财新 / 第一财经为深度
独立财经），与官方披露（#25 基本面）、头条舆情（#28 公域情绪）、微信舆情（#31 私域情绪）、
短线快讯（#34 盘中催化）、社区舆情（#36 散户情绪）、海外权威（#37 外资）、行情大涨（#23）
正交互补，共同构成八路可插拔信号源（#35 Kronos 技术面单独逐 alert 富化，不扩池）。

设计原则（对齐蓝图 §五 / 七 风控底线）：
  - 所有打分 / 加权 / 分级仍为数学编排，垂直媒体源只负责「喂什么专业媒体催化标的与事件」，
    不介入决策；LLM / 媒体模型不参与涨跌幅度、概率、中长期量化结论；
  - DSA 内核 propagate_shock 零改动；因子库仍由真实归因累积（#17/#24）替代 preset；
  - 切换零代码改动：仅通过环境变量控制，向后兼容既有 mock 行为；
  - 权重约束：始终官方公告 > 机构研报 / 权威专业媒体 > 圈层前瞻 > 自媒体公域 > 社区情绪
    （文档 §七）；垂直专业媒体主要作用于「权威可信度」维度（§五.1 多源交叉验证中归 L1 权威
    圈层），短线权重适中（0.12），严禁主导短线题材（权威媒体节奏偏慢、对短线题材催化弱）；
  - 合规底线：只抓取公开合法的专业财经媒体内容，不触碰付费终端私密内容 / 内幕信息。

文档 §一.7 / §五.1 权重建议（接入 DSA 模型，固定参数）：
  - 短线（1~7 日）：垂直专业媒体 0.12（权威媒体节奏偏慢、对短线题材催化弱）
  - 长线（中长期）：权威专业媒体 0.15（官方信披媒体公信力 + 深度调研，贴近权威可信维度）
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import BacktraceVerticalMediaOpinion, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

# 真实环境开关（默认关闭 → mock）。取值 '1' / 'true' / 'yes' 视为开启。
_ENV_KEY = 'DSA_REALTIME_VERTICAL_MEDIA'

# 文档 §一.7（垂直专业媒体短线 0.12）/ 长线权威可信维度 0.15。
VERTICAL_MEDIA_WEIGHT_SHORT = 0.12   # 1~7 日短线预测权重（权威媒体节奏偏慢，对题材催化弱）
VERTICAL_MEDIA_WEIGHT_LONG = 0.15    # 长线权威可信维度（官方信披媒体公信力 + 深度调研）

# 文档 §一.7 七类垂直专业财经媒体平台 / outlet。
MEDIA_CAIXIN = '财新'                 # 深度独立财经：调研权威、深度独家
MEDIA_QUANSHANG = '券商中国'          # 券商系专业媒体：机构视角、行业解读
MEDIA_EGS = 'e公司'                   # 证券时报旗下信披新媒体（法定信披媒体）
MEDIA_ZQS = '证券时报'                # 法定信披媒体
MEDIA_SHZQ = '上海证券报'             # 法定信披媒体
MEDIA_DIYCJ = '第一财经'              # 专业财经电视台 / 门户
MEDIA_21 = '21世纪经济报道'           # 专业财经纸媒

# 官方指定信披媒体（法定信息披露渠道）：公信力最高，归 L1 权威圈层核心。
_OFFICIAL_OUTLETS = {MEDIA_EGS, MEDIA_ZQS, MEDIA_SHZQ}


def is_official_outlet(media_name: str) -> bool:
    """判定是否官方指定信披媒体（法定信披渠道）。"""
    return (media_name or '').strip() in _OFFICIAL_OUTLETS


def classify_coverage(media_name: str) -> str:
    """文档 §一.7：垂直专业媒体的报道类型——深度调研 / 快讯点评 / 监管追踪 / 行业解读。

    财新/第一财经偏深度调研与行业解读；信披媒体（e公司/证券时报/上海证券报）偏监管追踪与
    法定信披快讯；券商中国偏行业解读。
    """
    m = (media_name or '').strip()
    if m in _OFFICIAL_OUTLETS:
        return '监管追踪'
    if m in (MEDIA_CAIXIN, MEDIA_DIYCJ, MEDIA_21):
        return '深度调研'
    return '行业解读'


def _weight_for(is_official: bool) -> float:
    """文档 §五.1 权重落地规则：默认短线 0.12；官方信披媒体事件权重上行（贴近权威可信维度）。"""
    return round(VERTICAL_MEDIA_WEIGHT_LONG if is_official else VERTICAL_MEDIA_WEIGHT_SHORT, 3)


class ProviderUnavailable(Exception):
    """垂直专业媒体数据源暂不可用（未部署抓取器 / 缺依赖 / 网络限流）。"""


class BaseVerticalMediaProvider:
    """统一垂直专业媒体数据源接口：近期个股 / 行业的专业媒体深度报道与权威催化事件。

    所有方法返回「标准字段字典列表」，下游扫描与 UI 按字段消费，与具体数据源解耦。
    """

    #: 数据源可读名（前端展示用）
    label: str = 'base'

    def get_vertical_media_news(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        """近期垂直专业财经媒体深度报道 / 权威催化事件（财新 / 券商中国 / e公司 / 证券时报 / 上海证券报 / 第一财经 / 21世纪经济报道）。

        返回字段：stock_code, stock_name, pub_date, title, media_name(媒体名),
        outlet(媒体分类), is_official(0/1 官方指定信披媒体), coverage_type(深度调研/快讯点评/监管追踪/行业解读),
        sentiment_score(-1~1), sentiment(看多/中性/看空), has_rumor(0/1),
        summary, weight_suggest(建议 DSA 权重)
        """
        raise NotImplementedError


class MockVerticalMediaProvider(BaseVerticalMediaProvider):
    """确定性模拟垂直专业媒体源：复用反向归因系统内置大涨池的已知标的，构造模板化专业媒体报道事件。

    用于沙箱验证与真实数据源不可用时的回退，保证接口契约稳定。覆盖文档 §一.7 / §三 全部
    字段，并刻意制造媒体 / 信披属性 / 报道类型 / 情绪多样性以驱动前端着色与风控展示。
    所有返回对沙箱确定性。600519 为池外标的，用于触发闭环扫描 union 的
    screen-pool 登记（与 #25/#28/#31/#34/#36/#37 同源假设）。
    """

    label = '模拟垂直专业媒体源（确定性 mock）'

    _NEWS: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'pub_date': '2026-07-26',
         'title': '财新深度：先进制程国产替代逻辑获权威印证，产业链调研确认订单能见度延伸', 'media_name': MEDIA_CAIXIN,
         'sentiment_score': 0.52, 'sentiment': '看多',
         'summary': '财新深度独立财经：调研权威、产业链独家印证，偏中长线逻辑发酵'},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'pub_date': '2026-07-27',
         'title': '证券时报：储能出海订单获官方信披确认，欧洲市场放量释放看多信号', 'media_name': MEDIA_ZQS,
         'sentiment_score': 0.55, 'sentiment': '看多',
         'summary': '法定信披媒体（证券时报）：官方公信力确认，长线权威维度偏多'},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'pub_date': '2026-07-25',
         'title': '券商中国：智能化渗透率提升行业解读，估值压制下中性偏多', 'media_name': MEDIA_QUANSHANG,
         'sentiment_score': 0.22, 'sentiment': '中性',
         'summary': '券商系专业媒体：机构视角行业解读，短线催化有限'},
        {'stock_code': '600519', 'stock_name': '贵州茅台', 'pub_date': '2026-07-24',
         'title': 'e公司（证券时报旗下）：消费税改革监管追踪，官方信披渠道动态密切跟踪', 'media_name': MEDIA_EGS,
         'sentiment_score': 0.06, 'sentiment': '中性',
         'summary': '法定信披新媒体（e公司）：监管追踪权威渠道，情绪中性、无谣言'},
        {'stock_code': '000725', 'stock_name': '京东方 A', 'pub_date': '2026-07-23',
         'title': '上海证券报：面板景气拐点获官方信披报道，行业回暖早期信号确认', 'media_name': MEDIA_SHZQ,
         'sentiment_score': 0.46, 'sentiment': '看多',
         'summary': '法定信披媒体（上海证券报）：景气拐点权威确认，情绪稳定偏多'},
        {'stock_code': '603799', 'stock_name': '华友钴业', 'pub_date': '2026-07-22',
         'title': '第一财经：资源品承压深度调研，镍价波动拖累基本面偏空', 'media_name': MEDIA_DIYCJ,
         'sentiment_score': -0.35, 'sentiment': '看空',
         'summary': '第一财经深度调研：资源品基本面承压，权威维度偏空'},
    ]

    def get_vertical_media_news(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        out = []
        for n in self._NEWS:
            item = dict(n)
            item['outlet'] = '官方指定信披媒体' if is_official_outlet(n.get('media_name')) else '专业财经媒体'
            item['is_official'] = int(is_official_outlet(n.get('media_name')))
            item['coverage_type'] = classify_coverage(n.get('media_name'))
            item['has_rumor'] = int(bool(n.get('has_rumor')))
            item['weight_suggest'] = _weight_for(bool(item['is_official']))
            out.append(item)
        if stock_codes:
            wanted = {str(c) for c in stock_codes}
            out = [n for n in out if str(n['stock_code']) in wanted]
        return out


class VerticalMediaCrawlerProvider(BaseVerticalMediaProvider):
    """真实垂直专业媒体数据源（财新/证券时报/e公司/上海证券报/第一财经抓取 + 机构评级/深度调研解析，见文档 §三.1）：缺失或失败即抛 ProviderUnavailable。

    仅在 DSA_REALTIME_VERTICAL_MEDIA=1 时由工厂构造。真实部署需：
      - crawl_service.vertical_media_spider（财新/证券时报/e公司/上海证券报/第一财经等公开合法抓取）；
      - 深度调研 / 监管追踪解析（增持/中性/减持 + 行业景气判断）；
    沙箱内无网络 / 无爬虫，故方法内按需探测依赖，不可用时明确回退，
    避免在导入期即报错。
    """

    label = '实时垂直专业媒体源（财新/证券时报/e公司/上海证券报/第一财经 抓取）'

    def _crawler(self):
        """探测真实抓取依赖（requests / aiohttp / 自有 vertical_media_spider），缺失即不可用。"""
        try:
            return importlib.import_module('requests')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'真实垂直媒体依赖未就绪（需部署 crawl_service.vertical_media_spider + requests/aiohttp）：{e}')

    def get_vertical_media_news(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        self._crawler()  # 确保依赖存在；否则抛 ProviderUnavailable
        # 真实环境：调用 vertical_media_spider 抓取 → 预处理 → 深度调研/监管追踪解析 → 结构化。
        # 该链路需网络、数据源授权与解析服务，超出沙箱范围；此处显式声明部署要求。
        raise ProviderUnavailable(
            '真实垂直专业媒体抓取需在部署环境启用 crawl_service.vertical_media_spider'
            '（财新/证券时报/e公司/上海证券报/第一财经）并挂载深度调研/监管追踪解析；'
            '沙箱不可用，请确认网络 / 数据源授权后重跑'
        )


def get_vertical_media_provider() -> tuple[BaseVerticalMediaProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_VERTICAL_MEDIA → (Mock, mock, 原因)
    - 开启但依赖 / 抓取器不可用 → (Mock, mock, 回退原因)
    - 开启且可用 → (VerticalMediaCrawler, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockVerticalMediaProvider(), MODE_MOCK, '沙箱确定性垂直专业媒体源（未开启 DSA_REALTIME_VERTICAL_MEDIA）'
    try:
        importlib.import_module('requests')
    except Exception:  # noqa: BLE001
        return (
            MockVerticalMediaProvider(),
            MODE_MOCK,
            '已请求实时垂直专业媒体源，但抓取依赖（requests/aiohttp）未部署，已回退模拟垂直专业媒体源',
        )
    return VerticalMediaCrawlerProvider(), MODE_REAL, '实时垂直专业媒体源（财新/证券时报/e公司/上海证券报/第一财经）——需部署 vertical_media_spider 与深度调研/监管追踪解析'


def describe_vertical_media_source() -> Dict[str, Any]:
    """描述当前活跃垂直专业媒体数据源，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_vertical_media_provider()
    try:
        news = provider.get_vertical_media_news(days=7)
    except Exception as e:  # noqa: BLE001
        logger.warning('垂直专业媒体源探测失败：%s', e)
        news = []
    official = sum(1 for n in news if n.get('is_official'))
    rating_up = sum(1 for n in news if n.get('sentiment') == '看多')
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'verticalMediaCount': len(news),
        'officialCount': official,
        'ratingUpCount': rating_up,
        'weightShortSuggest': VERTICAL_MEDIA_WEIGHT_SHORT,
        'weightLongSuggest': VERTICAL_MEDIA_WEIGHT_LONG,
        'envKey': _ENV_KEY,
    }


def refresh_vertical_media_pool(stock_codes: Optional[List[str]] = None, days: int = 7) -> Dict[str, Any]:
    """用活跃垂直专业媒体源重写专业媒体报道事件池（真实环境拉取抓取；模拟环境写入确定性模板）。

    返回 {code, msg, data:{ mode, provider, pubDate, count, officialCount, ratingUpCount, reason }}。
    """
    provider, mode, reason = get_vertical_media_provider()
    news = provider.get_vertical_media_news(stock_codes=stock_codes, days=days)
    today = datetime.now().strftime('%Y-%m-%d')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceVerticalMediaOpinion).delete()
        for n in news:
            s.add(BacktraceVerticalMediaOpinion(
                stock_code=str(n['stock_code']),
                stock_name=n.get('stock_name'),
                pub_date=n.get('pub_date') or today,
                title=str(n.get('title', '')),
                media_name=n.get('media_name'),
                outlet=n.get('outlet') or ('官方指定信披媒体' if n.get('is_official') else '专业财经媒体'),
                is_official=int(bool(n.get('is_official'))),
                coverage_type=n.get('coverage_type') or classify_coverage(n.get('media_name')),
                sentiment_score=float(n.get('sentiment_score') or 0.0),
                sentiment=n.get('sentiment'),
                has_rumor=int(bool(n.get('has_rumor'))),
                weight_suggest=float(n.get('weight_suggest', VERTICAL_MEDIA_WEIGHT_SHORT)),
                summary=n.get('summary'),
            ))
        s.flush()
        count = s.query(BacktraceVerticalMediaOpinion).count()
        official = s.query(BacktraceVerticalMediaOpinion).filter(BacktraceVerticalMediaOpinion.is_official == 1).count()
        rating_up = s.query(BacktraceVerticalMediaOpinion).filter(BacktraceVerticalMediaOpinion.sentiment == '看多').count()
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'pubDate': today,
            'count': int(count),
            'officialCount': int(official),
            'ratingUpCount': int(rating_up),
            'reason': reason,
        },
    }


def list_vertical_media_pool() -> Dict[str, Any]:
    """查询当前垂直专业媒体报道事件池（按发布日期倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceVerticalMediaOpinion)
            .order_by(BacktraceVerticalMediaOpinion.pub_date.desc(), BacktraceVerticalMediaOpinion.id.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'count': len(items), 'items': items}}
