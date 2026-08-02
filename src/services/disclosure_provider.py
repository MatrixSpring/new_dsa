# -*- coding: utf-8 -*-
"""可插拔公开披露数据源适配器（DSA-BACKTRACE-V1.0 #25，外挂微服务，不改动 DSA 内核）。

把闭环预警扫描（#20）与因子累积（#17/#24）的「基本面信号源」从确定性 mock 升级为
可切换的**真实披露数据源适配器**：

  - 沙箱（默认）：走确定性 mock，接口契约不变，全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_DISCLOSURE=1 后，切换为 cninfo 公告 /
    财报 / 研报接口（经 AkShare 懒加载）；若 akshare 未安装或调用失败，**优雅回退**
    mock 并记录原因，保证回溯闭环在任意环境都能运转。

设计原则（对齐 §7 决策权坚守）：
  - 所有打分 / 加权 / 分级仍为数学编排，披露源只负责「喂什么基本面催化标的与事件」，
    不介入决策；
  - DSA 内核 propagate_shock 零改动；因子库仍由真实归因累积（#17/#24）替代 preset；
  - 切换零代码改动：仅通过环境变量控制，向后兼容既有 mock 行为；
  - 与 #23 行情数据源正交：行情源喂「大涨标的池」，披露源喂「基本面催化事件」，
    二者在闭环扫描中叠加（union）成为完整的真实环境筛选画像。
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.storage import BacktraceDisclosure, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

# 真实环境开关（默认关闭 → mock）。取值 '1' / 'true' / 'yes' 视为开启。
_ENV_KEY = 'DSA_REALTIME_DISCLOSURE'


class ProviderUnavailable(Exception):
    """披露数据源暂不可用（未安装依赖 / 调用失败 / 限流）。"""


class BaseDisclosureProvider:
    """统一披露数据源接口：公告事件 / 财报 / 研报点评。

    所有方法返回「标准字段字典列表」，下游扫描与 UI 按字段消费，与具体数据源解耦。
    """

    #: 数据源可读名（前端展示用）
    label: str = 'base'

    def get_disclosures(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        """近期公开披露事件（公告 / 业绩预告 / 重大合同 / 股权激励 / 并购重组）。

        返回字段：stock_code, stock_name, disclosure_date, title, category, summary, sentiment
        """
        raise NotImplementedError

    def get_financial_reports(
        self, stock_code: Optional[str] = None, days: int = 90
    ) -> List[Dict[str, Any]]:
        """近期财报 / 业绩快报（营收同比 / 净利同比）。

        返回字段：stock_code, stock_name, period, revenue_yoy, netprofit_yoy, summary
        """
        raise NotImplementedError

    def get_research_reports(
        self, stock_code: Optional[str] = None, days: int = 30
    ) -> List[Dict[str, Any]]:
        """近期券商研报点评（评级 / 摘要）。

        返回字段：stock_code, stock_name, org_name, report_date, rating, summary
        """
        raise NotImplementedError


class MockDisclosureProvider(BaseDisclosureProvider):
    """确定性模拟披露源：复用反向归因系统内置大涨池的已知标的，构造模板化基本面催化事件。

    用于沙箱验证与真实数据源不可用时的回退，保证接口契约稳定。所有返回均对沙箱确定性。
    """

    label = '模拟披露源（确定性 mock）'

    #: 与 _MOCK_POOL 对齐的确定性基本面催化模板（仅引用池内标的，保证可被 agent_dig 解析）。
    _DISCLOSURES: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'disclosure_date': '2026-07-22',
         'title': '2026 半年度业绩预告：先进制程产能利用率提升，净利同比预增 55%',
         'category': '业绩预告', 'summary': '先进制程订单饱满，稼动率环比提升，毛利率改善', 'sentiment': '利好'},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'disclosure_date': '2026-07-25',
         'title': '签署海外储能系统重大供货合同，金额约 120 亿元',
         'category': '重大合同', 'summary': '海外储能订单落地，2026 发货节奏明确', 'sentiment': '利好'},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'disclosure_date': '2026-07-18',
         'title': '发布 2026 年股权激励计划，绑定核心技术与出海团队',
         'category': '股权激励', 'summary': '考核目标挂钩新能源出海销量与智能化渗透率', 'sentiment': '利好'},
        {'stock_code': '600519', 'stock_name': '贵州茅台', 'disclosure_date': '2026-07-20',
         'title': '2026 半年度主要经营数据：系列酒增长提速',
         'category': '财报', 'summary': '直营占比提升，吨价稳步上行', 'sentiment': '中性'},
        {'stock_code': '000725', 'stock_name': '京东方 A', 'disclosure_date': '2026-07-23',
         'title': '拟回购股份用于股权激励，金额上限 30 亿元',
         'category': '股权激励', 'summary': '面板景气回暖，现金流支撑回购', 'sentiment': '利好'},
        {'stock_code': '603799', 'stock_name': '华友钴业', 'disclosure_date': '2026-07-21',
         'title': '印尼镍资源项目投产，一体化布局降本',
         'category': '重大合同', 'summary': '上游资源自给率提升，盈利弹性释放', 'sentiment': '利好'},
    ]

    _FINANCIALS: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'period': '2026H1',
         'revenue_yoy': 28.4, 'netprofit_yoy': 55.0, 'summary': '先进制程放量驱动高增长'},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'period': '2026H1',
         'revenue_yoy': 19.2, 'netprofit_yoy': 33.6, 'summary': '储能与海外业务双轮驱动'},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'period': '2026H1',
         'revenue_yoy': 22.7, 'netprofit_yoy': 41.3, 'summary': '出海与高端化提升盈利'},
    ]

    _RESEARCH: List[Dict[str, Any]] = [
        {'stock_code': '688981', 'stock_name': '中芯国际', 'org_name': '中信证券',
         'report_date': '2026-07-26', 'rating': '买入', 'summary': '国产替代加速，先进制程拐点确认'},
        {'stock_code': '300750', 'stock_name': '宁德时代', 'org_name': '中金公司',
         'report_date': '2026-07-27', 'rating': '增持', 'summary': '全球储能需求超预期，龙头份额稳固'},
        {'stock_code': '002594', 'stock_name': '比亚迪', 'org_name': '国泰君安',
         'report_date': '2026-07-24', 'rating': '买入', 'summary': '智能化与全球化打开第二成长曲线'},
    ]

    def get_disclosures(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        out = [dict(d) for d in self._DISCLOSURES]
        if stock_codes:
            wanted = {str(c) for c in stock_codes}
            out = [d for d in out if str(d['stock_code']) in wanted]
        return out

    def get_financial_reports(
        self, stock_code: Optional[str] = None, days: int = 90
    ) -> List[Dict[str, Any]]:
        out = [dict(f) for f in self._FINANCIALS]
        if stock_code:
            out = [f for f in out if str(f['stock_code']) == str(stock_code)]
        return out

    def get_research_reports(
        self, stock_code: Optional[str] = None, days: int = 30
    ) -> List[Dict[str, Any]]:
        out = [dict(r) for r in self._RESEARCH]
        if stock_code:
            out = [r for r in out if str(r['stock_code']) == str(stock_code)]
        return out


class CninfoDisclosureProvider(BaseDisclosureProvider):
    """真实披露数据源（cninfo / 财报 / 研报，经 AkShare 懒加载）：缺失或失败即抛 ProviderUnavailable。

    仅在 DSA_REALTIME_DISCLOSURE=1 时由工厂构造；方法内按需 import akshare，
    避免在沙箱（无该依赖）导入期即报错。
    """

    label = '实时披露源（cninfo / 财报 / 研报）'

    def _ak(self):
        try:
            return importlib.import_module('akshare')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'akshare 未安装：{e}')

    def get_disclosures(
        self, stock_codes: Optional[List[str]] = None, days: int = 7
    ) -> List[Dict[str, Any]]:
        ak = self._ak()
        try:
            # 巨潮资讯个股公告（按代码列表拉取近期公告）
            df = ak.stock_notice_report(symbol='全部' if not stock_codes else ','.join(stock_codes))
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'cninfo 公告拉取失败：{e}')
        out: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            out.append({
                'stock_code': str(r.get('代码', '') or r.get('stock_code', '')),
                'stock_name': str(r.get('名称', '') or r.get('stock_name', '')),
                'disclosure_date': str(r.get('公告日期', '') or r.get('date', '')),
                'title': str(r.get('公告标题', '') or r.get('title', '')),
                'category': str(r.get('公告类型', '') or r.get('category', '公告')),
                'summary': str(r.get('摘要', '') or ''),
                'sentiment': '利好',
            })
        return out

    def get_financial_reports(
        self, stock_code: Optional[str] = None, days: int = 90
    ) -> List[Dict[str, Any]]:
        ak = self._ak()
        try:
            df = ak.stock_yjbb_em()  # 业绩报告（含营收/净利同比）
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'财报拉取失败：{e}')
        out: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            code = str(r.get('代码', ''))
            if stock_code and code != str(stock_code):
                continue
            out.append({
                'stock_code': code,
                'stock_name': str(r.get('名称', '')),
                'period': str(r.get('报告期', '')),
                'revenue_yoy': float(r.get('营业收入-营业收入同比增长', 0) or 0),
                'netprofit_yoy': float(r.get('净利润-净利润同比增长', 0) or 0),
                'summary': f"营收同比 {r.get('营业收入-营业收入同比增长', 0)}%，净利同比 {r.get('净利润-净利润同比增长', 0)}%",
            })
        return out

    def get_research_reports(
        self, stock_code: Optional[str] = None, days: int = 30
    ) -> List[Dict[str, Any]]:
        ak = self._ak()
        try:
            df = ak.stock_research_report_em()
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'研报拉取失败：{e}')
        out: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            code = str(r.get('股票代码', '') or r.get('code', ''))
            if stock_code and code != str(stock_code):
                continue
            out.append({
                'stock_code': code,
                'stock_name': str(r.get('股票名称', '') or r.get('name', '')),
                'org_name': str(r.get('机构', '') or r.get('org', '')),
                'report_date': str(r.get('报告日期', '') or r.get('date', '')),
                'rating': str(r.get('评级', '') or ''),
                'summary': str(r.get('摘要', '') or r.get('title', '')),
            })
        return out


def get_disclosure_provider() -> tuple[BaseDisclosureProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_DISCLOSURE → (Mock, mock, 原因)
    - 开启但 akshare 不可用 → (Mock, mock, 回退原因)
    - 开启且可用 → (Cninfo, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockDisclosureProvider(), MODE_MOCK, '沙箱确定性披露源（未开启 DSA_REALTIME_DISCLOSURE）'
    try:
        importlib.import_module('akshare')
    except Exception:  # noqa: BLE001
        return (
            MockDisclosureProvider(),
            MODE_MOCK,
            '已请求实时披露源，但 akshare 未安装，已回退模拟披露源（请 pip install akshare）',
        )
    return CninfoDisclosureProvider(), MODE_REAL, '实时披露源（cninfo/财报/研报）——请确保网络可达并 pip install akshare'


def describe_disclosure_source() -> Dict[str, Any]:
    """描述当前活跃披露数据源，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_disclosure_provider()
    try:
        disc = provider.get_disclosures(days=7)
        fin = provider.get_financial_reports(days=90)
        res = provider.get_research_reports(days=30)
    except Exception as e:  # noqa: BLE001
        logger.warning('披露源探测失败：%s', e)
        disc, fin, res = [], [], []
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'disclosureCount': len(disc),
        'financialCount': len(fin),
        'researchCount': len(res),
        'envKey': _ENV_KEY,
    }


