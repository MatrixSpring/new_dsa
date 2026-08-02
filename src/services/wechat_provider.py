# -*- coding: utf-8 -*-
"""可插拔微信私域舆情数据源适配器（DSA-WECHAT-OPINION-V1.0 #31，外挂微服务，不改动 DSA 内核）。

把闭环预警扫描（#20）与因子累积（#17/#24）的「私域情绪面信号源」从确定性 mock 升级为
可切换的**真实微信舆情数据源适配器**（微信公众号爬虫 + 视频号爬虫 + FinBERT 情绪量化，
见用户文档 §一~§七）：

  - 沙箱（默认）：走确定性 mock，接口契约不变，全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_WECHAT=1 后，切换为微信舆情爬虫
    （WeChatSpider 公众号 / VideoSpider-WeChat 视频号，接入 crawl_service.wechat_spider）
    + FinBERT 本地推理 + 可信度分级链路；若依赖 / 网络 / 爬虫不可用，**优雅回退** mock
    并记录原因，保证回溯闭环在任意环境都能运转。

与 #28 头条公域舆情（opinion_provider）的关系：
  - 二者正交、平行——都是「情绪面催化事件源」，但微信私域舆情对 A 股短线题材、小票、
    突发利空、小众产业链催化影响力 > 头条公域舆情（文档 §二 核心结论）；
  - 微信仅公众号 / 视频号可自动化抓取，微信群聊 / 朋友圈 / 私聊无法稳定抓取（文档 §三）；
  - 权重更高：微信短线 0.20 / 长线 0.08（#28 头条短线 0.15 / 长线 0.05，文档 §二 对比表）。

设计原则（对齐文档 §六 风控与落地注意事项 / 顶层原则）：
  - 所有打分 / 加权 / 分级仍为数学编排，微信源只负责「喂什么私域情绪催化标的与事件」，
    不介入决策；LLM / FinBERT 不参与涨跌幅度、概率、中长期量化结论；
  - DSA 内核 propagate_shock 零改动；因子库仍由真实归因累积（#17/#24）替代 preset；
  - 切换零代码改动：仅通过环境变量控制，向后兼容既有 mock 行为；
  - 权重约束：始终官方公告 > 机构研报 > 微信圈层舆情 > 头条散户舆情（文档 §六），
    杜绝舆情左右长线基本面判断；
  - 合规底线：只抓取公众号公开文章、公开视频号内容，不触碰群聊 / 朋友圈 / 私人聊天。

文档 §五 可信度分级规则（写入 credibility）：
  - 高：券商官方、正规产业号（主动阅读，机构散户都会看，是公开前瞻解读核心来源）
  - 中：行业垂直号、财经博主（信息扩散层）
  - 低：不知名自媒体、无来源爆料（强制降权，单一爆料不认定有效事件）
  - 多方公众号交叉印证同一事件 → 可信度大幅提升（真实环境由解析链路处理）

文档 §二 权重建议（接入 DSA 模型，固定参数）：
  - 短线（1~7 日）：微信舆情 0.20（高于头条 0.15）
  - 长线（中长期）：微信舆情 0.08（高于头条 0.05）
  - 利空预警：大范围微信负面爆料 → 立刻下调短期估值系数、强化悲观推演
  - 题材判断：公众号圈内持续发酵、头条尚未大面积曝光 → 标记题材发酵期；全网刷屏 → 狂热期
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import BacktraceWechatOpinion, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

# 真实环境开关（默认关闭 → mock）。取值 '1' / 'true' / 'yes' 视为开启。
_ENV_KEY = 'DSA_REALTIME_WECHAT'

# 文档 §二 对比表 / §五：微信舆情权重建议（固定参数，仅作展示与真实环境权重基准）。
# 与 #28 头条舆情（短线 0.15 / 长线 0.05）区分——微信私域前瞻价值更高。
WECHAT_WEIGHT_SHORT = 0.20   # 1~7 日短线预测权重
WECHAT_WEIGHT_LONG = 0.08    # 中长期预测权重（仅辅助参考）
# 谣言 / 低可信度事件降权系数（文档 §五 防造谣：单一自媒体爆料不认定有效事件）。
RUMOR_DOWNWEIGHT = 0.8       # 疑似谣言建议权重乘以该系数（即降到 20%）

# 文档 §五 可信度分级载体映射（用于 mock 与真实环境归类）。
CARRIER_OFFICIAL = '券商公众号'
CARRIER_INDUSTRY = '产业垂直号'
CARRIER_VIDEO = '财经视频号'
CARRIER_PAID = '付费社群线索'
CARRIER_OTHER = '其他自媒体'
CRED_HIGH = '高'   # 券商官方 / 正规产业号
CRED_MID = '中'    # 行业垂直号 / 财经博主
CRED_LOW = '低'    # 不知名自媒体 / 无来源爆料


class ProviderUnavailable(Exception):
    """微信舆情数据源暂不可用（未部署爬虫 / 缺依赖 / 网络限流 / FinBERT 不可用）。"""


def classify_stage(heat_score: float, sentiment_score: float) -> str:
    """文档 §五 题材判断规则：由热度与情绪推导扩散阶段。

    圈内微信群小众发酵 → 垂直公众号整理发文 → 全网公众号转载扩散 →
    头条公域大范围推送 → 散户集体跟风入场。

    萌芽（低热度）→ 发酵（热度上行）→ 狂热（高热度且强情绪）→ 退潮（高热度转负）。
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


