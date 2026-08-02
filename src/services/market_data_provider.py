# -*- coding: utf-8 -*-
"""可插拔实时数据源适配器（DSA-BACKTRACE-V1.0 #23，外挂微服务，不改动 DSA 内核）。

把 #20~#22 闭环预警链路中的「信号源 / 因子累积 / 大涨回溯池」从确定性 mock 升级为
可切换的**生产数据源适配器**：

  - 沙箱（默认）：走确定性 mock，接口契约不变，全链路可端到端验证；
  - 真实环境：设置环境变量 DSA_REALTIME_MARKET=1 后，切换为 AkShare 实时行情 /
    龙虎榜 / 机构调研接口；若 akshare 未安装或调用失败，**优雅回退** mock 并记录原因，
    保证回溯闭环在任意环境都能运转。

设计原则（对齐 §7 决策权坚守）：
  - 所有打分 / 加权 / 分级仍为数学编排，数据源只负责「喂什么标的与信号」，不介入决策；
  - DSA 内核 propagate_shock 零改动；因子库仍由真实归因累积（#17）替代 preset；
  - 切换零代码改动：仅通过环境变量控制，向后兼容既有 mock 行为。
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import BacktraceScreenPool, DatabaseManager

logger = logging.getLogger(__name__)

MODE_REAL = 'real'
MODE_MOCK = 'mock'

# 真实环境开关（默认关闭 → mock）。取值 '1' / 'true' / 'yes' 视为开启。
_ENV_KEY = 'DSA_REALTIME_MARKET'


class ProviderUnavailable(Exception):
    """数据源暂不可用（未安装依赖 / 调用失败 / 限流）。"""


class BaseMarketProvider:
    """统一数据源接口：大涨标的池 / 龙虎榜 / 机构调研。

    所有方法返回「标准字段字典列表」，下游闭环扫描与 Agent 深挖按字段消费，
    与具体数据源解耦。
    """

    #: 数据源可读名（前端展示用）
    label: str = 'base'

    def get_surging_stocks(
        self, limit: int = 200, gain_threshold: float = 5.0
    ) -> List[Dict[str, Any]]:
        """当日大涨标的池（涨幅榜 / 涨停 / 放量大涨）。

        返回字段：stock_code, stock_name, daily_gain, amount_yi, industry,
        rise_start_date, gain_type, consecutive_days
        """
        raise NotImplementedError

    def get_dragon_tiger_list(self, trade_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """龙虎榜（游资 / 活跃席位动向）。

        返回字段：stock_code, stock_name, net_buy, reason, branch_list
        """
        raise NotImplementedError

    def get_institution_surveys(
        self, stock_code: Optional[str] = None, days: int = 30
    ) -> List[Dict[str, Any]]:
        """机构调研（电话会 / 现场调研纪要线索）。

        返回字段：stock_code, stock_name, survey_date, org_count, summary
        """
        raise NotImplementedError


class MockMarketProvider(BaseMarketProvider):
    """确定性模拟数据源：复用反向归因系统的内置大涨标的池，龙虎榜 / 调研为模板样本。

    用于沙箱验证与真实数据源不可用时的回退，保证接口契约稳定。
    """

    label = '模拟数据源（确定性 mock）'

    def __init__(self) -> None:
        # 复用同一大涨池，杜绝两套 mock 数据漂移
        from src.services.backtrace_service import _MOCK_POOL

        self._pool = _MOCK_POOL

    def get_surging_stocks(
        self, limit: int = 200, gain_threshold: float = 5.0
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in self._pool:
            if float(row.get('daily_gain') or 0.0) < gain_threshold:
                continue
            out.append(
                {
                    'stock_code': row['stock_code'],
                    'stock_name': row['stock_name'],
                    'daily_gain': float(row['daily_gain']),
                    'amount_yi': float(row.get('amount_yi') or 0.0),
                    'industry': row.get('industry'),
                    'rise_start_date': row.get('rise_start_date'),
                    'gain_type': row.get('gain_type'),
                    'consecutive_days': int(row.get('consecutive_days') or 1),
                }
            )
        return out[:limit]

    def get_dragon_tiger_list(self, trade_date: Optional[str] = None) -> List[Dict[str, Any]]:
        # 模板样本：真实环境由 AkShare 龙虎榜替换
        samples = [
            {'stock_code': '688981', 'stock_name': '中芯国际', 'net_buy': 3.21,
             'reason': '机构席位净买入居前', 'branch_list': ['沪股通专用', '机构专用']},
            {'stock_code': '300750', 'stock_name': '宁德时代', 'net_buy': 2.04,
             'reason': '游资接力上榜', 'branch_list': ['华泰证券天津东丽', '东方财富拉萨']},
            {'stock_code': '002594', 'stock_name': '比亚迪', 'net_buy': 1.57,
             'reason': '知名游资上榜', 'branch_list': ['国泰君安上海江苏路']},
        ]
        return samples

    def get_institution_surveys(
        self, stock_code: Optional[str] = None, days: int = 30
    ) -> List[Dict[str, Any]]:
        samples = [
            {'stock_code': '688981', 'stock_name': '中芯国际', 'survey_date': '2026-07-20',
             'org_count': 42, 'summary': '先进制程产能利用率与订单能见度交流'},
            {'stock_code': '300750', 'stock_name': '宁德时代', 'survey_date': '2026-07-15',
             'org_count': 35, 'summary': '动力电池海外订单与储能出货展望'},
        ]
        if stock_code:
            samples = [s for s in samples if s['stock_code'] == stock_code]
        return samples


class AkShareMarketProvider(BaseMarketProvider):
    """真实行情数据源（AkShare）：懒加载依赖，缺失或失败即抛 ProviderUnavailable。

    仅在 DSA_REALTIME_MARKET=1 时由工厂构造；方法内按需 import akshare，
    避免在沙箱（无该依赖）导入期即报错。
    """

    label = '实时数据源（AkShare）'

    def _ak(self):
        try:
            return importlib.import_module('akshare')
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'akshare 未安装：{e}')

    def get_surging_stocks(
        self, limit: int = 200, gain_threshold: float = 5.0
    ) -> List[Dict[str, Any]]:
        ak = self._ak()
        try:
            df = ak.stock_zh_a_spot_em()
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'AkShare 涨幅榜调用失败：{e}')
        df = df[df['涨跌幅'] >= gain_threshold].sort_values('涨跌幅', ascending=False).head(limit)
        out: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            out.append(
                {
                    'stock_code': str(r.get('代码', '')),
                    'stock_name': str(r.get('名称', '')),
                    'daily_gain': float(r.get('涨跌幅') or 0.0),
                    'amount_yi': round(float(r.get('成交额') or 0) / 1e8, 2),
                    'industry': str(r.get('所属行业') or ''),
                    'rise_start_date': None,
                    'gain_type': '涨幅榜',
                    'consecutive_days': 1,
                }
            )
        return out

    def get_dragon_tiger_list(self, trade_date: Optional[str] = None) -> List[Dict[str, Any]]:
        ak = self._ak()
        try:
            df = ak.stock_lhb_detail_em(date=trade_date) if trade_date else ak.stock_lhb_detail_em()
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'AkShare 龙虎榜调用失败：{e}')
        out: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            out.append(
                {
                    'stock_code': str(r.get('代码', '')),
                    'stock_name': str(r.get('名称', '')),
                    'net_buy': float(r.get('净额') or r.get('NH 净流入') or 0.0),
                    'reason': str(r.get('解读') or ''),
                    'branch_list': [str(r.get('营业部名称', ''))] if r.get('营业部名称') else [],
                }
            )
        return out

    def get_institution_surveys(
        self, stock_code: Optional[str] = None, days: int = 30
    ) -> List[Dict[str, Any]]:
        ak = self._ak()
        try:
            df = ak.stock_jgdy_em()
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f'AkShare 机构调研调用失败（接口可能已下线）：{e}')
        out: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            code = str(r.get('代码', ''))
            if stock_code and code != stock_code:
                continue
            out.append(
                {
                    'stock_code': code,
                    'stock_name': str(r.get('名称', '')),
                    'survey_date': str(r.get('调研日期') or ''),
                    'org_count': int(r.get('机构家数') or 0),
                    'summary': str(r.get('接待方式') or ''),
                }
            )
        return out


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def get_market_provider() -> tuple[BaseMarketProvider, str, str]:
    """返回 (provider, mode, reason)。

    - 未开启 DSA_REALTIME_MARKET → (Mock, mock, 原因)
    - 开启但 akshare 不可用 → (Mock, mock, 回退原因)
    - 开启且可用 → (AkShare, real, 原因)
    """
    want_real = os.environ.get(_ENV_KEY, '').strip().lower() in ('1', 'true', 'yes')
    if not want_real:
        return MockMarketProvider(), MODE_MOCK, '沙箱确定性数据源（未开启 DSA_REALTIME_MARKET）'
    try:
        importlib.import_module('akshare')
    except Exception:  # noqa: BLE001
        return (
            MockMarketProvider(),
            MODE_MOCK,
            '已请求实时数据源，但 akshare 未安装，已回退模拟数据源（请 pip install akshare）',
        )
    return AkShareMarketProvider(), MODE_REAL, '实时数据源（AkShare）——请确保网络可达并 pip install akshare'


def describe_source() -> Dict[str, Any]:
    """描述当前活跃数据源，供前端标识与真实环境适配检查。"""
    provider, mode, reason = get_market_provider()
    try:
        surging = provider.get_surging_stocks(limit=200)
    except Exception as e:  # noqa: BLE001
        logger.warning('数据源探测失败：%s', e)
        surging = []
    return {
        'provider': type(provider).__name__,
        'label': provider.label,
        'mode': mode,
        'reason': reason,
        'surgingCount': len(surging),
        'envKey': _ENV_KEY,
    }


def refresh_screen_pool(limit: int = 200) -> Dict[str, Any]:
    """用活跃数据源重写当日大涨回溯池（真实环境拉取涨幅榜；模拟环境重写确定性池）。

    返回 {code, msg, data:{ mode, provider, screenDate, count, reason }}。
    """
    provider, mode, reason = get_market_provider()
    stocks = provider.get_surging_stocks(limit=limit)
    today = _today_str()
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceScreenPool).filter_by(screen_date=today).delete()
        for st in stocks:
            s.add(
                BacktraceScreenPool(
                    screen_date=today,
                    stock_code=st['stock_code'],
                    stock_name=st['stock_name'],
                    daily_gain=float(st['daily_gain']),
                    amount_yi=float(st.get('amount_yi') or 0.0),
                    industry=st.get('industry'),
                    rise_start_date=st.get('rise_start_date'),
                    gain_type=st.get('gain_type'),
                    consecutive_days=int(st.get('consecutive_days') or 1),
                )
            )
        s.flush()
        count = len(stocks)
    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'mode': mode,
            'provider': type(provider).__name__,
            'screenDate': today,
            'count': count,
            'reason': reason,
        },
    }