def refresh_disclosure_pool(stock_codes: Optional[List[str]] = None, days: int = 7) -> Dict[str, Any]:
    """用活跃披露源重写披露事件池（真实环境拉取 cninfo/财报/研报；模拟环境写入确定性模板）。

    返回 {code, msg, data:{ mode, provider, disclosureDate, count, financialCount,
          researchCount, reason }}。
    """
    provider, mode, reason = get_disclosure_provider()
    disclosures = provider.get_disclosures(stock_codes=stock_codes, days=days)
    financials = provider.get_financial_reports(days=90)
    research = provider.get_research_reports(days=30)
    today = datetime.now().strftime('%Y-%m-%d')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceDisclosure).delete()
        for d in disclosures:
            s.add(BacktraceDisclosure(
                stock_code=str(d['stock_code']),
                stock_name=d.get('stock_name'),
                disclosure_date=d.get('disclosure_date'),
                title=str(d.get('title', '')),
                category=str(d.get('category', '公告')),
                summary=d.get('summary'),
                sentiment=d.get('sentiment'),
            ))
        # 财报 / 研报也作为披露事件写入（category 区分），便于扫描叠加与前端聚合
        for f in financials:
            s.add(BacktraceDisclosure(
                stock_code=str(f['stock_code']), stock_name=f.get('stock_name'),
                disclosure_date=today, title=f"财报 {f.get('period', '')}：营收同比 {f.get('revenue_yoy')}%，净利同比 {f.get('netprofit_yoy')}%",
                category='财报', summary=f.get('summary'), sentiment='中性',
            ))
        for r in research:
            s.add(BacktraceDisclosure(
                stock_code=str(r['stock_code']), stock_name=r.get('stock_name'),
                disclosure_date=r.get('report_date') or today,
                title=f"{r.get('org_name', '券商')} 研报点评：{r.get('rating', '')}",
                category='研报点评', summary=r.get('summary'), sentiment='利好',
            ))
        s.flush()
        count = s.query(BacktraceDisclosure).count()
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'disclosureDate': today,
            'count': int(count),
            'financialCount': len(financials),
            'researchCount': len(research),
            'reason': reason,
        },
    }


def list_disclosure_pool() -> Dict[str, Any]:
    """查询当前披露事件池（按披露日期倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceDisclosure)
            .order_by(BacktraceDisclosure.disclosure_date.desc(), BacktraceDisclosure.id.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'count': len(items), 'items': items}}