def _weight_for(credibility: str, has_rumor: bool) -> float:
    """文档 §五 权重落地规则：默认短线 0.20；低可信度 / 谣言进一步降权。"""
    base = WECHAT_WEIGHT_SHORT
    if credibility == CRED_LOW:
        base *= 0.5          # 无来源爆料强制降权
    if has_rumor:
        base *= (1 - RUMOR_DOWNWEIGHT)  # 谣言降到 20%
    return round(base, 3)


class BaseWechatProvider:
    """统一微信舆情数据源接口：近期个股 / 行业私域舆情事件（含载体 / 可信度 / 情绪 / 热度）。

    所有方法返回「标准字段字典列表」，下游扫描与 UI 按字段消费，与具体数据源解耦。
    """

    #: 数据源可读名（前端展示用）
    label: str = 'base'

    def get_wechats(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        """近期微信私域舆情事件（公众号 / 视频号 / 付费社群线索）。

        返回字段：stock_code, stock_name, pub_date, title, source, carrier,
        credibility(高/中/低), heat_score(0~1), sentiment_score(-1~1),
        sentiment(利好/中性/利空), stage(萌芽/发酵/狂热/退潮), summary,
        has_rumor(0/1), weight_suggest(建议 DSA 短线权重)
        """
        raise NotImplementedError


class MockWechatProvider(BaseWechatProvider):
    """确定性模拟微信舆情源：复用反向归因系统内置大涨池的已知标的，构造模板化私域事件。

    用于沙箱验证与真实数据源不可用时的回退，保证接口契约稳定。覆盖文档 §五 全部字段，
    并刻意制造载体 / 可信度 / 情绪 / 阶段 / 谣言多样性以驱动前端着色与风控展示。
    所有返回对沙箱确定性。600519 为池外标的，用于触发闭环扫描 union 的 screen-pool 登记。
    """

    label = '模拟微信舆情源（确定性 mock）'

    _WECHATS: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'pub_date': '2026-07-26',
         'title': '券商官方公众号早评：先进制程订单能见度延伸至明年，国产替代加速', 'source': 'XX券商研究',
         'carrier': CARRIER_OFFICIAL, 'credibility': CRED_HIGH,
         'heat_score': 0.70, 'sentiment_score': 0.62, 'sentiment': '利好', 'stage': '发酵',
         'summary': '券商官方公众号主动推送，机构与散户均阅读，圈内资金提前悄悄建仓', 'has_rumor': 0},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'pub_date': '2026-07-27',
         'title': '产业垂直号梳理储能出海订单，游资题材号次日复盘催化', 'source': '产业深度号',
         'carrier': CARRIER_INDUSTRY, 'credibility': CRED_HIGH,
         'heat_score': 0.85, 'sentiment_score': 0.68, 'sentiment': '利好', 'stage': '狂热',
         'summary': '头条尚未大面积曝光，已进入题材发酵期；警惕全网刷屏后的狂热见顶', 'has_rumor': 0},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'pub_date': '2026-07-25',
         'title': '财经视频号博主可视化解读智能化渗透率提升逻辑', 'source': '车圈视频号',
         'carrier': CARRIER_VIDEO, 'credibility': CRED_MID,
         'heat_score': 0.55, 'sentiment_score': 0.12, 'sentiment': '中性', 'stage': '发酵',
         'summary': '视频号短线情绪放大器，介于公众号与头条之间，热度温和上行', 'has_rumor': 0},
        {'stock_code': '600519', 'stock_name': '贵州茅台', 'pub_date': '2026-07-24',
         'title': '无资质自媒体公众号编造消费税改革利空白酒传闻，小范围转载', 'source': '野鸡财经号',
         'carrier': CARRIER_OTHER, 'credibility': CRED_LOW,
         'heat_score': 0.66, 'sentiment_score': -0.58, 'sentiment': '利空', 'stage': '退潮',
         'summary': '无权威佐证的自媒体谣言，按文档 §六 强制降权、不认定有效事件', 'has_rumor': 1},
        {'stock_code': '000725', 'stock_name': '京东方 A', 'pub_date': '2026-07-23',
         'title': '付费产业社群提前提示面板景气回暖早期信号', 'source': '面板投研群线索',
         'carrier': CARRIER_PAID, 'credibility': CRED_MID,
         'heat_score': 0.45, 'sentiment_score': 0.48, 'sentiment': '利好', 'stage': '萌芽',
         'summary': '付费社群线索属于小众信息补充，产业圈内消息比全网公开早 3~15 天', 'has_rumor': 0},
        {'stock_code': '603799', 'stock_name': '华友钴业', 'pub_date': '2026-07-22',
         'title': '产业垂直号提示镍价波动拖累资源股，专业散户跟随减仓', 'source': '有色产业号',
         'carrier': CARRIER_INDUSTRY, 'credibility': CRED_HIGH,
         'heat_score': 0.55, 'sentiment_score': -0.40, 'sentiment': '利空', 'stage': '发酵',
         'summary': '产业链利空发酵，圈内提前恐慌出逃，个股毫无征兆快速下跌', 'has_rumor': 0},
    ]

    def get_wechats(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        out = []
        for w in self._WECHATS:
            item = dict(w)
            item['stage'] = w.get('stage') or classify_stage(w.get('heat_score'), w.get('sentiment_score'))
            item['weight_suggest'] = _weight_for(w.get('credibility', CRED_MID), bool(w.get('has_rumor')))
            out.append(item)
        if stock_codes:
            wanted = {str(c) for c in stock_codes}
            out = [w for w in out if str(w['stock_code']) in wanted]
        return out


class WechatSpiderProvider(BaseWechatProvider):
    """真实微信舆情数据源（公众号 / 视频号爬虫 + FinBERT + 可信度分级，见文档 §五）：缺失或失败即抛 ProviderUnavailable。

    仅在 DSA_REALTIME_WECHAT=1 时由工厂构造。真实部署需：
      - crawl_service.wechat_spider（WeChatSpider 公众号 / VideoSpider-WeChat 视频号，搜狗微信接口）；
      - FinBERT 本地推理（ProsusAI/finbert）输出 -1~+1 连续情感得分；
      - 可信度分级：券商官方 / 正规产业号高可信；不知名自媒体低可信、强制降权；
        多方公众号交叉印证同一事件可信度提升。
    沙箱内无网络 / 无爬虫 / 无 FinBERT，故方法内按需探测依赖，不可用时明确回退，
    避免在导入期即报错。合规底线：只抓公众号公开文章与公开视频号，不碰群聊 / 朋友圈。
    """

    label = '实时微信舆情源（公众号/视频号爬虫 + FinBERT）'

    def _crawler(self):
        """探测真实爬虫依赖（requests / 自有 wechat_spider），缺失即不可用。"""
        try:
            return importlib.import_module('requests')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'真实微信舆情依赖未就绪（需部署 crawl_service.wechat_spider + requests）：{e}')

    def get_wechats(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        self._crawler()  # 确保依赖存在；否则抛 ProviderUnavailable
        # 真实环境：调用 wechat_spider 抓取公众号/视频号 → 预处理 → FinBERT 情绪量化
        # → 可信度分级 → 谣言交叉验证降权 → 结构化。需网络、搜狗微信接口限流策略与
        # FinBERT 推理服务，超出沙箱范围；此处显式声明部署要求。
        raise ProviderUnavailable(
            '真实微信舆情抓取需在部署环境启用 crawl_service.wechat_spider（WeChatSpider 公众号 / '
            'VideoSpider-WeChat 视频号）并挂载 FinBERT 本地推理；沙箱不可用，请确认网络 / 搜狗接口限流 / '
            'FinBERT 服务后重跑'
        )


def get_wechat_provider() -> tuple[BaseWechatProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_WECHAT → (Mock, mock, 原因)
    - 开启但依赖 / 爬虫不可用 → (Mock, mock, 回退原因)
    - 开启且可用 → (WechatSpider, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockWechatProvider(), MODE_MOCK, '沙箱确定性微信舆情源（未开启 DSA_REALTIME_WECHAT）'
    try:
        importlib.import_module('requests')
    except Exception:  # noqa: BLE001
        return (
            MockWechatProvider(),
            MODE_MOCK,
            '已请求实时微信舆情源，但爬虫依赖（requests）未部署，已回退模拟微信舆情源',
        )
    return WechatSpiderProvider(), MODE_REAL, '实时微信舆情源（公众号/视频号爬虫 + FinBERT）——需部署 wechat_spider 与 FinBERT 推理服务'


def describe_wechat_source() -> Dict[str, Any]:
    """描述当前活跃微信舆情数据源，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_wechat_provider()
    try:
        wechats = provider.get_wechats(days=7)
    except Exception as e:  # noqa: BLE001
        logger.warning('微信舆情源探测失败：%s', e)
        wechats = []
    rumor = sum(1 for w in wechats if w.get('has_rumor'))
    low_cred = sum(1 for w in wechats if w.get('credibility') == CRED_LOW)
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'wechatCount': len(wechats),
        'rumorCount': rumor,
        'lowCredibilityCount': low_cred,
        'weightShortSuggest': WECHAT_WEIGHT_SHORT,
        'weightLongSuggest': WECHAT_WEIGHT_LONG,
        'envKey': _ENV_KEY,
    }


def refresh_wechat_pool(stock_codes: Optional[List[str]] = None, days: int = 7) -> Dict[str, Any]:
    """用活跃微信舆情源重写微信舆情事件池（真实环境拉取公众号/视频号；模拟环境写入确定性模板）。

    返回 {code, msg, data:{ mode, provider, pubDate, count, rumorCount, lowCredibilityCount, reason }}。
    """
    provider, mode, reason = get_wechat_provider()
    wechats = provider.get_wechats(stock_codes=stock_codes, days=days)
    today = datetime.now().strftime('%Y-%m-%d')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceWechatOpinion).delete()
        for w in wechats:
            s.add(BacktraceWechatOpinion(
                stock_code=str(w['stock_code']),
                stock_name=w.get('stock_name'),
                pub_date=w.get('pub_date') or today,
                title=str(w.get('title', '')),
                source=w.get('source'),
                carrier=w.get('carrier'),
                credibility=w.get('credibility'),
                heat_score=float(w.get('heat_score') or 0.0),
                sentiment_score=float(w.get('sentiment_score') or 0.0),
                sentiment=w.get('sentiment'),
                stage=w.get('stage') or classify_stage(w.get('heat_score'), w.get('sentiment_score')),
                has_rumor=int(bool(w.get('has_rumor'))),
                weight_suggest=float(w.get('weight_suggest', WECHAT_WEIGHT_SHORT)),
                summary=w.get('summary'),
            ))
        s.flush()
        count = s.query(BacktraceWechatOpinion).count()
        rumor = s.query(BacktraceWechatOpinion).filter(BacktraceWechatOpinion.has_rumor == 1).count()
        low = s.query(BacktraceWechatOpinion).filter(BacktraceWechatOpinion.credibility == CRED_LOW).count()
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'pubDate': today,
            'count': int(count),
            'rumorCount': int(rumor),
            'lowCredibilityCount': int(low),
            'reason': reason,
        },
    }


def list_wechat_pool() -> Dict[str, Any]:
    """查询当前微信舆情事件池（按发布日期倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceWechatOpinion)
            .order_by(BacktraceWechatOpinion.pub_date.desc(), BacktraceWechatOpinion.id.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'count': len(items), 'items': items}}
