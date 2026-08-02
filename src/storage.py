# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 存储层
===================================

职责：
1. 管理 SQLite 数据库连接（单例模式）
2. 定义 ORM 数据模型
3. 提供数据存取接口
4. 实现智能更新逻辑（断点续传）
"""

import atexit
from contextlib import contextmanager
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Tuple, Callable, TypeVar, Union

import pandas as pd
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    Integer,
    ForeignKey,
    Index,
    UniqueConstraint,
    Text,
    text,
    select,
    and_,
    or_,
    delete,
    desc,
    event,
    func,
    inspect,
    MetaData,
    Table,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Session,
)
from sqlalchemy.exc import IntegrityError, OperationalError

from src.agent.provider_trace import PROVIDER_TRACE_RETENTION_LIMIT
from src.config import get_config
from src.schemas.decision_profile import extract_legacy_decision_profile
from src.utils.sniper_points import extract_sniper_points, parse_sniper_value

logger = logging.getLogger(__name__)
T = TypeVar("T")
CURRENT_SCHEMA_VERSION = "2026-06-05-create-all-baseline"
INTELLIGENCE_ITEM_NULL_SCOPE_VALUE = "__dsa_null_scope__"

# SQLAlchemy ORM 基类
Base = declarative_base()

if TYPE_CHECKING:
    from src.search_service import SearchResponse


def utc_naive_now() -> datetime:
    """Return current UTC time without tzinfo for SQLite DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive_datetime(value: datetime) -> datetime:
    """Normalize aware datetimes to UTC-naive; treat naive values as UTC-naive."""
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# === 数据模型定义 ===

class DatabaseSchemaMigration(Base):
    """Applied database schema version marker."""

    __tablename__ = 'schema_migrations'

    version = Column(String(64), primary_key=True)
    description = Column(String(255), nullable=False)
    applied_at = Column(DateTime, default=datetime.now, nullable=False, index=True)


class XzscIndustryChain(Base):
    """新质生产力产业链图谱

    数据来源：微信公众号《华夏气候/制造前沿》文章
    《新质生产力解析：全景图+58大产业链图谱》
    https://mp.weixin.qq.com/s/GfcGGYNruErxC1qVP9LyQQ

    与申万2021版 346 条三级产业链(sw_industry_chain_dict)互补：
    本表侧重新质生产力主题赛道，按 L1 赛道 / L2 分类梳理，并补充结构(segments)。
    """

    __tablename__ = 'xzsc_industry_chain'

    id = Column(Integer, primary_key=True, autoincrement=True)
    no = Column(Integer, nullable=False, unique=True, index=True)          # 序号 1-58
    name = Column(String(128), nullable=False, index=True)                 # 产业链名称
    l1 = Column(String(64), nullable=False, index=True)                    # 一级赛道
    l2 = Column(String(64), nullable=True, index=True)                     # 二级分类
    summary = Column(Text, nullable=True)                                  # 一句话定义/定位
    segments = Column(Text, nullable=True)                                 # JSON: {阶段: [环节...]}
    source_name = Column(String(256), nullable=True)
    source_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)

    def to_dict(self) -> Dict[str, Any]:
        segs: Dict[str, Any] = {}
        if self.segments:
            try:
                segs = json.loads(self.segments)
            except Exception:
                segs = {}
        return {
            "id": self.id,
            "no": self.no,
            "name": self.name,
            "l1": self.l1,
            "l2": self.l2,
            "summary": self.summary,
            "segments": segs,
            "source_name": self.source_name,
            "source_url": self.source_url,
        }


class StockDaily(Base):
    """
    股票日线数据模型
    
    存储每日行情数据和计算的技术指标
    支持多股票、多日期的唯一约束
    """
    __tablename__ = 'stock_daily'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 股票代码（如 600519, 000001）
    code = Column(String(10), nullable=False, index=True)
    
    # 交易日期
    date = Column(Date, nullable=False, index=True)
    
    # OHLC 数据
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    
    # 成交数据
    volume = Column(Float)  # 成交量（股）
    amount = Column(Float)  # 成交额（元）
    pct_chg = Column(Float)  # 涨跌幅（%）
    
    # 技术指标
    ma5 = Column(Float)
    ma10 = Column(Float)
    ma20 = Column(Float)
    volume_ratio = Column(Float)  # 量比
    
    # 数据来源
    data_source = Column(String(50))  # 记录数据来源（如 AkshareFetcher）
    
    # 更新时间
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 唯一约束：同一股票同一日期只能有一条数据
    __table_args__ = (
        UniqueConstraint('code', 'date', name='uix_code_date'),
        Index('ix_code_date', 'code', 'date'),
    )
    
    def __repr__(self):
        return f"<StockDaily(code={self.code}, date={self.date}, close={self.close})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'code': self.code,
            'date': self.date,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'amount': self.amount,
            'pct_chg': self.pct_chg,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'volume_ratio': self.volume_ratio,
            'data_source': self.data_source,
        }


class NewsIntel(Base):
    """
    新闻情报数据模型

    存储搜索到的新闻情报条目，用于后续分析与查询
    """
    __tablename__ = 'news_intel'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关联用户查询操作
    query_id = Column(String(64), index=True)

    # 股票信息
    code = Column(String(10), nullable=False, index=True)
    name = Column(String(50))

    # 搜索上下文
    dimension = Column(String(32), index=True)  # latest_news / risk_check / earnings / market_analysis / industry
    query = Column(String(255))
    provider = Column(String(32), index=True)

    # 新闻内容
    title = Column(String(300), nullable=False)
    snippet = Column(Text)
    url = Column(String(1000), nullable=False)
    source = Column(String(100))
    published_date = Column(DateTime, index=True)

    # 入库时间
    fetched_at = Column(DateTime, default=datetime.now, index=True)
    query_source = Column(String(32), index=True)  # bot/web/cli/system
    requester_platform = Column(String(20))
    requester_user_id = Column(String(64))
    requester_user_name = Column(String(64))
    requester_chat_id = Column(String(64))
    requester_message_id = Column(String(64))
    requester_query = Column(String(255))

    __table_args__ = (
        UniqueConstraint('url', name='uix_news_url'),
        Index('ix_news_code_pub', 'code', 'published_date'),
    )

    def __repr__(self) -> str:
        return f"<NewsIntel(code={self.code}, title={self.title[:20]}...)>"


class IntelligenceSource(Base):
    """可配置资讯源。"""

    __tablename__ = 'intelligence_sources'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    source_type = Column(String(32), nullable=False, default='rss', index=True)
    url = Column(String(1000), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    scope_type = Column(String(32), nullable=False, default='market', index=True)
    scope_value = Column(String(64), index=True)
    market = Column(String(32), nullable=False, default='cn', index=True)
    description = Column(Text)
    last_status = Column(String(32))
    last_error = Column(Text)
    last_fetched_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index('ix_intel_source_scope', 'scope_type', 'scope_value', 'market'),
    )


class IntelligenceItem(Base):
    """沉淀后的资讯 / 情报条目。"""

    __tablename__ = 'intelligence_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey('intelligence_sources.id', ondelete='SET NULL'), nullable=True, index=True)
    source_name = Column(String(100), index=True)
    source_type = Column(String(32), nullable=False, default='rss', index=True)
    title = Column(String(300), nullable=False)
    summary = Column(Text)
    url = Column(String(1000), nullable=False, index=True)
    source = Column(String(100))
    published_at = Column(DateTime, index=True)
    fetched_at = Column(DateTime, default=datetime.now, index=True)
    scope_type = Column(String(32), nullable=False, default='market', index=True)
    scope_value = Column(String(64), nullable=False, default=INTELLIGENCE_ITEM_NULL_SCOPE_VALUE, index=True)
    market = Column(String(32), nullable=False, default='cn', index=True)
    raw_payload = Column(Text)

    __table_args__ = (
        UniqueConstraint(
            'source_id',
            'url',
            'scope_type',
            'scope_value',
            'market',
            name='uix_intel_item_source_scope_url',
        ),
        Index('ix_intel_item_scope_time', 'scope_type', 'scope_value', 'market', 'published_at'),
        Index('ix_intel_item_fetch_time', 'fetched_at'),
    )


class FundamentalSnapshot(Base):
    """
    基本面上下文快照（P0 write-only）。

    仅用于写入，主链路不依赖读取该表，便于后续回测/画像扩展。
    """
    __tablename__ = 'fundamental_snapshot'

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(String(64), nullable=False, index=True)
    code = Column(String(10), nullable=False, index=True)
    payload = Column(Text, nullable=False)
    source_chain = Column(Text)
    coverage = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_fundamental_snapshot_query_code', 'query_id', 'code'),
        Index('ix_fundamental_snapshot_created', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<FundamentalSnapshot(query_id={self.query_id}, code={self.code})>"


class CompanyProfile(Base):
    """
    上市公司全维度信息表（company_profile）。

    汇总系统已有公司信息，并按业务维度扩展。字段分组对应需求：
      1) 公司基础信息  2) 股东与分红  3) 估值指标  4) 财务分析
      5) 商业与行业分析  6) 技术与研发  7) 其他
    JSON 类字段以 Text(JSON 字符串) 存储；identity + 合并元数据(data_sources/linked_chains)
    记录该行数据的来源与产业键关联，便于后续增量补充与溯源。
    """

    __tablename__ = 'company_profile'

    # ---- 身份标识 ----
    code = Column(String(10), primary_key=True, comment='归一化 6 位股票代码')
    name = Column(String(80), index=True, comment='公司名称')
    pinyin = Column(String(80), index=True, comment='名称拼音(检索用)')
    aliases = Column(Text, comment='别名列表(JSON)')
    exchange = Column(String(8), comment='交易所 SZ/SH/BJ')

    # ---- 1) 公司基础信息 ----
    total_shares = Column(Float, comment='总股本(股本)')
    float_shares = Column(Float, comment='流通股本')
    executives = Column(Text, comment='高管列表(JSON:[{name,title}])')
    employee_count = Column(Integer, comment='员工人数')
    net_assets = Column(Float, comment='净资产')
    net_asset_ratio = Column(Float, comment='净资产占比')
    big_goodwill = Column(Text, comment='大额商誉(JSON:{amount,note})')
    restricted_unlock = Column(Text, comment='限售解禁(JSON:[{date,amount,ratio}])')
    shareholder_households = Column(Integer, comment='股东户数')

    # ---- 2) 股东与分红 ----
    top_float_shareholders = Column(Text, comment='十大流通股东(JSON:[{name,shares,ratio}])')
    equity_pledges = Column(Text, comment='股权质押(JSON:[{holder,pledged,ratio}])')
    dividend_yield = Column(Float, comment='股息率')
    payout_ratio = Column(Float, comment='股利支付率')
    dividend_financing_ratio = Column(Float, comment='派现融资比')

    # ---- 3) 估值指标 ----
    price = Column(Float, comment='股价')
    total_market_cap = Column(Float, comment='总市值')
    float_market_cap = Column(Float, comment='流通市值')
    pe = Column(Float, comment='市盈率(PE)')
    pb = Column(Float, comment='市净率(PB)')
    ps = Column(Float, comment='市销率(PS)')

    # ---- 4) 财务分析 ----
    revenue = Column(Float, comment='营业收入')
    main_business_ratio = Column(Float, comment='主营占比')
    gross_profit = Column(Float, comment='毛利润')
    net_profit = Column(Float, comment='净利润')
    deduct_net_profit = Column(Float, comment='扣非净利润')
    net_margin = Column(Float, comment='净利率')
    cash_flow = Column(Float, comment='经营现金流')
    asset_liability_ratio = Column(Float, comment='资产负债率')
    revenue_composition = Column(Text, comment='营收构成(JSON:[{segment,amount,ratio}])')
    profit_composition = Column(Text, comment='利润构成(JSON:[{segment,amount,ratio}])')
    inventory_turnover_days = Column(Float, comment='存货周转天数')

    # ---- 5) 商业与行业分析 ----
    industry_cycle = Column(Text, comment='行业周期')
    policy_impact = Column(Text, comment='政策影响')
    business_model = Column(Text, comment='商业模式')
    market_size = Column(Text, comment='市场规模')
    industry_share = Column(Text, comment='行业市占率')
    pricing_power = Column(Text, comment='产品定价权')
    performance_drivers = Column(Text, comment='业绩驱动因子(JSON:[...])')
    customer_concentration = Column(Text, comment='客户集中度(JSON:[{customer,ratio}])')
    supplier_concentration = Column(Text, comment='供应商集中度(JSON:[{supplier,ratio}])')

    # ---- 6) 技术与研发 ----
    rd_expense = Column(Float, comment='研发费用')
    rd_headcount = Column(Integer, comment='研发人数')
    new_patents = Column(Integer, comment='新增专利')
    total_patents = Column(Integer, comment='存量专利')
    tech_layout = Column(Text, comment='技术布局(JSON/[...])')

    # ---- 7) 其他 ----
    highlights = Column(Text, comment='优点/亮点')
    main_risks = Column(Text, comment='主要风险')

    # ---- 8) 一致预期（机构盈利预测/评级，对标 Wind 一致预期数据库壁垒）----
    consensus_year = Column(Integer, comment='一致预期预测年度')
    consensus_eps = Column(Float, comment='一致预期EPS')
    consensus_eps_growth = Column(Float, comment='一致预期EPS同比增速(%)')
    consensus_net_profit = Column(Float, comment='一致预期净利润')
    consensus_revenue = Column(Float, comment='一致预期营业收入')
    consensus_rating = Column(String(16), comment='机构综合评级(买入/增持/中性/减持/卖出)')
    consensus_institutes = Column(Integer, comment='覆盖机构家数')
    consensus_target_price = Column(Float, comment='一致预期目标价')

    # ---- 9) ESG（环境/社会/治理评级）----
    esg_score = Column(Float, comment='ESG综合评分')
    esg_rating = Column(String(8), comment='ESG评级(AAA~CCC 或 AA~C)')
    esg_environment = Column(Float, comment='E环境分项得分')
    esg_social = Column(Float, comment='S社会分项得分')
    esg_governance = Column(Float, comment='G治理分项得分')
    esg_year = Column(Integer, comment='ESG数据年份')

    # ---- 合并元数据 ----
    data_sources = Column(Text, comment='数据来源(JSON:[...])')
    linked_chains = Column(Text, comment='关联产业链(JSON:[{chain_id,chain_name,role}])')

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('ix_company_profile_name', 'name'),
        Index('ix_company_profile_pinyin', 'pinyin'),
    )

    def __repr__(self) -> str:
        return f"<CompanyProfile(code={self.code}, name={self.name})>"

    def to_dict(self) -> Dict[str, Any]:
        """转字典，JSON 字段反序列化为对象。"""
        import json as _json
        d = {}
        for c in self.__table__.columns:
            v = getattr(self, c.name)
            if c.name in _JSON_COLUMNS:
                try:
                    v = _json.loads(v) if v else None
                except (ValueError, TypeError):
                    v = None
            d[c.name] = v
        return d


# company_profile 中 JSON 类型字段名集合
_JSON_COLUMNS = {
    'aliases', 'executives', 'big_goodwill', 'restricted_unlock',
    'top_float_shareholders', 'equity_pledges',
    'revenue_composition', 'profit_composition',
    'performance_drivers', 'customer_concentration', 'supplier_concentration',
    'tech_layout', 'data_sources', 'linked_chains',
}


# ---------------------------------------------------------------------------
# 设计文档新增表（§5.3）：产业链传导系数覆盖 / DSA 全局参数 / 公司风险标签
# 均为外挂扩展表，不修改既有 company_profile / xzsc_industry_chain 结构。
# ---------------------------------------------------------------------------
class ChainEdgeOverride(Base):
    """产业链自定义传导系数覆盖（页面4「自定义传导系数默认值」持久化）。

    覆盖默认 edges.coeff=0.6 / lag=5，写入后前端重调 propagate 刷新预测。
    """
    __tablename__ = 'chain_edge_override'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chain_id = Column(String(32), nullable=False, index=True)
    source_node = Column(String(64), nullable=False)
    target_node = Column(String(64), nullable=False)
    coeff = Column(Float, nullable=False, default=0.6)
    lag = Column(Integer, default=5)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('chain_id', 'source_node', 'target_node', name='uq_chain_edge'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'chainId': self.chain_id,
            'sourceNode': self.source_node,
            'targetNode': self.target_node,
            'coeff': self.coeff,
            'lag': self.lag,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class DsaGlobalParam(Base):
    """DSA 全局模型参数（页面8 统一管控：递归深度/系数阈值/风险衰减）。"""
    __tablename__ = 'dsa_global_params'

    id = Column(Integer, primary_key=True, autoincrement=True)
    param_key = Column(String(48), nullable=False, unique=True, index=True)
    param_value = Column(Float, nullable=False)
    param_desc = Column(String(128), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'paramKey': self.param_key,
            'paramValue': self.param_value,
            'paramDesc': self.param_desc,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class CompanyRiskTag(Base):
    """公司风险/利好标签（页面5「自动利好/利空识别写风险标签」持久化）。

    与 company_profile 解耦，避免 ALTER 既有宽表；GET /companies/{code} 时合并返回。
    """
    __tablename__ = 'company_risk_tags'

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    risk_tags = Column(Text, nullable=False, default='[]')  # JSON: [{tag, level, note, source}]
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint('code', name='uq_company_risk'),
    )

    def to_dict(self) -> Dict[str, Any]:
        tags: Any = []
        try:
            tags = json.loads(self.risk_tags) if self.risk_tags else []
        except (ValueError, TypeError):
            tags = []
        return {
            'id': self.id,
            'code': self.code,
            'riskTags': tags,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class ChainRiskFlag(Base):
    """产业链环节异常风险标记（页面4「行业异常自动标记风险」）。

    risk_type: price_up(涨价) / output_cut(减产) / oversupply(过剩) / other
    severity: 高/中/低
    """
    __tablename__ = 'chain_risk_flag'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chain_id = Column(String(32), nullable=False, index=True)
    node = Column(String(64), nullable=False)
    risk_type = Column(String(24), nullable=False, default='other')
    severity = Column(String(8), nullable=False, default='中')
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'chainId': self.chain_id,
            'node': self.node,
            'riskType': self.risk_type,
            'severity': self.severity,
            'note': self.note,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class ForecastBatchSnapshot(Base):
    """多周期前瞻预测批量结果快照（设计 §5.3 表1）。

    聚合 decision_signals 的四周期结论，供前瞻预测中心页查询。
    scope_type: event/industry/stock/portfolio；cycle: 1w/2w/1m/6m。
    """
    __tablename__ = 'forecast_batch_snapshot'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope_type = Column(String(16), nullable=False, index=True)
    scope_value = Column(String(64), nullable=True, index=True)
    cycle = Column(String(8), nullable=False, index=True)
    direction = Column(String(8), nullable=True)        # up/down/oscillation
    low_pct = Column(Float, nullable=True)
    high_pct = Column(Float, nullable=True)
    up_prob = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    core_driver = Column(Text, nullable=True)
    main_risk = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.now, index=True)
    job_run_id = Column(String(64), nullable=True)

    __table_args__ = (
        Index('ix_fbs_scope_cycle', 'scope_type', 'scope_value', 'cycle'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'scopeType': self.scope_type,
            'scopeValue': self.scope_value,
            'cycle': self.cycle,
            'direction': self.direction,
            'lowPct': self.low_pct,
            'highPct': self.high_pct,
            'upProb': self.up_prob,
            'confidence': self.confidence,
            'coreDriver': self.core_driver,
            'mainRisk': self.main_risk,
            'generatedAt': self.generated_at.isoformat() if self.generated_at else None,
            'jobRunId': self.job_run_id,
        }


class SchedulerJobRun(Base):
    """自动化任务运行日志（设计 §5.3 表4，替代现有内存日志底座）。"""
    __tablename__ = 'scheduler_job_run'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_key = Column(String(32), nullable=False, index=True)  # overnight/preopen/intraday/postclose/batch/archive
    started_at = Column(DateTime, default=datetime.now, index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=True)               # success/failed/running
    summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    __table_args__ = (
        Index('ix_sjr_job_key', 'job_key', 'started_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'jobKey': self.job_key,
            'startedAt': self.started_at.isoformat() if self.started_at else None,
            'finishedAt': self.finished_at.isoformat() if self.finished_at else None,
            'status': self.status,
            'summary': self.summary,
            'error': self.error,
        }


class IntelligenceItemImpact(Base):
    """情报结构化 5 字段 + AI 分级（设计 §2.2 / §5.2，外挂伴随表）。

    不 ALTER 既有 intelligence_items 宽表；按 item_id 关联，缺失即启发式补齐。
    impact_level: 高/中/低；impact_cycle: 1w/2w/1m/6m；impact_direction: 利好/利空/中性。
    """
    __tablename__ = 'intelligence_item_impact'

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(64), nullable=False, unique=True, index=True)
    impact_level = Column(String(8), nullable=True)        # 高/中/低
    impact_cycle = Column(String(8), nullable=True)        # 1w/2w/1m/6m
    impact_industry = Column(String(64), nullable=True)    # 关联产业链 id
    impact_direction = Column(String(8), nullable=True)    # 利好/利空/中性
    transmit_weight = Column(Float, nullable=True, default=0.5)  # 0~1
    graded_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'itemId': self.item_id,
            'impactLevel': self.impact_level,
            'impactCycle': self.impact_cycle,
            'impactIndustry': self.impact_industry,
            'impactDirection': self.impact_direction,
            'transmitWeight': self.transmit_weight,
            'gradedAt': self.graded_at.isoformat() if self.graded_at else None,
        }


class CrawledDocument(Base):
    """爬虫落地库（自动爬虫 + 长文本解析流水线 P0，外挂伴随表）。

    存放「抓取源 → 原始文本 → LLM 结构化解析」全链路产物；
    不改动既有 intelligence_items / company_profile 等宽表，仅通过 source_key 关联溯源。
    status: pending/fetched/parsed/failed。
    """

    __tablename__ = 'crawled_documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_key = Column(String(64), nullable=False, index=True)   # cninfo_announcement / morning_notes ...
    title = Column(String(255), nullable=False)
    doc_type = Column(String(32), nullable=False, default='policy')  # policy/report/prospectus/minutes
    raw_text = Column(Text, nullable=True)
    parsed_json = Column(Text, nullable=True)   # llm_parse_service 结构化结果(JSON 串)
    status = Column(String(16), nullable=False, default='pending', index=True)
    error = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=datetime.now)
    parsed_at = Column(DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        parsed: Any = None
        if self.parsed_json:
            try:
                parsed = json.loads(self.parsed_json)
            except (ValueError, TypeError):
                parsed = None
        return {
            'id': self.id,
            'sourceKey': self.source_key,
            'title': self.title,
            'docType': self.doc_type,
            'status': self.status,
            'error': self.error,
            'fetchedAt': self.fetched_at.isoformat() if self.fetched_at else None,
            'parsedAt': self.parsed_at.isoformat() if self.parsed_at else None,
            'rawLength': len(self.raw_text) if self.raw_text else 0,
            'parsed': parsed,
        }


# ======================================================================
# 反向归因回溯子系统（DSA-BACKTRACE-V1.0，外挂伴随表，不改动 DSA 内核）
# 五层架构：行情筛选 → 历史回溯抓取 → LLM 归因推理 → 标准化输出 → DSA 联动
# ======================================================================

class BacktraceScreenPool(Base):
    """反向归因：每日大涨标的筛选池（SRS §3.1，外挂伴随表）。

    记录收盘后自动扫描得到的大涨个股回溯池：涨幅≥5% / 涨停 / 放量大涨 / 板块联动。
    """
    __tablename__ = 'backtrace_screen_pool'

    id = Column(Integer, primary_key=True, autoincrement=True)
    screen_date = Column(String(10), nullable=False, index=True)   # YYYY-MM-DD
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=False)
    daily_gain = Column(Float, nullable=False, default=0.0)         # 当日涨幅 %
    amount_yi = Column(Float, nullable=True)                        # 成交额(亿元)
    industry = Column(String(64), nullable=True)
    rise_start_date = Column(String(10), nullable=True)             # 拉升起始日
    gain_type = Column(String(32), nullable=True)                   # 涨停/放量大涨/板块联动
    consecutive_days = Column(Integer, nullable=True, default=1)    # 连续上涨天数
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'screenDate': self.screen_date,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'dailyGain': self.daily_gain,
            'amountYi': self.amount_yi,
            'industry': self.industry,
            'riseStartDate': self.rise_start_date,
            'gainType': self.gain_type,
            'consecutiveDays': self.consecutive_days,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceDisclosure(Base):
    """反向归因·真实环境适配：公开披露事件池（公告 / 财报 / 研报，#25 外挂伴随表）。

    由可插拔披露适配器（disclosure_provider）写入：沙箱走确定性 mock，
    真实环境（DSA_REALTIME_DISCLOSURE=1）由 cninfo / 财报接口拉取；缺失或失败优雅回退 mock。
    闭环预警扫描（#20）在 watchlist=None 时把披露池标的作为基本面筛选叠加，喂给真实归因累积。
    """
    __tablename__ = 'backtrace_disclosures'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    disclosure_date = Column(String(10), nullable=True)        # 披露日期 YYYY-MM-DD
    title = Column(String(255), nullable=False)                # 公告 / 财报 / 研报 标题
    category = Column(String(32), nullable=False)              # 业绩预告/重大合同/股权激励/并购重组/财报/研报点评
    summary = Column(Text, nullable=True)
    sentiment = Column(String(16), nullable=True)              # 利好/中性/利空
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'disclosureDate': self.disclosure_date,
            'title': self.title,
            'category': self.category,
            'summary': self.summary,
            'sentiment': self.sentiment,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceOpinion(Base):
    """反向归因·公开舆情子系统：头条舆情催化事件池（DSA-PUBLIC-OPINION-V1.0，#28 外挂伴随表）。

    由可插拔舆情适配器（opinion_provider）写入：沙箱走确定性 mock，
    真实环境（DSA_REALTIME_OPINION=1）由头条爬虫 + FinBERT 情绪量化链路拉取；
    缺失或失败优雅回退 mock。闭环预警扫描在 watchlist=None 时把舆情池标的作为
    情绪面筛选叠加（union），与 #25 披露（基本面）、#23 行情（大涨）正交互补。
    字段对齐文档 §四 统一结构化 JSON：sentiment_score(-1~1) / heat_score(0~1) /
    info_diff_stage(萌芽/发酵/狂热/退潮) / has_rumor(谣言降权标记)。
    """
    __tablename__ = 'backtrace_opinions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    opinion_date = Column(String(10), nullable=True)             # 舆情日期 YYYY-MM-DD
    title = Column(String(255), nullable=False)                  # 舆情标题
    source = Column(String(64), nullable=True)                   # 来源（头条/雪球/股吧/Mock）
    heat_score = Column(Float, nullable=True, default=0.0)       # 热度指数 0~1
    sentiment_score = Column(Float, nullable=True, default=0.0)  # 情绪得分 -1~1（FinBERT 代理）
    sentiment = Column(String(16), nullable=True)                # 利好/中性/利空
    stage = Column(String(16), nullable=True)                    # 萌芽/发酵/狂热/退潮
    summary = Column(Text, nullable=True)
    has_rumor = Column(Integer, nullable=False, default=0)       # 1=疑似谣言（已降权）
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'opinionDate': self.opinion_date,
            'title': self.title,
            'source': self.source,
            'heatScore': self.heat_score,
            'sentimentScore': self.sentiment_score,
            'sentiment': self.sentiment,
            'stage': self.stage,
            'summary': self.summary,
        'hasRumor': bool(self.has_rumor),
        'createdAt': self.created_at.isoformat() if self.created_at else None,
    }


class BacktraceWechatOpinion(Base):
    """反向归因·微信私域舆情子系统：微信舆情催化事件池（DSA-WECHAT-OPINION-V1.0，#31 外挂伴随表）。

    与 #28 头条公域舆情（BacktraceOpinion）正交、平行的「私域圈层情绪面催化事件源」：
    文档核心结论——微信私域舆情（公众号 / 视频号 / 付费社群线索）对 A 股短线题材、小票、
    突发利空、小众产业链催化影响力 > 头条公域舆情；但微信群聊 / 朋友圈 / 私聊无法稳定抓取。

    由可插拔微信舆情适配器（wechat_provider）写入：沙箱走确定性 mock，真实环境
    （DSA_REALTIME_WECHAT=1）由公众号爬虫（WeChatSpider）/ 视频号爬虫（VideoSpider-WeChat）
    + FinBERT 情绪量化 + 可信度分级链路拉取；缺失或失败优雅回退 mock。

    字段对齐文档 §五 解析与量化规则 + §二 对比表权重：
      - carrier（载体）：券商公众号 / 产业垂直号 / 财经视频号 / 付费社群线索 / 其他自媒体
      - credibility（可信度）：高（券商官方 / 正规产业号）/ 中（行业号）/ 低（无来源爆料，强制降权）
      - sentiment_score(-1~1) / heat_score(0~1) / stage(萌芽/发酵/狂热/退潮)
      - has_rumor(谣言降权标记) / weight_suggest(建议 DSA 权重：短线 0.20 / 长线 0.08)
    闭环预警扫描在 watchlist=None 时把微信池标的作为情绪面筛选叠加（union），
    与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#23 行情（大涨）正交互补。
    """
    __tablename__ = 'backtrace_wechat_opinions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    pub_date = Column(String(10), nullable=True)                  # 发布日期 YYYY-MM-DD
    title = Column(String(255), nullable=False)                  # 舆情标题
    source = Column(String(64), nullable=True)                   # 具体账号 / 渠道名
    carrier = Column(String(32), nullable=True)                  # 载体：券商公众号/产业垂直号/财经视频号/付费社群线索/其他自媒体
    credibility = Column(String(16), nullable=True)              # 可信度：高/中/低
    heat_score = Column(Float, nullable=True, default=0.0)       # 热度指数 0~1
    sentiment_score = Column(Float, nullable=True, default=0.0)  # 情绪得分 -1~1
    sentiment = Column(String(16), nullable=True)                # 利好/中性/利空
    stage = Column(String(16), nullable=True)                    # 萌芽/发酵/狂热/退潮
    has_rumor = Column(Integer, nullable=False, default=0)       # 1=疑似谣言（已降权）
    weight_suggest = Column(Float, nullable=True, default=0.20)  # 建议 DSA 短线权重（默认 0.20）
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'pubDate': self.pub_date,
            'title': self.title,
            'source': self.source,
            'carrier': self.carrier,
            'credibility': self.credibility,
            'heatScore': self.heat_score,
            'sentimentScore': self.sentiment_score,
            'sentiment': self.sentiment,
            'stage': self.stage,
            'hasRumor': bool(self.has_rumor),
            'weightSuggest': self.weight_suggest,
            'summary': self.summary,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceFlashOpinion(Base):
    """反向归因·短线快讯舆情子系统：快讯催化事件池（DSA-FLASH-OPINION-V1.0，#34 外挂伴随表）。

    与 #28 头条公域舆情（BacktraceOpinion）、#31 微信私域舆情（BacktraceWechatOpinion）
    正交、平行的「短线快讯情绪面催化事件源」：覆盖蓝图 §一.2 / §七类的
    财联社 / 华尔街见闻 / 金十（media_type='快讯'）+ 财新 / 券商中国 / e公司
    （media_type='深度媒体'，个股闪崩高频源头）。财联社为 A 股短线第一舆情平台，
    游资 / 量化第一参考资讯源，题材炒作核心发酵推手，对短线题材、盘中催化影响力极强。

    由可插拔快讯适配器（flash_provider）写入：沙箱走确定性 mock，真实环境
    （DSA_REALTIME_FLASH=1）由快讯爬虫（cls-crawler / Crawl4AI）+ FinBERT 情绪量化
    + 谣言降权链路拉取；缺失或失败优雅回退 mock。

    字段对齐蓝图 §一.2 / §三 / §五.2：
      - media_type（渠道类型）：快讯（财联社/华尔街见闻/金十）/ 深度媒体（财新/券商中国/e公司）
      - is_breaking（盘中突发）：1=盘中/早盘突发催化（短线节奏核心信号）
      - sentiment_score(-1~1) / heat_score(0~1) / stage(萌芽/发酵/狂热/退潮)
      - has_rumor(谣言降权标记) / weight_suggest(建议 DSA 短线权重：默认 0.22)
    闭环预警扫描在 watchlist=None 时把快讯池标的作为情绪面筛选叠加（union），
    与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#23 行情（大涨）正交互补。
    """
    __tablename__ = 'backtrace_flash_opinions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    pub_date = Column(String(10), nullable=True)                  # 发布日期 YYYY-MM-DD
    title = Column(String(255), nullable=False)                  # 快讯标题
    source = Column(String(64), nullable=True)                   # 具体渠道名（财联社/华尔街见闻/金十/e公司...）
    media_type = Column(String(16), nullable=True)               # 快讯 / 深度媒体
    is_breaking = Column(Integer, nullable=False, default=0)     # 1=盘中/早盘突发催化
    heat_score = Column(Float, nullable=True, default=0.0)       # 热度指数 0~1
    sentiment_score = Column(Float, nullable=True, default=0.0)  # 情绪得分 -1~1
    sentiment = Column(String(16), nullable=True)                # 利好/中性/利空
    stage = Column(String(16), nullable=True)                    # 萌芽/发酵/狂热/退潮
    has_rumor = Column(Integer, nullable=False, default=0)       # 1=疑似谣言（已降权）
    weight_suggest = Column(Float, nullable=True, default=0.22)  # 建议 DSA 短线权重（默认 0.22）
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'pubDate': self.pub_date,
            'title': self.title,
            'source': self.source,
            'mediaType': self.media_type,
            'isBreaking': bool(self.is_breaking),
            'heatScore': self.heat_score,
            'sentimentScore': self.sentiment_score,
            'sentiment': self.sentiment,
            'stage': self.stage,
            'hasRumor': bool(self.has_rumor),
            'weightSuggest': self.weight_suggest,
            'summary': self.summary,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceCommunityOpinion(Base):
    """反向归因·深度社区舆情子系统：社区讨论情绪催化事件池（DSA-COMMUNITY-OPINION-V1.0，#36 外挂伴随表）。

    与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#34 短线快讯
    （盘中催化）、#23 行情（大涨）正交、平行的「深度社区情绪面催化事件源」：覆盖蓝图 §一.2 的
    雪球 / 东财股吧 / 淘股吧 三类深度社区平台。社区平台对 A 股**散户情绪、短线题材、追涨杀跌、
    谣言发酵**影响力极强（雪球偏理性中长线、股吧/淘股吧偏情绪化短线），是六路可插拔信号源之一。

    由可插拔社区适配器（community_provider）写入：沙箱走确定性 mock，真实环境
    （DSA_REALTIME_COMMUNITY=1）由社区爬虫（xueqiu / guba / taoguba）+ FinBERT 情绪量化
    + 质量分层（雪球=高质量 / 股吧·淘股吧=噪音）+ 谣言降权链路拉取；缺失或失败优雅回退 mock。

    字段对齐蓝图 §一.2 / §三 / §五：
      - platform（平台）：雪球 / 东财股吧 / 淘股吧
      - quality（质量分层）：高质量（雪球）/ 普通 / 噪音（股吧·淘股吧，情绪极化、谣言高发）
      - is_hot（登社区热榜）：1=登热帖/热榜（短线情绪风向标）
      - post_count（讨论数）/ discussion_heat（讨论热度 0~1）
      - sentiment_score(-1~1) / sentiment(看多/中性/看空)
      - has_rumor(谣言降权标记) / weight_suggest(建议 DSA 短线权重：默认 0.13)
    闭环预警扫描在 watchlist=None 时把社区池标的作为情绪面筛选叠加（union），
    与 #25 披露 / #28 头条舆情 / #31 微信舆情 / #34 短线快讯 / #23 行情 正交互补。
    """
    __tablename__ = 'backtrace_community_opinions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    pub_date = Column(String(10), nullable=True)                  # 发布日期 YYYY-MM-DD
    title = Column(String(255), nullable=False)                  # 讨论标题
    platform = Column(String(16), nullable=True)                 # 平台（雪球/东财股吧/淘股吧）
    quality = Column(String(16), nullable=True)                  # 质量分层（高质量/普通/噪音）
    is_hot = Column(Integer, nullable=False, default=0)          # 1=登社区热榜/热帖榜
    post_count = Column(Integer, nullable=True, default=0)       # 讨论 / 帖子数
    discussion_heat = Column(Float, nullable=True, default=0.0)  # 讨论热度 0~1
    sentiment_score = Column(Float, nullable=True, default=0.0)  # 情绪得分 -1~1
    sentiment = Column(String(16), nullable=True)                # 看多/中性/看空
    has_rumor = Column(Integer, nullable=False, default=0)       # 1=疑似谣言（已降权）
    weight_suggest = Column(Float, nullable=True, default=0.13)  # 建议 DSA 短线权重（默认 0.13）
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'pubDate': self.pub_date,
            'title': self.title,
            'platform': self.platform,
            'quality': self.quality,
            'isHot': bool(self.is_hot),
            'postCount': self.post_count,
            'discussionHeat': self.discussion_heat,
            'sentimentScore': self.sentiment_score,
            'sentiment': self.sentiment,
            'hasRumor': bool(self.has_rumor),
            'weightSuggest': self.weight_suggest,
            'summary': self.summary,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceOverseasOpinion(Base):
    """反向归因·海外权威舆情子系统：海外权威资讯/机构评级催化事件池（DSA-OVERSEAS-OPINION-V1.0，#37 外挂伴随表）。

    与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#34 短线快讯
    （盘中催化）、#36 社区舆情（散户情绪）、#23 行情（大涨）正交、平行的「海外权威情绪面
    催化事件源」：覆盖蓝图 §一.6 的彭博 / 路透 / WSJ / Seeking Alpha 四类海外权威平台。
    海外权威源对 A 股**外资流向、机构评级、长线基本面预期**影响力极强（外资定价权、北向
    资金风向标），是七路可插拔信号源之一。

    由可插拔海外适配器（overseas_provider）写入：沙箱走确定性 mock，真实环境
    （DSA_REALTIME_OVERSEAS=1）由海外财经数据源（Bloomberg / Reuters / WSJ / SeekingAlpha
    抓取 + 机构评级 / 外资流向解析）拉取；缺失或失败优雅回退 mock。

    字段对齐蓝图 §一.6 / §三 / §五：
      - platform（平台）：彭博 / 路透 / WSJ / Seeking Alpha
      - region（区域）：海外
      - is_institution（机构评级/研报）：1=机构评级/研报事件（外资定价权确认）
      - rating（评级）：增持 / 中性 / 减持 / 无
      - sentiment_score(-1~1) / sentiment(看多/中性/看空)
      - impact_type（催化类型）：外资流向 / 评级调整 / 基本面 / 宏观
      - weight_suggest(建议 DSA 权重：短线 0.14 / 机构事件 0.18)
    闭环预警扫描在 watchlist=None 时把海外池标的作为情绪面筛选叠加（union），
    与 #25 披露 / #28 头条舆情 / #31 微信舆情 / #34 短线快讯 / #36 社区舆情 / #23 行情 正交互补。
    """
    __tablename__ = 'backtrace_overseas_opinions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    pub_date = Column(String(10), nullable=True)                  # 发布日期 YYYY-MM-DD
    title = Column(String(255), nullable=False)                  # 资讯标题
    platform = Column(String(24), nullable=True)                 # 平台（彭博/路透/WSJ/Seeking Alpha）
    region = Column(String(8), nullable=True, default='海外')    # 区域（海外）
    is_institution = Column(Integer, nullable=False, default=0)  # 1=机构评级/研报事件
    rating = Column(String(8), nullable=True)                    # 增持/中性/减持/无
    sentiment_score = Column(Float, nullable=True, default=0.0)  # 情绪得分 -1~1
    sentiment = Column(String(16), nullable=True)                # 看多/中性/看空
    impact_type = Column(String(16), nullable=True)              # 外资流向/评级调整/基本面/宏观
    weight_suggest = Column(Float, nullable=True, default=0.14)  # 建议 DSA 权重（短线 0.14 / 机构 0.18）
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'pubDate': self.pub_date,
            'title': self.title,
            'platform': self.platform,
            'region': self.region,
            'isInstitution': bool(self.is_institution),
            'rating': self.rating,
            'sentimentScore': self.sentiment_score,
            'sentiment': self.sentiment,
            'impactType': self.impact_type,
            'weightSuggest': self.weight_suggest,
            'summary': self.summary,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceVerticalMediaOpinion(Base):
    """反向归因·垂直专业财经媒体子系统：专业媒体报道/权威催化事件池（DSA-VERTICAL-MEDIA-OPINION-V1.0，#40 外挂伴随表）。

    与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#34 短线快讯
    （盘中催化）、#36 社区舆情（散户情绪）、#37 海外权威（外资/机构）、#23 行情（大涨）正交、
    平行的「垂直专业媒体情绪面催化事件源」：覆盖蓝图 §一.7 的财新 / 券商中国 / e公司（证券时报
    旗下） / 证券时报 / 上海证券报 / 第一财经 / 21世纪经济报道 七类经官方批准的专业财经媒体。
    垂直专业媒体对 A 股**官方指定信披媒体公信力、深度调研、监管追踪、行业权威解读**影响力强
    （证券时报 / e公司 / 上海证券报为法定信披媒体，财新 / 第一财经为深度独立财经），是八路
    可插拔信号源之一（#35 Kronos 技术面单独逐 alert 富化，不扩池）。

    由可插拔垂直媒体适配器（vertical_media_provider）写入：沙箱走确定性 mock，真实环境
    （DSA_REALTIME_VERTICAL_MEDIA=1）由垂直专业媒体抓取（财新/证券时报/e公司/上海证券报/
    第一财经 + 深度调研 / 监管追踪解析）拉取；缺失或失败优雅回退 mock。

    字段对齐蓝图 §一.7 / §三 / §五：
      - media_name（媒体名）：财新 / 券商中国 / e公司 / 证券时报 / 上海证券报 / 第一财经 / 21世纪经济报道
      - outlet（媒体分类）：官方指定信披媒体 / 专业财经媒体
      - is_official（官方指定信披媒体）：1=法定信披渠道（e公司/证券时报/上海证券报）
      - coverage_type（报道类型）：深度调研 / 快讯点评 / 监管追踪 / 行业解读
      - sentiment_score(-1~1) / sentiment(看多/中性/看空)
      - has_rumor(疑似谣言)：0/1（权威媒体极少，用于风控降权）
      - weight_suggest(建议 DSA 权重：短线 0.12 / 官方信披 0.15)
    闭环预警扫描在 watchlist=None 时把垂直专业媒体池标的作为情绪面筛选叠加（union），
    与 #25 披露 / #28 头条舆情 / #31 微信舆情 / #34 短线快讯 / #36 社区舆情 / #37 海外权威 /
    #23 行情 正交互补；并在 #38 六层信息圈层交叉验证中归入 L1 权威圈层。
    """
    __tablename__ = 'backtrace_vertical_media_opinions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    pub_date = Column(String(10), nullable=True)                  # 发布日期 YYYY-MM-DD
    title = Column(String(255), nullable=False)                  # 报道标题
    media_name = Column(String(24), nullable=True)               # 媒体名（财新/券商中国/e公司/证券时报/上海证券报/第一财经/21世纪经济报道）
    outlet = Column(String(24), nullable=True)                   # 媒体分类（官方指定信披媒体/专业财经媒体）
    is_official = Column(Integer, nullable=False, default=0)     # 1=官方指定信披媒体（法定信披渠道）
    coverage_type = Column(String(16), nullable=True)            # 深度调研/快讯点评/监管追踪/行业解读
    sentiment_score = Column(Float, nullable=True, default=0.0)  # 情绪得分 -1~1
    sentiment = Column(String(16), nullable=True)                # 看多/中性/看空
    has_rumor = Column(Integer, nullable=False, default=0)       # 1=疑似谣言（权威媒体极少，用于风控降权）
    weight_suggest = Column(Float, nullable=True, default=0.12)  # 建议 DSA 权重（短线 0.12 / 官方信披 0.15）
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'pubDate': self.pub_date,
            'title': self.title,
            'mediaName': self.media_name,
            'outlet': self.outlet,
            'isOfficial': bool(self.is_official),
            'coverageType': self.coverage_type,
            'sentimentScore': self.sentiment_score,
            'sentiment': self.sentiment,
            'hasRumor': bool(self.has_rumor),
            'weightSuggest': self.weight_suggest,
            'summary': self.summary,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceKronosSignal(Base):
    """反向归因·K 线技术面算力底座：逐只标的 Kronos 技术面信号（DSA-KRONOS-V1.0，#35 外挂伴随表）。

    与 #25 披露 / #28 头条舆情 / #31 微信舆情 / #34 短线快讯**本质不同**：Kronos 不是事件 /
    情绪催化源（不做 union 候选池叠加），而是**逐只 alert 的技术面算力底座**——对每只已扫描
    标的富化技术面信号（trend / 拐点 / 上涨·横盘·下跌三态概率 / 波动率 / 量能 / 持续性 / Alpha
    因子），并独立输出三类选股池（短线强势池 / 趋势反转池 / 风险预警池，见 kronos_service.kronos_pools）。

    由可插拔 Kronos 适配器（kronos_service）写入：沙箱走确定性 mock（按股票代码 hash 稳定分布，
    覆盖强势多头 / 高位顶部风险 / 底部反转三类场景），真实环境（DSA_REALTIME_KRONOS=1）由
    NeoQuasar 权重 + BSQ 球面量化 Tokenizer + 分层因果 Transformer 自回归推理；缺失权重 /
    torch / transformers / GPU 时优雅回退 mock。

    字段对齐蓝图 §一/§二/§四：
      - trend（趋势）：多头趋势 / 空头趋势 / 震荡
      - momentum（趋势强度 0~1）/ inflection_point（拐点：无顶部拐点 / 顶部拐点·高位见顶 / 底部拐点·下跌末端反转）
      - rise_prob / sideway_prob / down_prob（上涨 / 横盘 / 下跌三态概率分布，和≈1，Kronos 概率多路径预测）
      - volatility（波动率 0~1）/ volume_score（量能评分 0~1）
      - persistence（持续性文本，如「中期上升趋势，量价配合，可持续 1~2 周」）
      - factor_scores（JSON 文本）：由 BSQ Tokenizer 隐向量派生的候选 Alpha 量化因子列表 [{name, score}]
    风控硬约束（蓝图 §七）：K 线信号权重短线最高 0.35、长线最高 0.15，Kronos 仅输出技术参考，
    最终涨跌量化 / 中长期结论由 DSA 数学模型决定；新增因子须经历史回测验证方可入库。
    """
    __tablename__ = 'backtrace_kronos_signals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    trend = Column(String(16), nullable=True)                  # 多头趋势 / 空头趋势 / 震荡
    momentum = Column(Float, nullable=True, default=0.0)       # 趋势强度 0~1
    inflection_point = Column(String(32), nullable=True)       # 拐点（无顶部拐点 / 顶部拐点·高位见顶 / 底部拐点·下跌末端反转）
    rise_prob = Column(Float, nullable=True, default=0.0)      # 上涨概率 0~1
    sideway_prob = Column(Float, nullable=True, default=0.0)   # 横盘概率 0~1
    down_prob = Column(Float, nullable=True, default=0.0)      # 下跌概率 0~1
    volatility = Column(Float, nullable=True, default=0.0)     # 波动率 0~1
    volume_score = Column(Float, nullable=True, default=0.0)   # 量能评分 0~1
    persistence = Column(String(64), nullable=True)            # 持续性文本
    factor_scores = Column(Text, nullable=True)                # JSON 文本：候选 Alpha 因子 [{name, score}]
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        fs: List[Dict[str, Any]] = []
        if self.factor_scores:
            try:
                fs = json.loads(self.factor_scores)
            except Exception:  # noqa: BLE001
                fs = []
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'trend': self.trend,
            'momentum': self.momentum,
            'inflectionPoint': self.inflection_point,
            'riseProb': self.rise_prob,
            'sidewayProb': self.sideway_prob,
            'downProb': self.down_prob,
            'volatility': self.volatility,
            'volumeScore': self.volume_score,
            'persistence': self.persistence,
            'factorScores': fs,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceNewsDoc(Base):
    """反向归因：拉升前历史资讯回溯（SRS §3.2，外挂伴随表）。

    严格时间过滤：仅保留股价拉升启动日之前的内容（is_prior=1）；
    拉升后新闻（is_prior=0）剔除，禁止作为上涨原因（防事后强行归因）。
    """
    __tablename__ = 'backtrace_news_docs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    doc_type = Column(String(32), nullable=False)       # announcement/research/policy/industry/news
    source = Column(String(64), nullable=False)         # 来源名（巨潮/券商/财联社...）
    title = Column(String(255), nullable=False)
    published_at = Column(String(19), nullable=False)   # 原文发布时间
    raw_text = Column(Text, nullable=True)
    is_prior = Column(Integer, nullable=False, default=1)  # 1=拉升前(采用) 0=拉升后(剔除)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'docType': self.doc_type,
            'source': self.source,
            'title': self.title,
            'publishedAt': self.published_at,
            'isPrior': bool(self.is_prior),
            'rawLength': len(self.raw_text) if self.raw_text else 0,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceAttribution(Base):
    """反向归因：结构化归因结果（SRS §3.4，外挂伴随表）。

    result_json 存放固定 JSON 归因（stock_code / driving_factor / similar_history_case /
    trend_persistence_judge / suggest_adjust + 驱动分类 / 防幻觉护栏）。
    """
    __tablename__ = 'backtrace_attributions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=False)
    rise_start_date = Column(String(10), nullable=True)
    daily_gain = Column(Float, nullable=True)
    total_rise_days = Column(Integer, nullable=True)
    result_json = Column(Text, nullable=True)           # §3.4 结构化结果(JSON 串)
    drive_category = Column(String(32), nullable=True)  # 基本面事件驱动/题材情绪驱动/资金筹码驱动
    trend_judge = Column(String(32), nullable=True)     # 短期脉冲/中期趋势/长期主升
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        result: Any = None
        if self.result_json:
            try:
                result = json.loads(self.result_json)
            except (ValueError, TypeError):
                result = None
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'riseStartDate': self.rise_start_date,
            'dailyGain': self.daily_gain,
            'totalRiseDays': self.total_rise_days,
            'driveCategory': self.drive_category,
            'trendJudge': self.trend_judge,
            'result': result,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceLinkage(Base):
    """反向归因：DSA 系统联动记录（SRS §3.5，外挂伴随表）。

    归因结果自动分发：事件库入库 / 个股权重修正 / 产业链系数 / 预测重算 / 案例沉淀。
    """
    __tablename__ = 'backtrace_linkages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    attribution_id = Column(Integer, nullable=False, index=True)
    stock_code = Column(String(16), nullable=False, index=True)
    event_library_added = Column(Integer, nullable=False, default=0)
    fundamental_weight_delta = Column(Float, nullable=True)
    chain_coeff_delta = Column(Float, nullable=True)
    forecast_recompute = Column(Integer, nullable=False, default=0)
    case_banked = Column(Integer, nullable=False, default=0)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'attributionId': self.attribution_id,
            'stockCode': self.stock_code,
            'eventLibraryAdded': bool(self.event_library_added),
            'fundamentalWeightDelta': self.fundamental_weight_delta,
            'chainCoeffDelta': self.chain_coeff_delta,
            'forecastRecompute': bool(self.forecast_recompute),
            'caseBanked': bool(self.case_banked),
            'note': self.note,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceSectorReview(Base):
    """反向归因：批量板块复盘记录（SRS §3.6，外挂伴随表）。

    针对板块集体大涨，批量回溯板块内个股共同前置事件，输出板块景气判断、
    轮动逻辑、上下游传导链与共同催化分布。
    """
    __tablename__ = 'backtrace_sector_reviews'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sector_name = Column(String(64), nullable=False, index=True)
    rise_date = Column(String(16), nullable=True)
    prosperity = Column(String(32), nullable=True)
    member_count = Column(Integer, nullable=False, default=0)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'sectorName': self.sector_name,
            'riseDate': self.rise_date,
            'prosperity': self.prosperity,
            'memberCount': self.member_count,
            'resultJson': self.result_json,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceBacktest(Base):
    """反向归因：归因有效性回测校验记录（SRS §3.7，外挂伴随表）。

    将某次归因逻辑放入历史同类行情回测，统计历史胜率 / 平均涨幅 / 期望收益，
    并据此反向修正该次归因的置信度，规避事后强行归因。
    """
    __tablename__ = 'backtrace_backtests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    attribution_id = Column(Integer, nullable=False, index=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=False)
    drive_category = Column(String(32), nullable=True)
    samples = Column(Integer, nullable=False, default=0)       # 历史样本覆盖量
    win_rate = Column(Float, nullable=True)                    # 加权历史胜率 0~1
    avg_gain_1w = Column(Float, nullable=True)                 # 平均 1 周涨幅(%)
    avg_gain_1m = Column(Float, nullable=True)                 # 平均 1 月涨幅(%)
    avg_loss_1m = Column(Float, nullable=True)                 # 平均 1 月回撤(%)
    expectancy_1m = Column(Float, nullable=True)               # 期望 1 月净收益(%)
    confidence_raw = Column(Float, nullable=True)              # 归因原置信度(因子加权)
    confidence_adjusted = Column(Float, nullable=True)         # 回测修正后置信度
    verdict = Column(String(48), nullable=True)                # 历史有效性判定
    result_json = Column(Text, nullable=True)                  # 完整回测明细(JSON 串)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        result: Any = None
        if self.result_json:
            try:
                result = json.loads(self.result_json)
            except (ValueError, TypeError):
                result = None
        return {
            'id': self.id,
            'attributionId': self.attribution_id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'driveCategory': self.drive_category,
            'samples': self.samples,
            'winRate': self.win_rate,
            'avgGain1w': self.avg_gain_1w,
            'avgGain1m': self.avg_gain_1m,
            'avgLoss1m': self.avg_loss_1m,
            'expectancy1m': self.expectancy_1m,
            'confidenceRaw': self.confidence_raw,
            'confidenceAdjusted': self.confidence_adjusted,
            'verdict': self.verdict,
            'result': result,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceAgentSignal(Base):
    """反向归因：Agent 自主深挖小众突发事件信号（DSA-BACKTRACE-V1.0 增强，外挂伴随表）。

    在反向回溯（§3.1~§3.7）基础上，Agent 主动扫描拉升前窗口内的隐藏早期信号
    （机构调研 / 产业链异动 / 舆情小道消息 / 游资动向），按时间临近度 + 来源可信度
    + 相关度综合打分，输出信号时间线，反哺归因 driving_factor 的早期佐证强度。
    """

    __tablename__ = 'backtrace_agent_signals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    signal_type = Column(String(32), nullable=False, index=True)   # 机构调研/产业链异动/舆情小道消息/游资动向
    signal_date = Column(String(10), nullable=False, index=True)   # YYYY-MM-DD（拉升前）
    lead_days = Column(Integer, nullable=False)                    # 距拉升起始日的提前天数
    source = Column(String(64), nullable=False)
    summary = Column(Text, nullable=True)
    credibility = Column(Float, nullable=True)                     # 来源可信度 0~1
    relevance = Column(Float, nullable=True)                       # 与拉升的相关度 0~1
    score = Column(Float, nullable=True)                           # 综合得分 0~100
    is_early = Column(Integer, nullable=False, default=0)          # 1=小众早期信号(lead_days>=阈值)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'signalType': self.signal_type,
            'signalDate': self.signal_date,
            'leadDays': self.lead_days,
            'source': self.source,
            'summary': self.summary,
            'credibility': self.credibility,
            'relevance': self.relevance,
            'score': self.score,
            'isEarly': bool(self.is_early),
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceFactorLibrary(Base):
    """反向归因：高频上涨因子自动沉淀库（DSA-BACKTRACE-V1.0 增强，外挂伴随表）。

    将已验证的归因（§3.4）与回测（§3.7）结果按驱动因子聚合统计，沉淀为标准化
    「上涨因子库」：出现频次 / 历史胜率 / 平均涨幅 / 期望净收益 / 置信度，并反向
    支撑正向预判（输入早期信号 → 匹配因子库 → 输出上涨概率与建议动作）。
    """

    __tablename__ = 'backtrace_factor_library'

    id = Column(Integer, primary_key=True, autoincrement=True)
    factor_name = Column(String(128), nullable=False, index=True)   # 标准化因子名（驱动正文归一）
    factor_category = Column(String(32), nullable=False, index=True)  # 基本面/题材情绪/资金筹码
    occur_count = Column(Integer, nullable=False, default=0)         # 历史沉淀出现次数
    avg_win_rate = Column(Float, nullable=False, default=0.0)        # 历史胜率 0~1
    avg_gain_1w = Column(Float, nullable=False, default=0.0)         # 平均 1 周涨幅 %
    avg_gain_1m = Column(Float, nullable=False, default=0.0)         # 平均 1 月涨幅 %
    avg_loss_1m = Column(Float, nullable=False, default=0.0)         # 平均 1 月回撤 %（负）
    expectancy_1m = Column(Float, nullable=False, default=0.0)       # 期望 1 月净收益 %
    confidence = Column(Float, nullable=False, default=0.0)          # 因子置信度 0~1（随频次上升）
    sample_stocks = Column(Text, nullable=True)                      # 代表性样本标的 JSON
    last_updated = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'factorName': self.factor_name,
            'factorCategory': self.factor_category,
            'occurCount': self.occur_count,
            'avgWinRate': self.avg_win_rate,
            'avgGain1w': self.avg_gain_1w,
            'avgGain1m': self.avg_gain_1m,
            'avgLoss1m': self.avg_loss_1m,
            'expectancy1m': self.expectancy_1m,
            'confidence': self.confidence,
            'sampleStocks': json.loads(self.sample_stocks) if self.sample_stocks else [],
            'lastUpdated': self.last_updated.isoformat() if self.last_updated else None,
        }


class BacktraceScanAlert(Base):
    """反向归因：自动化闭环预警扫描结果（DSA-BACKTRACE-V1.0 #20，外挂伴随表）。

    把 #19 一键闭环编排为批量扫描：对大涨回溯池（或指定 watchlist）逐只跑
    闭环（Agent 深挖 → 因子预判 → 内核传导），按综合评分分级（强信号·重点关注 /
    中性·持续观察 / 弱信号·低关注），落库后供前端预警看板与 GET 查询消费。
    """

    __tablename__ = 'backtrace_scan_alerts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_batch = Column(String(32), nullable=False, index=True)      # 同一批次扫描标识
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64), nullable=True)
    chain_id = Column(String(32), nullable=True)
    predicted_prob = Column(Float, nullable=False, default=0.0)      # 正向预判上涨概率 0~1
    boost = Column(Float, nullable=False, default=0.0)               # 内核传导幅度增益（钳制[0,0.5]）
    signal_count = Column(Integer, nullable=False, default=0)        # 深挖隐藏信号总数
    early_count = Column(Integer, nullable=False, default=0)         # 小众早期信号数
    top_signal_score = Column(Float, nullable=False, default=0.0)    # 最高单条信号评分 0~100
    composite_score = Column(Float, nullable=False, default=0.0)     # 综合预警评分 0~1
    level = Column(String(32), nullable=False, default='弱信号·低关注')  # 预警级别
    created_at = Column(DateTime, default=datetime.now, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'scanBatch': self.scan_batch,
            'stockCode': self.stock_code,
            'stockName': self.stock_name,
            'chainId': self.chain_id,
            'predictedProb': self.predicted_prob,
            'boost': self.boost,
            'signalCount': self.signal_count,
            'earlyCount': self.early_count,
            'topSignalScore': self.top_signal_score,
            'compositeScore': self.composite_score,
            'level': self.level,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceScanBatch(Base):
    """反向归因：闭环预警扫描批次历史（DSA-BACKTRACE-V1.0 #21，外挂伴随表）。

    把 #20 自动化预警扫描包装为可调度任务：每次手动/定时/事件触发扫描后，
    聚合本次批次的分级计数（强/中/弱）、Top 标的与综合评分，落库供历史回看与
    收盘后定时预警追溯。
    """

    __tablename__ = 'backtrace_scan_batches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(32), nullable=False, index=True)       # 与 backtrace_scan_alerts.scan_batch 对应
    run_type = Column(String(16), nullable=False, default='manual')  # manual | schedule | event
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    total_scanned = Column(Integer, nullable=False, default=0)
    strong_count = Column(Integer, nullable=False, default=0)       # 强信号·重点关注
    neutral_count = Column(Integer, nullable=False, default=0)      # 中性·持续观察
    weak_count = Column(Integer, nullable=False, default=0)         # 弱信号·低关注
    top_stock = Column(String(16), nullable=True)
    top_stock_name = Column(String(64), nullable=True)
    top_composite = Column(Float, nullable=False, default=0.0)      # Top 标的综合预警评分 0~1
    created_at = Column(DateTime, default=datetime.now, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'batchId': self.batch_id,
            'runType': self.run_type,
            'scheduledAt': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'startedAt': self.started_at.isoformat() if self.started_at else None,
            'finishedAt': self.finished_at.isoformat() if self.finished_at else None,
            'totalScanned': self.total_scanned,
            'strongCount': self.strong_count,
            'neutralCount': self.neutral_count,
            'weakCount': self.weak_count,
            'topStock': self.top_stock,
            'topStockName': self.top_stock_name,
            'topComposite': self.top_composite,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class BacktraceScanSchedule(Base):
    """反向归因：闭环预警扫描调度配置（#21，单键配置行）。

    默认收盘后定时触发（周一至周五 15:30）。cron 为 5 段标准表达式
    （分 时 日 月 周），enabled 控制是否生效。
    """

    __tablename__ = 'backtrace_scan_schedule'

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(32), nullable=False, unique=True, default='default')
    cron = Column(String(32), nullable=False, default='30 15 * * 1-5')
    enabled = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'configKey': self.config_key,
            'cron': self.cron,
            'enabled': bool(self.enabled),
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class FactorMiningResult(Base):
    """自动因子挖掘闭环结果（P0-②）。记录每代因子及其 IC/多空收益，闭环保留最优。"""
    __tablename__ = 'factor_mining_result'
    id = Column(Integer, primary_key=True, autoincrement=True)
    generation = Column(Integer, index=True, comment='进化代次')
    factor_name = Column(String(80), index=True, comment='因子名')
    factor_expr = Column(Text, comment='因子表达式(可复现)')
    ic = Column(Float, comment='信息系数(与未来收益Spearman相关)')
    rank_ic = Column(Float, comment='RankIC')
    icir = Column(Float, comment='ICIR(IC稳定性代理)')
    long_short_return = Column(Float, comment='多空组合年化收益(%)')
    sharpe = Column(Float, comment='因子多空夏普')
    turnover = Column(Float, comment='因子换手率(%)')
    source = Column(String(16), comment='base/evolved')
    is_active = Column(Integer, default=0, comment='是否当前保留的最优因子(1=是)')
    created_at = Column(DateTime, default=datetime.now)
    __table_args__ = (Index('ix_fmr_gen_active', 'generation', 'is_active'),)

    def to_dict(self) -> Dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class AnalysisHistory(Base):
    """
    分析结果历史记录模型

    保存每次分析结果，支持按 query_id/股票代码检索
    """
    __tablename__ = 'analysis_history'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关联查询链路
    query_id = Column(String(64), index=True)

    # 股票信息
    code = Column(String(10), nullable=False, index=True)
    name = Column(String(50))
    report_type = Column(String(16), index=True)

    # 核心结论
    sentiment_score = Column(Integer)
    operation_advice = Column(String(20))
    trend_prediction = Column(String(50))
    analysis_summary = Column(Text)

    # 详细数据
    raw_result = Column(Text)
    news_content = Column(Text)
    context_snapshot = Column(Text)

    # 狙击点位（用于回测）
    ideal_buy = Column(Float)
    secondary_buy = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)

    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_analysis_code_time', 'code', 'created_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'query_id': self.query_id,
            'code': self.code,
            'name': self.name,
            'report_type': self.report_type,
            'sentiment_score': self.sentiment_score,
            'operation_advice': self.operation_advice,
            'trend_prediction': self.trend_prediction,
            'analysis_summary': self.analysis_summary,
            'raw_result': self.raw_result,
            'news_content': self.news_content,
            'context_snapshot': self.context_snapshot,
            'ideal_buy': self.ideal_buy,
            'secondary_buy': self.secondary_buy,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BacktestResult(Base):
    """单条分析记录的回测结果。"""

    __tablename__ = 'backtest_results'

    id = Column(Integer, primary_key=True, autoincrement=True)

    analysis_history_id = Column(
        Integer,
        ForeignKey('analysis_history.id'),
        nullable=False,
        index=True,
    )

    # 冗余字段，便于按股票筛选
    code = Column(String(10), nullable=False, index=True)
    analysis_date = Column(Date, index=True)

    # 回测参数
    eval_window_days = Column(Integer, nullable=False, default=10)
    engine_version = Column(String(16), nullable=False, default='v1')

    # 状态
    eval_status = Column(String(16), nullable=False, default='pending')
    evaluated_at = Column(DateTime, default=datetime.now, index=True)

    # 建议快照（避免未来分析字段变化导致回测不可解释）
    operation_advice = Column(String(20))
    position_recommendation = Column(String(8))  # long/cash

    # 价格与收益
    start_price = Column(Float)
    end_close = Column(Float)
    max_high = Column(Float)
    min_low = Column(Float)
    stock_return_pct = Column(Float)

    # 方向与结果
    direction_expected = Column(String(16))  # up/down/flat/not_down
    direction_correct = Column(Boolean, nullable=True)
    outcome = Column(String(16))  # win/loss/neutral

    # 目标价命中（仅 long 且配置了止盈/止损时有意义）
    stop_loss = Column(Float)
    take_profit = Column(Float)
    hit_stop_loss = Column(Boolean)
    hit_take_profit = Column(Boolean)
    first_hit = Column(String(16))  # take_profit/stop_loss/ambiguous/neither/not_applicable
    first_hit_date = Column(Date)
    first_hit_trading_days = Column(Integer)

    # 模拟执行（long-only）
    simulated_entry_price = Column(Float)
    simulated_exit_price = Column(Float)
    simulated_exit_reason = Column(String(24))  # stop_loss/take_profit/window_end/cash/ambiguous_stop_loss
    simulated_return_pct = Column(Float)

    __table_args__ = (
        UniqueConstraint(
            'analysis_history_id',
            'eval_window_days',
            'engine_version',
            name='uix_backtest_analysis_window_version',
        ),
        Index('ix_backtest_code_date', 'code', 'analysis_date'),
    )


class BacktestSummary(Base):
    """回测汇总指标（按股票或全局）。"""

    __tablename__ = 'backtest_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)

    scope = Column(String(16), nullable=False, index=True)  # overall/stock
    code = Column(String(16), index=True)

    eval_window_days = Column(Integer, nullable=False, default=10)
    engine_version = Column(String(16), nullable=False, default='v1')
    computed_at = Column(DateTime, default=datetime.now, index=True)

    # 计数
    total_evaluations = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    insufficient_count = Column(Integer, default=0)
    long_count = Column(Integer, default=0)
    cash_count = Column(Integer, default=0)

    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)

    # 准确率/胜率
    direction_accuracy_pct = Column(Float)
    win_rate_pct = Column(Float)
    neutral_rate_pct = Column(Float)

    # 收益
    avg_stock_return_pct = Column(Float)
    avg_simulated_return_pct = Column(Float)

    # 目标价触发统计（仅 long 且配置止盈/止损时统计）
    stop_loss_trigger_rate = Column(Float)
    take_profit_trigger_rate = Column(Float)
    ambiguous_rate = Column(Float)
    avg_days_to_first_hit = Column(Float)

    # 诊断字段（JSON 字符串）
    advice_breakdown_json = Column(Text)
    diagnostics_json = Column(Text)

    __table_args__ = (
        UniqueConstraint(
            'scope',
            'code',
            'eval_window_days',
            'engine_version',
            name='uix_backtest_summary_scope_code_window_version',
        ),
    )


class PortfolioAccount(Base):
    """Portfolio account metadata."""

    __tablename__ = 'portfolio_accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(String(64), index=True)
    name = Column(String(64), nullable=False)
    broker = Column(String(64))
    market = Column(String(8), nullable=False, default='cn', index=True)  # cn/hk/us
    base_currency = Column(String(8), nullable=False, default='CNY')
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('ix_portfolio_account_owner_active', 'owner_id', 'is_active'),
    )


class PortfolioTrade(Base):
    """Executed trade events used as the source of truth for replay."""

    __tablename__ = 'portfolio_trades'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    trade_uid = Column(String(128))
    symbol = Column(String(16), nullable=False, index=True)
    market = Column(String(8), nullable=False, default='cn')
    currency = Column(String(8), nullable=False, default='CNY')
    trade_date = Column(Date, nullable=False, index=True)
    side = Column(String(8), nullable=False)  # buy/sell
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fee = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    note = Column(String(255))
    dedup_hash = Column(String(64), index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint('account_id', 'trade_uid', name='uix_portfolio_trade_uid'),
        UniqueConstraint('account_id', 'dedup_hash', name='uix_portfolio_trade_dedup_hash'),
        Index('ix_portfolio_trade_account_date', 'account_id', 'trade_date'),
    )


class PortfolioCashLedger(Base):
    """Cash in/out events."""

    __tablename__ = 'portfolio_cash_ledger'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    event_date = Column(Date, nullable=False, index=True)
    direction = Column(String(8), nullable=False)  # in/out
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default='CNY')
    note = Column(String(255))
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_portfolio_cash_account_date', 'account_id', 'event_date'),
    )


class PortfolioCorporateAction(Base):
    """Corporate actions that impact cash or share quantity."""

    __tablename__ = 'portfolio_corporate_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    market = Column(String(8), nullable=False, default='cn')
    currency = Column(String(8), nullable=False, default='CNY')
    effective_date = Column(Date, nullable=False, index=True)
    action_type = Column(String(24), nullable=False)  # cash_dividend/split_adjustment
    cash_dividend_per_share = Column(Float)
    split_ratio = Column(Float)
    note = Column(String(255))
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_portfolio_ca_account_date', 'account_id', 'effective_date'),
    )


class PortfolioPosition(Base):
    """Latest replayed position snapshot for each symbol in one account."""

    __tablename__ = 'portfolio_positions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    cost_method = Column(String(8), nullable=False, default='fifo')
    symbol = Column(String(16), nullable=False, index=True)
    market = Column(String(8), nullable=False, default='cn')
    currency = Column(String(8), nullable=False, default='CNY')
    quantity = Column(Float, nullable=False, default=0.0)
    avg_cost = Column(Float, nullable=False, default=0.0)
    total_cost = Column(Float, nullable=False, default=0.0)
    last_price = Column(Float, nullable=False, default=0.0)
    market_value_base = Column(Float, nullable=False, default=0.0)
    unrealized_pnl_base = Column(Float, nullable=False, default=0.0)
    valuation_currency = Column(String(8), nullable=False, default='CNY')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint(
            'account_id',
            'symbol',
            'market',
            'currency',
            'cost_method',
            name='uix_portfolio_position_account_symbol_market_currency',
        ),
    )


class PortfolioPositionLot(Base):
    """Lot-level remaining quantities used by FIFO replay."""

    __tablename__ = 'portfolio_position_lots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    cost_method = Column(String(8), nullable=False, default='fifo')
    symbol = Column(String(16), nullable=False, index=True)
    market = Column(String(8), nullable=False, default='cn')
    currency = Column(String(8), nullable=False, default='CNY')
    open_date = Column(Date, nullable=False, index=True)
    remaining_quantity = Column(Float, nullable=False, default=0.0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    source_trade_id = Column(Integer, ForeignKey('portfolio_trades.id'))
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index('ix_portfolio_lot_account_symbol', 'account_id', 'symbol'),
    )


class PortfolioDailySnapshot(Base):
    """Daily account snapshot generated by read-time replay."""

    __tablename__ = 'portfolio_daily_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    cost_method = Column(String(8), nullable=False, default='fifo')  # fifo/avg
    base_currency = Column(String(8), nullable=False, default='CNY')
    total_cash = Column(Float, nullable=False, default=0.0)
    total_market_value = Column(Float, nullable=False, default=0.0)
    total_equity = Column(Float, nullable=False, default=0.0)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    fee_total = Column(Float, nullable=False, default=0.0)
    tax_total = Column(Float, nullable=False, default=0.0)
    fx_stale = Column(Boolean, nullable=False, default=False)
    payload = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint(
            'account_id',
            'snapshot_date',
            'cost_method',
            name='uix_portfolio_snapshot_account_date_method',
        ),
    )


class PortfolioFxRate(Base):
    """Cached FX rates used for cross-currency portfolio conversion."""

    __tablename__ = 'portfolio_fx_rates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_currency = Column(String(8), nullable=False, index=True)
    to_currency = Column(String(8), nullable=False, index=True)
    rate_date = Column(Date, nullable=False, index=True)
    rate = Column(Float, nullable=False)
    source = Column(String(32), nullable=False, default='manual')
    is_stale = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint(
            'from_currency',
            'to_currency',
            'rate_date',
            name='uix_portfolio_fx_pair_date',
        ),
    )


class ConversationMessage(Base):
    """
    Agent 对话历史记录表
    """
    __tablename__ = 'conversation_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), index=True, nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, index=True)


class ConversationSummary(Base):
    """Rolling summary for visible Agent chat history."""

    __tablename__ = 'conversation_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, unique=True, index=True)
    summary = Column(Text, nullable=False)
    covered_message_id = Column(Integer, nullable=False, default=0)
    source_message_count = Column(Integer, nullable=False, default=0)
    estimated_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)


class AgentProviderTurn(Base):
    """Provider protocol trace required for thinking/tool-call roundtrip."""

    __tablename__ = 'agent_provider_turns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(64), nullable=False, index=True)
    model = Column(String(160), nullable=False, index=True)
    anchor_user_message_id = Column(Integer, nullable=False, index=True)
    anchor_assistant_message_id = Column(Integer, nullable=False, index=True)
    messages_json = Column(Text, nullable=False)
    contains_reasoning = Column(Boolean, nullable=False, default=False)
    contains_tool_calls = Column(Boolean, nullable=False, default=False)
    contains_thinking_blocks = Column(Boolean, nullable=False, default=False)
    must_roundtrip = Column(Boolean, nullable=False, default=False, index=True)
    estimated_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_agent_provider_turn_bucket', 'session_id', 'provider', 'model', 'must_roundtrip'),
    )


class LLMUsage(Base):
    """One row per litellm.completion() call — token-usage audit log."""

    __tablename__ = 'llm_usage'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 'analysis' | 'agent' | 'market_review'
    call_type = Column(String(32), nullable=False, index=True)
    model = Column(String(128), nullable=False)
    stock_code = Column(String(16), nullable=True)
    provider = Column(String(64), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)

    # Sanitized provider usage snapshot; raw prompts, messages, headers, and
    # tokenizer free-text fields are intentionally not persisted here.
    provider_usage_json = Column(Text, nullable=True)
    provider_usage_schema_name = Column(String(64), nullable=True)
    provider_usage_schema_version = Column(String(32), nullable=True)
    provider_usage_observed_at = Column(String(32), nullable=True)

    # Normalized telemetry values are derived from provider usage and may stay
    # NULL when the provider payload is absent or explicitly invalid.
    normalized_prompt_tokens = Column(Integer, nullable=True)
    normalized_completion_tokens = Column(Integer, nullable=True)
    normalized_total_tokens = Column(Integer, nullable=True)
    normalized_cache_read_tokens = Column(Integer, nullable=True)
    normalized_cache_write_tokens = Column(Integer, nullable=True)
    normalized_cache_miss_tokens = Column(Integer, nullable=True)
    normalized_uncached_input_tokens = Column(Integer, nullable=True)
    normalized_cache_eligible_input_tokens = Column(Integer, nullable=True)
    normalized_cache_hit_ratio = Column(Float, nullable=True)
    normalized_cache_write_ratio = Column(Float, nullable=True)
    cache_capability = Column(String(32), nullable=True)
    cache_eligibility = Column(String(32), nullable=True)
    cache_observation = Column(String(32), nullable=True)
    estimated_prefix_tokens = Column(Integer, nullable=True)
    provider_reported_prompt_tokens = Column(Integer, nullable=True)
    provider_reported_cached_tokens = Column(Integer, nullable=True)
    provider_min_cache_tokens = Column(Integer, nullable=True)
    eligibility_confidence = Column(String(32), nullable=True)

    # Kept nullable for schema compatibility; new writes do not store provider
    # or proxy tokenizer free-text values.
    tokenizer_name = Column(String(128), nullable=True)
    tokenizer_version = Column(String(64), nullable=True)

    # HMAC fingerprints let deployments compare message shapes without storing
    # raw prompt/message content.
    messages_hmac = Column(String(64), nullable=True)
    system_message_hmac = Column(String(64), nullable=True)
    user_message_hmac = Column(String(64), nullable=True)
    hmac_key_version = Column(String(64), nullable=True)
    hmac_domain = Column(String(32), nullable=True)
    hash_scope = Column(String(32), nullable=True)

    # P0.5a internal legacy message stability audit. These diagnostics are
    # stored locally only and are not returned by public usage APIs.
    language = Column(String(16), nullable=True)
    market_group = Column(String(16), nullable=True)
    analysis_mode = Column(String(64), nullable=True)
    legacy_prompt_mode = Column(String(32), nullable=True)
    skill_config_hmac = Column(String(64), nullable=True)
    transport = Column(String(64), nullable=True)
    message_count = Column(Integer, nullable=True)
    estimated_total_prompt_tokens = Column(Integer, nullable=True)
    approx_common_prefix_chars = Column(Integer, nullable=True)
    approx_common_prefix_tokens = Column(Integer, nullable=True)
    known_dynamic_marker_positions = Column(Text, nullable=True)
    called_at = Column(DateTime, default=datetime.now, index=True)


_LLM_USAGE_TELEMETRY_COLUMN_SQL: Dict[str, str] = {
    "provider_usage_json": "TEXT",
    "provider": "VARCHAR(64)",
    "provider_usage_schema_name": "VARCHAR(64)",
    "provider_usage_schema_version": "VARCHAR(32)",
    "provider_usage_observed_at": "VARCHAR(32)",
    "normalized_prompt_tokens": "INTEGER",
    "normalized_completion_tokens": "INTEGER",
    "normalized_total_tokens": "INTEGER",
    "normalized_cache_read_tokens": "INTEGER",
    "normalized_cache_write_tokens": "INTEGER",
    "normalized_cache_miss_tokens": "INTEGER",
    "normalized_uncached_input_tokens": "INTEGER",
    "normalized_cache_eligible_input_tokens": "INTEGER",
    "normalized_cache_hit_ratio": "FLOAT",
    "normalized_cache_write_ratio": "FLOAT",
    "cache_capability": "VARCHAR(32)",
    "cache_eligibility": "VARCHAR(32)",
    "cache_observation": "VARCHAR(32)",
    "estimated_prefix_tokens": "INTEGER",
    "provider_reported_prompt_tokens": "INTEGER",
    "provider_reported_cached_tokens": "INTEGER",
    "provider_min_cache_tokens": "INTEGER",
    "eligibility_confidence": "VARCHAR(32)",
    "tokenizer_name": "VARCHAR(128)",
    "tokenizer_version": "VARCHAR(64)",
    "messages_hmac": "VARCHAR(64)",
    "system_message_hmac": "VARCHAR(64)",
    "user_message_hmac": "VARCHAR(64)",
    "hmac_key_version": "VARCHAR(64)",
    "hmac_domain": "VARCHAR(32)",
    "hash_scope": "VARCHAR(32)",
    "language": "VARCHAR(16)",
    "market_group": "VARCHAR(16)",
    "analysis_mode": "VARCHAR(64)",
    "legacy_prompt_mode": "VARCHAR(32)",
    "skill_config_hmac": "VARCHAR(64)",
    "transport": "VARCHAR(64)",
    "message_count": "INTEGER",
    "estimated_total_prompt_tokens": "INTEGER",
    "approx_common_prefix_chars": "INTEGER",
    "approx_common_prefix_tokens": "INTEGER",
    "known_dynamic_marker_positions": "TEXT",
}
_LLM_USAGE_INTEGER_TELEMETRY_COLUMNS = {
    column
    for column, column_type in _LLM_USAGE_TELEMETRY_COLUMN_SQL.items()
    if column_type == "INTEGER"
}
_LLM_USAGE_DROPPED_FREE_TEXT_COLUMNS = {"tokenizer_name", "tokenizer_version"}
_LLM_PROMPT_CACHE_TELEMETRY_DISABLED_ATTR = "prompt_cache_telemetry_disabled"
_LLM_PROMPT_CACHE_TELEMETRY_COLUMNS = {
    "provider_usage_json",
    "provider_usage_schema_name",
    "provider_usage_schema_version",
    "provider_usage_observed_at",
    "normalized_cache_read_tokens",
    "normalized_cache_write_tokens",
    "normalized_cache_miss_tokens",
    "normalized_uncached_input_tokens",
    "normalized_cache_eligible_input_tokens",
    "normalized_cache_hit_ratio",
    "normalized_cache_write_ratio",
    "cache_capability",
    "cache_eligibility",
    "cache_observation",
    "estimated_prefix_tokens",
    "provider_reported_cached_tokens",
    "provider_min_cache_tokens",
    "eligibility_confidence",
}


class AlertRuleRecord(Base):
    """Persisted alert rule managed through the Alert API."""

    __tablename__ = 'alert_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    target_scope = Column(String(32), nullable=False, default='single_symbol', index=True)
    target = Column(String(64), nullable=False, index=True)
    alert_type = Column(String(32), nullable=False, index=True)
    parameters = Column(Text, nullable=False, default='{}')
    severity = Column(String(16), nullable=False, default='warning', index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    source = Column(String(16), nullable=False, default='api', index=True)
    cooldown_policy = Column(Text)
    notification_policy = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index('ix_alert_rule_type_target', 'alert_type', 'target'),
    )


class AlertTriggerRecord(Base):
    """Alert trigger history row.

    P1 exposes read APIs and table shape; runtime writer integration lands in
    later phases.
    """

    __tablename__ = 'alert_triggers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, index=True)
    target = Column(String(64), nullable=False, index=True)
    observed_value = Column(Float)
    threshold = Column(Float)
    reason = Column(Text)
    data_source = Column(String(64))
    data_timestamp = Column(DateTime, index=True)
    triggered_at = Column(DateTime, default=datetime.now, index=True)
    status = Column(String(16), nullable=False, default='triggered', index=True)
    diagnostics = Column(Text)

    __table_args__ = (
        Index('ix_alert_trigger_rule_time', 'rule_id', 'triggered_at'),
    )


class AlertNotificationRecord(Base):
    """Notification attempt row for alert triggers.

    P1 exposes read APIs and table shape; runtime writer integration lands in
    later phases.
    """

    __tablename__ = 'alert_notifications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger_id = Column(Integer, index=True)
    channel = Column(String(32), nullable=False, index=True)
    attempt = Column(Integer, nullable=False, default=1)
    success = Column(Boolean, nullable=False, default=False, index=True)
    error_code = Column(String(64))
    retryable = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Integer)
    diagnostics = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_alert_notification_trigger_channel', 'trigger_id', 'channel'),
    )


class AlertCooldownRecord(Base):
    """Persisted alert cooldown state for DB-managed alert rules."""

    __tablename__ = 'alert_cooldowns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, index=True)
    # Reserved for future non-DB/expanded-scope rules; P4 queries by rule_id.
    rule_key = Column(String(255), index=True)
    target = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default='warning', index=True)
    last_triggered_at = Column(DateTime, index=True)
    cooldown_until = Column(DateTime, index=True)
    reason = Column(Text)
    state = Column(String(16), nullable=False, default='active', index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint('rule_id', 'target', 'severity', name='uix_alert_cooldown_rule_target_severity'),
    )


class DecisionSignalRecord(Base):
    """Persisted AI decision signal asset for Issue #1390 P1."""

    __tablename__ = 'decision_signals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64))
    market = Column(String(8), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, index=True)
    source_agent = Column(String(64))
    source_report_id = Column(Integer, index=True)
    trace_id = Column(String(64), index=True)
    decision_profile = Column(String(16), index=True)
    market_phase = Column(String(24), index=True)
    trigger_source = Column(String(64), nullable=False, index=True)
    action = Column(String(16), nullable=False, index=True)
    action_label = Column(String(32))
    confidence = Column(Float)
    score = Column(Integer)
    horizon = Column(String(16), index=True)
    entry_low = Column(Float)
    entry_high = Column(Float)
    stop_loss = Column(Float)
    target_price = Column(Float)
    invalidation = Column(Text)
    watch_conditions = Column(Text)
    reason = Column(Text)
    risk_summary = Column(Text)
    catalyst_summary = Column(Text)
    evidence_json = Column(Text)
    data_quality_summary_json = Column(Text)
    plan_quality = Column(String(16), nullable=False, default='unknown', index=True)
    status = Column(String(16), nullable=False, default='active', index=True)
    expires_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)
    metadata_json = Column(Text)

    __table_args__ = (
        Index('ix_decision_signal_stock_status_time', 'stock_code', 'status', 'created_at'),
        Index('ix_decision_signal_market_status_time', 'market', 'status', 'created_at'),
        Index(
            'ix_decision_signal_report_type_market_stock_action_horizon_phase',
            'source_report_id',
            'source_type',
            'market',
            'stock_code',
            'action',
            'horizon',
            'market_phase',
        ),
        Index(
            'ix_decision_signal_trace_type_market_stock_action_horizon_phase',
            'trace_id',
            'source_type',
            'market',
            'stock_code',
            'action',
            'horizon',
            'market_phase',
        ),
        Index(
            'ix_decision_signal_report_type_market_stock_profile_action_horizon_phase',
            'source_report_id',
            'source_type',
            'market',
            'stock_code',
            'decision_profile',
            'action',
            'horizon',
            'market_phase',
        ),
        Index(
            'ix_decision_signal_trace_type_market_stock_profile_action_horizon_phase',
            'trace_id',
            'source_type',
            'market',
            'stock_code',
            'decision_profile',
            'action',
            'horizon',
            'market_phase',
        ),
        Index(
            'ix_decision_signal_market_stock_profile_created',
            'market',
            'stock_code',
            'decision_profile',
            'created_at',
        ),
    )


class DecisionSignalOutcomeRecord(Base):
    """Signal-level forward outcome for Issue #1390 P5."""

    __tablename__ = 'decision_signal_outcomes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, nullable=False, index=True)
    horizon = Column(String(16), nullable=False, index=True)
    engine_version = Column(String(32), nullable=False, index=True)
    eval_status = Column(String(24), nullable=False, default='unable', index=True)
    outcome = Column(String(16), index=True)
    direction_expected = Column(String(16), index=True)
    direction_correct = Column(Boolean)
    unable_reason = Column(String(64), index=True)
    anchor_date = Column(Date, index=True)
    eval_window_days = Column(Integer)
    start_price = Column(Float)
    end_close = Column(Float)
    max_high = Column(Float)
    min_low = Column(Float)
    stock_return_pct = Column(Float)

    action = Column(String(16), index=True)
    market = Column(String(8), index=True)
    market_phase = Column(String(24), index=True)
    source_type = Column(String(32), index=True)
    source_agent = Column(String(64), index=True)
    plan_quality = Column(String(16), index=True)
    data_quality_level = Column(String(24), index=True)
    holding_state = Column(String(16), nullable=False, default='unknown', index=True)

    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)

    __table_args__ = (
        UniqueConstraint('signal_id', 'horizon', 'engine_version', name='uix_decision_signal_outcome_key'),
        Index('ix_decision_signal_outcome_stats_action', 'engine_version', 'action', 'horizon'),
        Index('ix_decision_signal_outcome_stats_market', 'engine_version', 'market', 'horizon'),
    )


class DecisionSignalFeedbackRecord(Base):
    """Latest user feedback for a decision signal."""

    __tablename__ = 'decision_signal_feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, nullable=False, unique=True, index=True)
    feedback_value = Column(String(16), nullable=False, index=True)
    reason_code = Column(String(64), index=True)
    note = Column(Text)
    source = Column(String(16), nullable=False, default='api', index=True)
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)


class SkillOpinionSampleRecord(Base):
    """Immutable, low-sensitivity skill opinion sample for Issue #1904 P2 PR1."""

    __tablename__ = 'skill_opinion_samples'

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_history_id = Column(
        Integer,
        ForeignKey('analysis_history.id'),
        nullable=False,
        index=True,
    )
    stock_code = Column(String(16), nullable=False, index=True)
    skill_id = Column(String(128), nullable=False, index=True)
    skill_version = Column(String(64), index=True)
    signal = Column(String(16), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    horizon = Column(String(16), index=True)
    data_quality_level = Column(String(24), index=True)
    opinion_created_at = Column(DateTime, index=True)
    sample_schema_version = Column(String(32), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_naive_now, index=True)

    __table_args__ = (
        UniqueConstraint(
            'analysis_history_id',
            'skill_id',
            'sample_schema_version',
            name='uix_skill_opinion_sample_key',
        ),
        Index(
            'ix_skill_opinion_sample_skill_horizon_created',
            'skill_id',
            'horizon',
            'created_at',
        ),
        Index(
            'ix_skill_opinion_sample_stock_created',
            'stock_code',
            'created_at',
        ),
    )


class _DatabaseManagerMeta(type):
    """Serialize DatabaseManager construction across __new__ and __init__."""

    def __call__(cls, *args, **kwargs):
        with cls._init_lock:
            return super().__call__(*args, **kwargs)


class DatabaseManager(metaclass=_DatabaseManagerMeta):
    """
    数据库管理器 - 单例模式
    
    职责：
    1. 管理数据库连接池
    2. 提供 Session 上下文管理
    3. 封装数据存取操作
    """
    
    _instance: Optional['DatabaseManager'] = None
    _init_lock = threading.RLock()
    _initialized: bool = False
    
    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_url: Optional[str] = None):
        """
        初始化数据库管理器
        
        Args:
            db_url: 数据库连接 URL（可选，默认从配置读取）
        """
        if getattr(self, '_initialized', False):
            return

        created_engine = None

        try:
            config = get_config()
            if db_url is None:
                db_url = config.get_db_url()

            self._db_url = db_url
            self._sqlite_wal_enabled = config.sqlite_wal_enabled
            self._sqlite_busy_timeout_ms = config.sqlite_busy_timeout_ms
            self._sqlite_write_retry_max = config.sqlite_write_retry_max
            self._sqlite_write_retry_base_delay = config.sqlite_write_retry_base_delay

            engine_kwargs = {
                "echo": False,
                "pool_pre_ping": True,
            }
            if str(db_url).startswith("sqlite:") and self._sqlite_busy_timeout_ms > 0:
                engine_kwargs["connect_args"] = {
                    "timeout": self._sqlite_busy_timeout_ms / 1000,
                }

            # 创建数据库引擎
            created_engine = create_engine(
                db_url,
                **engine_kwargs,
            )
            self._engine = created_engine
            self._is_sqlite_engine = self._engine.url.get_backend_name() == 'sqlite'
            self._sqlite_file_db = self._is_sqlite_engine and self._is_file_sqlite_database()
            self._install_sqlite_pragma_handler()

            # 创建 Session 工厂
            self._SessionLocal = sessionmaker(
                bind=self._engine,
                autocommit=False,
                autoflush=False,
            )

            # 创建所有表
            Base.metadata.create_all(self._engine)
            self._ensure_llm_usage_telemetry_columns()
            self._ensure_decision_signal_profile_schema()
            self._ensure_intelligence_item_scope_values()
            self._ensure_schema_migration_record()
            self._ensure_intelligence_items_unique_index()

            self._initialized = True
            logger.info(f"数据库初始化完成: {db_url}")

            # 注册退出钩子，确保程序退出时关闭数据库连接
            atexit.register(DatabaseManager._cleanup_engine, self._engine)
        except Exception:
            self._initialized = False
            try:
                if created_engine is not None:
                    created_engine.dispose()
            except Exception as cleanup_exc:
                logger.warning("数据库初始化失败后的引擎清理也失败: %s", cleanup_exc)
            self._engine = None
            self._SessionLocal = None
            self.__class__._instance = None
            raise

    def _ensure_schema_migration_record(self) -> None:
        session = self._SessionLocal()
        values = {
            "version": CURRENT_SCHEMA_VERSION,
            "description": "Baseline schema created through SQLAlchemy metadata.create_all",
        }
        try:
            if self._is_sqlite_engine:
                statement = sqlite_insert(DatabaseSchemaMigration).values(**values)
                statement = statement.on_conflict_do_nothing(index_elements=["version"])
                session.execute(statement)
            else:
                session.execute(DatabaseSchemaMigration.__table__.insert().values(**values))
            session.commit()
        except IntegrityError:
            session.rollback()
            with self._SessionLocal() as verify_session:
                existing = verify_session.get(DatabaseSchemaMigration, CURRENT_SCHEMA_VERSION)
            if existing is None:
                raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _ensure_decision_signal_profile_schema(self) -> None:
        """Add and backfill nullable decision_profile for existing SQLite DBs."""

        if not self._is_sqlite_engine:
            return
        inspector = inspect(self._engine)
        if not inspector.has_table(DecisionSignalRecord.__tablename__):
            return

        try:
            existing = {
                column["name"]
                for column in inspector.get_columns(DecisionSignalRecord.__tablename__)
            }
        except Exception as exc:
            logger.error(
                "[DecisionSignal] failed to inspect decision_profile column; "
                "profile migration cannot continue safely: %s",
                exc,
            )
            raise

        if "decision_profile" not in existing:
            try:
                with self._engine.begin() as connection:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {DecisionSignalRecord.__tablename__} "
                        "ADD COLUMN decision_profile VARCHAR(16)"
                    )
            except OperationalError as exc:
                if not self._is_sqlite_duplicate_column_error(exc, "decision_profile"):
                    raise

        self._ensure_decision_signal_profile_indexes()
        self._backfill_decision_signal_profile_from_metadata()

    def _ensure_decision_signal_profile_indexes(self) -> None:
        """Create profile-aware indexes without dropping legacy indexes."""

        expected_indexes = {
            "ix_decision_signals_decision_profile": ["decision_profile"],
            "ix_decision_signal_market_stock_profile_created": [
                "market", "stock_code", "decision_profile", "created_at",
            ],
            "ix_decision_signal_report_type_market_stock_profile_action_horizon_phase": [
                "source_report_id", "source_type", "market", "stock_code",
                "decision_profile", "action", "horizon", "market_phase",
            ],
            "ix_decision_signal_trace_type_market_stock_profile_action_horizon_phase": [
                "trace_id", "source_type", "market", "stock_code",
                "decision_profile", "action", "horizon", "market_phase",
            ],
        }
        with self._engine.begin() as connection:
            for index_name, columns in expected_indexes.items():
                connection.exec_driver_sql(
                    f"CREATE INDEX IF NOT EXISTS {index_name} "
                    f"ON decision_signals ({', '.join(columns)})"
                )

        actual_indexes = {
            index["name"]: index["column_names"]
            for index in inspect(self._engine).get_indexes(
                DecisionSignalRecord.__tablename__
            )
        }
        for index_name, expected_columns in expected_indexes.items():
            if actual_indexes.get(index_name) != expected_columns:
                raise RuntimeError(
                    "decision_profile index verification failed: "
                    f"index={index_name} expected={expected_columns} "
                    f"actual={actual_indexes.get(index_name)}"
                )

    def _backfill_decision_signal_profile_from_metadata(self) -> None:
        stats = {
            "candidate_count": 0,
            "backfilled_count": 0,
            "guard_skipped_count": 0,
            "missing_metadata_count": 0,
            "missing_profile_count": 0,
            "invalid_json_count": 0,
            "non_object_count": 0,
            "invalid_profile_count": 0,
            "skipped_existing_profile_count": 0,
        }
        with self._engine.begin() as connection:
            stats["skipped_existing_profile_count"] = connection.execute(
                text(
                    "SELECT COUNT(*) FROM decision_signals "
                    "WHERE decision_profile IS NOT NULL"
                )
            ).scalar_one()
            candidate_rows = [
                (row["id"], row["metadata_json"])
                for row in connection.execute(
                    text(
                        "SELECT id, metadata_json FROM decision_signals "
                        "WHERE decision_profile IS NULL ORDER BY id"
                    )
                ).mappings()
            ]
            stats["candidate_count"] = len(candidate_rows)

            for signal_id, metadata_json in candidate_rows:
                if metadata_json is None:
                    stats["missing_metadata_count"] += 1
                    continue
                try:
                    metadata = json.loads(metadata_json)
                except (TypeError, ValueError, RecursionError):
                    stats["invalid_json_count"] += 1
                    continue
                if not isinstance(metadata, dict):
                    stats["non_object_count"] += 1
                    continue

                raw_profile = metadata.get("decision_profile")
                if raw_profile is None or (
                    isinstance(raw_profile, str) and not raw_profile.strip()
                ):
                    stats["missing_profile_count"] += 1
                    continue
                profile = extract_legacy_decision_profile(metadata)
                if profile is None:
                    stats["invalid_profile_count"] += 1
                    continue

                result = connection.execute(
                    text(
                        "UPDATE decision_signals "
                        "SET decision_profile = :decision_profile "
                        "WHERE id = :signal_id AND decision_profile IS NULL"
                    ),
                    {"decision_profile": profile, "signal_id": signal_id},
                )
                if result.rowcount == 1:
                    stats["backfilled_count"] += 1
                elif result.rowcount == 0:
                    stats["guard_skipped_count"] += 1
                else:
                    raise RuntimeError(
                        "decision_profile backfill updated an unexpected number "
                        f"of rows for signal_id={signal_id}: {result.rowcount}"
                    )

            classified_count = sum(
                stats[key]
                for key in (
                    "backfilled_count",
                    "guard_skipped_count",
                    "missing_metadata_count",
                    "missing_profile_count",
                    "invalid_json_count",
                    "non_object_count",
                    "invalid_profile_count",
                )
            )
            if classified_count != stats["candidate_count"]:
                raise RuntimeError(
                    "decision_profile migration stats did not classify every "
                    f"candidate: candidates={stats['candidate_count']} "
                    f"classified={classified_count}"
                )
        logger.info(
            "[DecisionSignal] decision_profile migration stats: "
            "candidate_count=%s backfilled_count=%s guard_skipped_count=%s "
            "missing_metadata_count=%s missing_profile_count=%s "
            "invalid_json_count=%s non_object_count=%s invalid_profile_count=%s "
            "skipped_existing_profile_count=%s",
            stats["candidate_count"],
            stats["backfilled_count"],
            stats["guard_skipped_count"],
            stats["missing_metadata_count"],
            stats["missing_profile_count"],
            stats["invalid_json_count"],
            stats["non_object_count"],
            stats["invalid_profile_count"],
            stats["skipped_existing_profile_count"],
        )

    def _ensure_intelligence_items_unique_index(self) -> None:
        if not self._is_sqlite_engine:
            return

        if not inspect(self._engine).has_table("intelligence_items"):
            return

        try:
            unique_indexes = self._list_sqlite_unique_indexes("intelligence_items")
        except Exception as exc:
            logger.warning(
                "[Intelligence items] failed to inspect unique indexes; "
                "skip migration/repair: %s",
                exc,
            )
            return

        target_columns = ("source_id", "url", "scope_type", "scope_value", "market")
        has_target_index = any(tuple(cols) == target_columns for cols in unique_indexes)
        has_legacy_url_unique = any(tuple(cols) == ("url",) for cols in unique_indexes)

        if has_target_index:
            return
        if unique_indexes and not has_legacy_url_unique:
            # Table has other unique index shapes; avoid aggressive changes and add
            # the expected scoped uniqueness directly.
            self._ensure_intelligence_items_scoped_unique_index_once()
            return

        self._rebuild_intelligence_items_table()

    def _rebuild_intelligence_items_table(self) -> None:
        temporary_table = f"intelligence_items_recreate_tmp_{int(time.time() * 1_000_000_000)}"
        columns = [column.name for column in IntelligenceItem.__table__.columns]
        select_clause = ", ".join(f'"{column}"' for column in columns)
        scoped_index_columns = ", ".join(["source_id", "url", "scope_type", "scope_value", "market"])
        scoped_index_name = "uix_intel_item_scope"

        tmp_metadata = MetaData()
        tmp_table = Table(
            temporary_table,
            tmp_metadata,
            *(column.copy() for column in IntelligenceItem.__table__.columns),
        )
        logger.info("Rebuilding intelligence_items table to align composite uniqueness constraints.")
        with self._engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "{temporary_table}"'))
            tmp_table.create(connection)
            connection.execute(
                text(
                    f"INSERT INTO \"{temporary_table}\" ({select_clause}) "
                    f"SELECT {select_clause} FROM intelligence_items"
                )
            )
            connection.execute(text('DROP TABLE "intelligence_items"'))
            connection.execute(
                text(f'ALTER TABLE "{temporary_table}" RENAME TO intelligence_items')
            )
            connection.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {scoped_index_name} ON "
                    f"intelligence_items ({scoped_index_columns})"
                )
            )

    def _ensure_intelligence_items_scoped_unique_index_once(self) -> None:
        target_index_name = "uix_intel_item_scope"
        with self._engine.begin() as connection:
            rows = connection.execute(
                text("PRAGMA index_list(intelligence_items)")
            ).fetchall()
            for row in rows:
                if row[1] == target_index_name:
                    return
            index_columns = ", ".join(["source_id", "url", "scope_type", "scope_value", "market"])
            connection.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {target_index_name} ON "
                    f"intelligence_items ({index_columns})"
                )
            )

    def _list_sqlite_unique_indexes(self, table_name: str):
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(f"PRAGMA index_list({table_name})")
            ).fetchall()
            unique_indexes = []
            for row in rows:
                # row: (seq, name, unique, origin, partial)
                if int(row[2]) != 1:
                    continue
                index_name = row[1]
                index_columns = []
                for index_info in connection.execute(
                    text(f"PRAGMA index_xinfo({index_name})")
                ).fetchall():
                    # index_xinfo: (seqno, cid, name, desc, coll, key, ... )
                    column_name = index_info[2]
                    if column_name is None:
                        continue
                    index_columns.append(column_name)
                unique_indexes.append(index_columns)
            return unique_indexes

    def _ensure_llm_usage_telemetry_columns(self) -> None:
        """Add nullable P0a usage telemetry columns to existing SQLite DBs."""
        if not self._is_sqlite_engine:
            return
        try:
            existing = {
                column["name"]
                for column in inspect(self._engine).get_columns(LLMUsage.__tablename__)
            }
        except Exception as exc:
            logger.warning(
                "[LLM usage] failed to inspect telemetry columns; "
                "skipping best-effort SQLite telemetry column backfill: %s",
                exc,
            )
            return

        max_retries = self._sqlite_write_retry_max
        for column, column_type in _LLM_USAGE_TELEMETRY_COLUMN_SQL.items():
            if column in existing:
                continue
            for attempt in range(max_retries + 1):
                try:
                    with self._engine.begin() as connection:
                        connection.exec_driver_sql(
                            f"ALTER TABLE {LLMUsage.__tablename__} "
                            f"ADD COLUMN {column} {column_type}"
                        )
                    existing.add(column)
                    break
                except OperationalError as exc:
                    if self._is_sqlite_duplicate_column_error(exc, column):
                        existing.add(column)
                        break
                    if self._is_sqlite_locked_error(exc) and attempt < max_retries:
                        delay = self._sqlite_write_retry_base_delay * (2 ** attempt)
                        logger.warning(
                            "[LLM usage] SQLite telemetry column backfill locked, "
                            "retrying: %s (%s/%s, %.2fs)",
                            column,
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        if delay > 0:
                            time.sleep(delay)
                        continue
                    raise

    def _ensure_intelligence_item_scope_values(self) -> None:
        """Backfill nullable intelligence item scopes so SQLite unique keys work."""
        if not self._is_sqlite_engine:
            return
        try:
            existing = {
                column["name"]
                for column in inspect(self._engine).get_columns(IntelligenceItem.__tablename__)
            }
        except Exception as exc:
            logger.warning("资讯池 scope_value 回填检查失败，已跳过: %s", exc)
            return
        if "scope_value" not in existing:
            return
        try:
            with self._engine.begin() as connection:
                connection.exec_driver_sql(
                    f"UPDATE {IntelligenceItem.__tablename__} "
                    "SET scope_value = ? "
                    "WHERE scope_value IS NULL OR scope_value = ''",
                    (INTELLIGENCE_ITEM_NULL_SCOPE_VALUE,),
                )
        except Exception as exc:
            logger.warning("资讯池 scope_value 回填失败，已跳过: %s", exc)

    @classmethod
    def get_instance(cls) -> 'DatabaseManager':
        """获取单例实例"""
        with cls._init_lock:
            if cls._instance is None:
                cls()
            return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        with cls._init_lock:
            if cls._instance is not None:
                if hasattr(cls._instance, '_engine') and cls._instance._engine is not None:
                    cls._instance._engine.dispose()
                cls._instance._initialized = False
                cls._instance = None

    @classmethod
    def _cleanup_engine(cls, engine) -> None:
        """
        清理数据库引擎（atexit 钩子）

        确保程序退出时关闭所有数据库连接，避免 ResourceWarning

        Args:
            engine: SQLAlchemy 引擎对象
        """
        try:
            if engine is not None:
                engine.dispose()
                logger.debug("数据库引擎已清理")
        except Exception as e:
            logger.warning(f"清理数据库引擎时出错: {e}")

    def _install_sqlite_pragma_handler(self) -> None:
        """为 SQLite 连接安装竞争保护参数。"""
        if not self._is_sqlite_engine:
            return

        @event.listens_for(self._engine, "connect")
        def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f"PRAGMA busy_timeout={int(self._sqlite_busy_timeout_ms)}")
                if self._sqlite_file_db and self._sqlite_wal_enabled:
                    cursor.execute("PRAGMA journal_mode=WAL")
            except Exception as exc:
                logger.warning("初始化 SQLite PRAGMA 失败: %s", exc)
            finally:
                cursor.close()

    def _is_file_sqlite_database(self) -> bool:
        database = (self._engine.url.database or "").strip()
        return bool(database) and database.lower() != ":memory:"

    def _run_write_transaction(
        self,
        operation_name: str,
        write_operation: Callable[[Session], T],
    ) -> T:
        max_retries = self._sqlite_write_retry_max if self._is_sqlite_engine else 0

        for attempt in range(max_retries + 1):
            session = self.get_session()
            try:
                if self._is_sqlite_engine:
                    # Acquire the SQLite writer lock before any reads inside
                    # `write_operation()` so pre-write existence checks and the
                    # later upsert share one consistent write window.
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                result = write_operation(session)
                session.commit()
                return result
            except OperationalError as exc:
                session.rollback()
                if (
                    self._is_sqlite_engine
                    and self._is_sqlite_locked_error(exc)
                    and attempt < max_retries
                ):
                    delay = self._sqlite_write_retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "SQLite 写入锁冲突，准备重试: %s (%s/%s, %.2fs)",
                        operation_name,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    @staticmethod
    def _is_sqlite_locked_error(exc: OperationalError) -> bool:
        err_text = str(getattr(exc, "orig", exc)).lower()
        return any(
            token in err_text
            for token in (
                "database is locked",
                "database schema is locked",
                "database table is locked",
            )
        )

    @staticmethod
    def _is_sqlite_duplicate_column_error(exc: OperationalError, column: str) -> bool:
        err_text = str(getattr(exc, "orig", exc)).lower()
        return "duplicate column name" in err_text and column.lower() in err_text

    @staticmethod
    def _normalize_daily_date(value: Any) -> Any:
        if isinstance(value, str):
            return datetime.strptime(value, '%Y-%m-%d').date()
        if isinstance(value, pd.Timestamp):
            return value.date()
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _normalize_sql_value(value: Any) -> Any:
        return None if pd.isna(value) else value
    
    def get_session(self) -> Session:
        """
        获取数据库 Session
        
        使用示例:
            with db.get_session() as session:
                # 执行查询
                session.commit()  # 如果需要
        """
        if not getattr(self, '_initialized', False) or not hasattr(self, '_SessionLocal'):
            raise RuntimeError(
                "DatabaseManager 未正确初始化。"
                "请确保通过 DatabaseManager.get_instance() 获取实例。"
            )
        session = self._SessionLocal()
        try:
            return session
        except Exception:
            session.close()
            raise

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def has_today_data(self, code: str, target_date: Optional[date] = None) -> bool:
        """
        检查是否已有指定日期的数据
        
        用于断点续传逻辑：如果已有数据则跳过网络请求
        
        Args:
            code: 股票代码
            target_date: 目标日期（默认今天）
            
        Returns:
            是否存在数据
        """
        if target_date is None:
            target_date = date.today()
        # 注意：这里的 target_date 语义是“自然日”，而不是“最新交易日”。
        # 在周末/节假日/非交易日运行时，即使数据库已有最新交易日数据，这里也会返回 False。
        # 该行为目前保留（按需求不改逻辑）。
        
        with self.get_session() as session:
            result = session.execute(
                select(StockDaily).where(
                    and_(
                        StockDaily.code == code,
                        StockDaily.date == target_date
                    )
                )
            ).scalar_one_or_none()
            
            return result is not None
    
    def get_latest_data(
        self, 
        code: str, 
        days: int = 2
    ) -> List[StockDaily]:
        """
        获取最近 N 天的数据
        
        用于计算"相比昨日"的变化
        
        Args:
            code: 股票代码
            days: 获取天数
            
        Returns:
            StockDaily 对象列表（按日期降序）
        """
        with self.get_session() as session:
            results = session.execute(
                select(StockDaily)
                .where(StockDaily.code == code)
                .order_by(desc(StockDaily.date))
                .limit(days)
            ).scalars().all()
            
            return list(results)

    def save_news_intel(
        self,
        code: str,
        name: str,
        dimension: str,
        query: str,
        response: 'SearchResponse',
        query_context: Optional[Dict[str, str]] = None
    ) -> int:
        """
        保存新闻情报到数据库

        去重策略：
        - 优先按 URL 去重（唯一约束）
        - URL 缺失时按 title + source + published_date 进行软去重

        关联策略：
        - query_context 记录用户查询信息（平台、用户、会话、原始指令等）
        """
        if not response or not response.results:
            return 0

        saved_count = 0
        query_ctx = query_context or {}
        current_query_id = (query_ctx.get("query_id") or "").strip()

        def _write(session: Session) -> int:
            local_saved_count = 0

            for item in response.results:
                title = (item.title or '').strip()
                url = (item.url or '').strip()
                source = (item.source or '').strip()
                snippet = (item.snippet or '').strip()
                published_date = self._parse_published_date(item.published_date)

                if not title and not url:
                    continue

                url_key = url or self._build_fallback_url_key(
                    code=code,
                    title=title,
                    source=source,
                    published_date=published_date
                )

                existing = session.execute(
                    select(NewsIntel).where(NewsIntel.url == url_key)
                ).scalar_one_or_none()

                if existing:
                    existing.name = name or existing.name
                    existing.dimension = dimension or existing.dimension
                    existing.query = query or existing.query
                    existing.provider = response.provider or existing.provider
                    existing.snippet = snippet or existing.snippet
                    existing.source = source or existing.source
                    existing.published_date = published_date or existing.published_date
                    existing.fetched_at = datetime.now()

                    if query_context:
                        if not existing.query_id and current_query_id:
                            existing.query_id = current_query_id
                        existing.query_source = (
                            query_context.get("query_source") or existing.query_source
                        )
                        existing.requester_platform = (
                            query_context.get("requester_platform") or existing.requester_platform
                        )
                        existing.requester_user_id = (
                            query_context.get("requester_user_id") or existing.requester_user_id
                        )
                        existing.requester_user_name = (
                            query_context.get("requester_user_name") or existing.requester_user_name
                        )
                        existing.requester_chat_id = (
                            query_context.get("requester_chat_id") or existing.requester_chat_id
                        )
                        existing.requester_message_id = (
                            query_context.get("requester_message_id") or existing.requester_message_id
                        )
                        existing.requester_query = (
                            query_context.get("requester_query") or existing.requester_query
                        )
                    continue

                try:
                    with session.begin_nested():
                        record = NewsIntel(
                            code=code,
                            name=name,
                            dimension=dimension,
                            query=query,
                            provider=response.provider,
                            title=title,
                            snippet=snippet,
                            url=url_key,
                            source=source,
                            published_date=published_date,
                            fetched_at=datetime.now(),
                            query_id=current_query_id or None,
                            query_source=query_ctx.get("query_source"),
                            requester_platform=query_ctx.get("requester_platform"),
                            requester_user_id=query_ctx.get("requester_user_id"),
                            requester_user_name=query_ctx.get("requester_user_name"),
                            requester_chat_id=query_ctx.get("requester_chat_id"),
                            requester_message_id=query_ctx.get("requester_message_id"),
                            requester_query=query_ctx.get("requester_query"),
                        )
                        session.add(record)
                        session.flush()
                    local_saved_count += 1
                except IntegrityError:
                    logger.debug("新闻情报重复（已跳过）: %s %s", code, url_key)

            return local_saved_count

        try:
            saved_count = self._run_write_transaction(
                f"save_news_intel[{code}]",
                _write,
            )
            logger.info(f"保存新闻情报成功: {code}, 新增 {saved_count} 条")
        except Exception as e:
            logger.error(f"保存新闻情报失败: {e}")
            raise

        return saved_count

    def save_fundamental_snapshot(
        self,
        query_id: str,
        code: str,
        payload: Optional[Dict[str, Any]],
        source_chain: Optional[Any] = None,
        coverage: Optional[Any] = None,
    ) -> int:
        """
        保存基本面快照（P0 write-only）。失败不抛异常，返回写入条数 0/1。
        """
        if not query_id or not code or payload is None:
            return 0

        try:
            def _write(session: Session) -> int:
                session.add(
                    FundamentalSnapshot(
                        query_id=query_id,
                        code=code,
                        payload=self._safe_json_dumps(payload),
                        source_chain=self._safe_json_dumps(source_chain or []),
                        coverage=self._safe_json_dumps(coverage or {}),
                    )
                )
                return 1
            return self._run_write_transaction(
                f"save_fundamental_snapshot[{query_id}:{code}]",
                _write,
            )
        except Exception as e:
            logger.debug(
                "基本面快照写入失败（fail-open）: query_id=%s code=%s err=%s",
                query_id,
                code,
                e,
            )
            return 0

    def get_latest_fundamental_snapshot(
        self,
        query_id: str,
        code: str,
    ) -> Optional[Dict[str, Any]]:
        """
        获取指定 query_id + code 的最新基本面快照 payload。

        读取失败或不存在时返回 None（fail-open）。
        """
        if not query_id or not code:
            return None

        with self.get_session() as session:
            try:
                row = session.execute(
                    select(FundamentalSnapshot)
                    .where(
                        and_(
                            FundamentalSnapshot.query_id == query_id,
                            FundamentalSnapshot.code == code,
                        )
                    )
                    .order_by(desc(FundamentalSnapshot.created_at))
                    .limit(1)
                ).scalar_one_or_none()
            except Exception as e:
                logger.debug(
                    "基本面快照读取失败（fail-open）: query_id=%s code=%s err=%s",
                    query_id,
                    code,
                    e,
                )
                return None

            if row is None:
                return None
            try:
                payload = json.loads(row.payload or "{}")
                return payload if isinstance(payload, dict) else None
            except Exception:
                return None

    def get_recent_news(self, code: str, days: int = 7, limit: int = 20) -> List[NewsIntel]:
        """
        获取指定股票最近 N 天的新闻情报
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            results = session.execute(
                select(NewsIntel)
                .where(
                    and_(
                        NewsIntel.code == code,
                        NewsIntel.fetched_at >= cutoff_date
                    )
                )
                .order_by(desc(NewsIntel.fetched_at))
                .limit(limit)
            ).scalars().all()

            return list(results)

    def get_news_intel_by_query_id(self, query_id: str, limit: int = 20) -> List[NewsIntel]:
        """
        根据 query_id 获取新闻情报列表

        Args:
            query_id: 分析记录唯一标识
            limit: 返回数量限制

        Returns:
            NewsIntel 列表（按发布时间或抓取时间倒序）
        """
        from sqlalchemy import func

        with self.get_session() as session:
            results = session.execute(
                select(NewsIntel)
                .where(NewsIntel.query_id == query_id)
                .order_by(
                    desc(func.coalesce(NewsIntel.published_date, NewsIntel.fetched_at)),
                    desc(NewsIntel.fetched_at)
                )
                .limit(limit)
            ).scalars().all()

            return list(results)

    def save_analysis_history(
        self,
        result: Any,
        query_id: str,
        report_type: str,
        news_content: Optional[str],
        context_snapshot: Optional[Dict[str, Any]] = None,
        save_snapshot: bool = True
    ) -> int:
        """
        保存分析结果历史记录。

        Returns:
            新保存的 AnalysisHistory.id；保存失败返回 0。
        """
        if result is None:
            return 0

        sniper_points = self._extract_sniper_points(result)
        raw_result = self._build_raw_result(result)
        context_text = None
        if save_snapshot and context_snapshot is not None:
            context_text = self._safe_json_dumps(context_snapshot)

        try:
            def _write(session: Session) -> int:
                history = AnalysisHistory(
                    query_id=query_id,
                    code=result.code,
                    name=result.name,
                    report_type=report_type,
                    sentiment_score=result.sentiment_score,
                    operation_advice=result.operation_advice,
                    trend_prediction=result.trend_prediction,
                    analysis_summary=result.analysis_summary,
                    raw_result=self._safe_json_dumps(raw_result),
                    news_content=news_content,
                    context_snapshot=context_text,
                    ideal_buy=sniper_points.get("ideal_buy"),
                    secondary_buy=sniper_points.get("secondary_buy"),
                    stop_loss=sniper_points.get("stop_loss"),
                    take_profit=sniper_points.get("take_profit"),
                    created_at=datetime.now(),
                )
                session.add(history)
                session.flush()
                return int(history.id or 0)
            return self._run_write_transaction(
                f"save_analysis_history[{result.code}]",
                _write,
            )
        except Exception as e:
            logger.error(f"保存分析历史失败: {e}")
            return 0

    def update_analysis_history_diagnostics(
        self,
        *,
        query_id: str,
        code: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
        notification_runs: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """
        更新已保存分析历史的运行诊断快照。

        通知结果通常在分析历史落库后才产生，因此这里仅补写
        context_snapshot.diagnostics，不改变报告正文或其它历史字段。
        """
        if not query_id or (diagnostics is None and not notification_runs):
            return 0

        try:
            def _write(session: Session) -> int:
                conditions = [AnalysisHistory.query_id == query_id]
                if code:
                    conditions.append(AnalysisHistory.code == code)

                row = session.execute(
                    select(AnalysisHistory)
                    .where(and_(*conditions))
                    .order_by(desc(AnalysisHistory.created_at))
                    .limit(1)
                ).scalars().first()
                if row is None:
                    return 0

                context_snapshot: Dict[str, Any] = {}
                if row.context_snapshot:
                    try:
                        parsed = json.loads(row.context_snapshot)
                        if isinstance(parsed, dict):
                            context_snapshot = parsed
                    except Exception:
                        context_snapshot = {}

                if diagnostics is not None:
                    context_snapshot["diagnostics"] = diagnostics
                else:
                    existing_diagnostics = context_snapshot.get("diagnostics")
                    if not isinstance(existing_diagnostics, dict):
                        existing_diagnostics = {
                            "query_id": query_id,
                            "stock_code": code,
                            "notification_runs": [],
                        }
                    runs = existing_diagnostics.get("notification_runs")
                    if not isinstance(runs, list):
                        runs = []
                    trace_id = existing_diagnostics.get("trace_id")
                    for run in notification_runs or []:
                        if isinstance(run, dict):
                            run_payload = dict(run)
                            if trace_id and not run_payload.get("trace_id"):
                                run_payload["trace_id"] = trace_id
                            runs.append(run_payload)
                    existing_diagnostics["notification_runs"] = runs
                    context_snapshot["diagnostics"] = existing_diagnostics
                row.context_snapshot = self._safe_json_dumps(context_snapshot)
                return 1

            return self._run_write_transaction(
                f"update_analysis_history_diagnostics[{query_id}:{code or '*'}]",
                _write,
            )
        except Exception as e:
            logger.warning(
                "更新分析历史诊断快照失败（fail-open）: query_id=%s code=%s err=%s",
                query_id,
                code,
                e,
            )
            return 0

    def get_analysis_history(
        self,
        code: Optional[str] = None,
        query_id: Optional[str] = None,
        days: int = 30,
        limit: int = 50,
        exclude_query_id: Optional[str] = None,
    ) -> List[AnalysisHistory]:
        """
        Query analysis history records.

        Notes:
        - If query_id is provided, perform exact lookup and ignore days window.
        - If query_id is not provided, apply days-based time filtering.
        - exclude_query_id: exclude records with this query_id (for history comparison).
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            conditions = []

            if query_id:
                conditions.append(AnalysisHistory.query_id == query_id)
            else:
                conditions.append(AnalysisHistory.created_at >= cutoff_date)

            if code:
                conditions.append(AnalysisHistory.code == code)

            # exclude_query_id only applies when not doing exact lookup (query_id is None)
            if exclude_query_id and not query_id:
                conditions.append(AnalysisHistory.query_id != exclude_query_id)

            results = session.execute(
                select(AnalysisHistory)
                .where(and_(*conditions))
                .order_by(desc(AnalysisHistory.created_at))
                .limit(limit)
            ).scalars().all()

            return list(results)

    def get_latest_analysis_history_id(
        self,
        *,
        query_id: str,
        code: str,
        report_type: str,
    ) -> Optional[int]:
        """Return the latest matching history id for read-only lookups.

        P2 automatic DecisionSignal extraction receives the freshly saved id
        directly from ``save_analysis_history()`` and does not use this helper.
        """

        if not query_id or not code or not report_type:
            return None

        with self.get_session() as session:
            return session.execute(
                select(AnalysisHistory.id)
                .where(
                    AnalysisHistory.query_id == query_id,
                    AnalysisHistory.code == code,
                    AnalysisHistory.report_type == report_type,
                )
                .order_by(desc(AnalysisHistory.created_at), desc(AnalysisHistory.id))
                .limit(1)
            ).scalar_one_or_none()
    
    def get_analysis_history_paginated(
        self,
        code: Optional[Union[str, List[str]]] = None,
        report_type: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        offset: int = 0,
        limit: int = 20
    ) -> Tuple[List[AnalysisHistory], int]:
        """
        分页查询分析历史记录（带总数）
        
        Args:
            code: 股票代码筛选
            report_type: 报告类型筛选
            start_date: 开始日期（含）
            end_date: 结束日期（含）
            offset: 偏移量（跳过前 N 条）
            limit: 每页数量
            
        Returns:
            Tuple[List[AnalysisHistory], int]: (记录列表, 总数)
        """
        from sqlalchemy import func
        
        with self.get_session() as session:
            conditions = []
            
            if code:
                if isinstance(code, list):
                    codes = [c for c in code if c]
                    if codes:
                        conditions.append(AnalysisHistory.code.in_(codes))
                else:
                    conditions.append(AnalysisHistory.code == code)
            if report_type:
                conditions.append(AnalysisHistory.report_type == report_type)
            if start_date:
                # created_at >= start_date 00:00:00
                conditions.append(AnalysisHistory.created_at >= datetime.combine(start_date, datetime.min.time()))
            if end_date:
                # created_at < end_date+1 00:00:00 (即 <= end_date 23:59:59)
                conditions.append(AnalysisHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
            
            # 构建 where 子句
            where_clause = and_(*conditions) if conditions else True
            
            # 查询总数
            total_query = select(func.count(AnalysisHistory.id)).where(where_clause)
            total = session.execute(total_query).scalar() or 0
            
            # 查询分页数据
            data_query = (
                select(AnalysisHistory)
                .where(where_clause)
                .order_by(desc(AnalysisHistory.created_at))
                .offset(offset)
                .limit(limit)
            )
            results = session.execute(data_query).scalars().all()
            
            return list(results), total
    
    def get_analysis_history_by_id(self, record_id: int) -> Optional[AnalysisHistory]:
        """
        根据数据库主键 ID 查询单条分析历史记录
        
        由于 query_id 可能重复（批量分析时多条记录共享同一 query_id），
        使用主键 ID 确保精确查询唯一记录。
        
        Args:
            record_id: 分析历史记录的主键 ID
            
        Returns:
            AnalysisHistory 对象，不存在返回 None
        """
        with self.get_session() as session:
            result = session.execute(
                select(AnalysisHistory).where(AnalysisHistory.id == record_id)
            ).scalars().first()
            return result

    def delete_analysis_history_records(self, record_ids: List[int]) -> int:
        """
        删除指定的分析历史记录。

        同时清理依赖这些历史记录的回测结果和分析来源决策信号，避免
        依赖历史记录的派生数据残留。DecisionSignal 的 source_report_id
        允许弱引用，因此这里只清理 source_type=analysis 的真实历史绑定信号。

        Args:
            record_ids: 要删除的历史记录主键 ID 列表

        Returns:
            实际删除的历史记录数量
        """
        ids = sorted({int(record_id) for record_id in record_ids if record_id is not None})
        if not ids:
            return 0

        def _write(session: Session) -> int:
            existing_ids = sorted(
                session.execute(
                    select(AnalysisHistory.id).where(AnalysisHistory.id.in_(ids))
                ).scalars().all()
            )
            if not existing_ids:
                return 0

            linked_signal_ids = sorted(
                session.execute(
                    select(DecisionSignalRecord.id).where(
                        and_(
                            DecisionSignalRecord.source_type == "analysis",
                            DecisionSignalRecord.source_report_id.in_(existing_ids),
                        )
                    )
                ).scalars().all()
            )
            if linked_signal_ids:
                session.execute(
                    delete(DecisionSignalOutcomeRecord).where(
                        DecisionSignalOutcomeRecord.signal_id.in_(linked_signal_ids)
                    )
                )
                session.execute(
                    delete(DecisionSignalFeedbackRecord).where(
                        DecisionSignalFeedbackRecord.signal_id.in_(linked_signal_ids)
                    )
                )
                session.execute(
                    delete(DecisionSignalRecord).where(DecisionSignalRecord.id.in_(linked_signal_ids))
                )
            session.execute(
                delete(BacktestResult).where(BacktestResult.analysis_history_id.in_(existing_ids))
            )
            session.execute(
                delete(SkillOpinionSampleRecord).where(
                    SkillOpinionSampleRecord.analysis_history_id.in_(existing_ids)
                )
            )
            result = session.execute(
                delete(AnalysisHistory).where(AnalysisHistory.id.in_(existing_ids))
            )
            return result.rowcount or 0

        return self._run_write_transaction(
            "delete analysis history records",
            _write,
        )

    def get_distinct_stocks_from_history(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 200,
        include_market_review: bool = False,
    ) -> List[AnalysisHistory]:
        """
        获取历史记录中的不重复股票列表，每只股票取最新一条记录。

        使用子查询按 code 分组取 MAX(id)，再 JOIN 回查完整记录。
        默认排除大盘复盘，避免混入普通个股栏。

        Args:
            start_date: 开始日期
            end_date: 结束日期
            limit: 最大返回数量
            include_market_review: 是否包含大盘复盘记录

        Returns:
            每条股票最新一条 AnalysisHistory 记录列表
        """
        with self.get_session() as session:
            subq = (
                select(
                    AnalysisHistory.code,
                    func.max(AnalysisHistory.id).label("max_id"),
                )
            )
            if start_date:
                subq = subq.where(
                    AnalysisHistory.created_at >= datetime.combine(start_date, datetime.min.time())
                )
            if end_date:
                subq = subq.where(
                    AnalysisHistory.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
                )
            if not include_market_review:
                subq = subq.where(
                    and_(
                        AnalysisHistory.code != "MARKET",
                        or_(
                            AnalysisHistory.report_type.is_(None),
                            AnalysisHistory.report_type != "market_review",
                        ),
                    )
                )
            subq = subq.group_by(AnalysisHistory.code).subquery()

            results = (
                session.execute(
                    select(AnalysisHistory)
                    .join(subq, AnalysisHistory.id == subq.c.max_id)
                    .order_by(
                        desc(AnalysisHistory.created_at),
                    )
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return list(results)

    def get_latest_analysis_by_query_id(
        self,
        query_id: str,
        *,
        code: Optional[str] = None,
        report_type: Optional[str] = None,
    ) -> Optional[AnalysisHistory]:
        """
        根据 query_id 查询最新一条分析历史记录

        query_id 在批量分析时可能重复，故返回最近创建的一条。

        Args:
            query_id: 分析记录关联的 query_id
            code: 可选股票代码过滤，用于区分同一 query_id 下的 MARKET 与个股记录
            report_type: 可选报告类型过滤

        Returns:
            AnalysisHistory 对象，不存在返回 None
        """
        with self.get_session() as session:
            conditions = [AnalysisHistory.query_id == query_id]
            if code:
                conditions.append(AnalysisHistory.code == code)
            if report_type:
                conditions.append(AnalysisHistory.report_type == report_type)

            result = session.execute(
                select(AnalysisHistory)
                .where(and_(*conditions))
                .order_by(desc(AnalysisHistory.created_at))
                .limit(1)
            ).scalars().first()
            return result
    
    def get_data_range(
        self, 
        code: str, 
        start_date: date, 
        end_date: date
    ) -> List[StockDaily]:
        """
        获取指定日期范围的数据
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            StockDaily 对象列表
        """
        with self.get_session() as session:
            results = session.execute(
                select(StockDaily)
                .where(
                    and_(
                        StockDaily.code == code,
                        StockDaily.date >= start_date,
                        StockDaily.date <= end_date
                    )
                )
                .order_by(StockDaily.date)
            ).scalars().all()
            
            return list(results)
    
    def save_daily_data(
        self, 
        df: pd.DataFrame, 
        code: str,
        data_source: str = "Unknown"
    ) -> int:
        """
        保存日线数据到数据库
        
        策略：
        - 按 `(code, date)` 做批量 UPSERT，已存在记录会覆盖更新
        - 同一批次内若存在重复日期，以最后一条记录为准
        - SQLite 分支按 chunk 写入以避免绑定参数上限
        
        Args:
            df: 包含日线数据的 DataFrame
            code: 股票代码
            data_source: 数据来源名称
            
        Returns:
            本次实际新增的记录数（不含更新）
        """
        if df is None or df.empty:
            logger.warning(f"保存数据为空，跳过 {code}")
            return 0

        now = datetime.now()
        records_by_date: Dict[date, Dict[str, Any]] = {}
        for row in df.to_dict(orient='records'):
            row_date = self._normalize_daily_date(row.get('date'))
            records_by_date[row_date] = {
                'code': code,
                'date': row_date,
                'open': self._normalize_sql_value(row.get('open')),
                'high': self._normalize_sql_value(row.get('high')),
                'low': self._normalize_sql_value(row.get('low')),
                'close': self._normalize_sql_value(row.get('close')),
                'volume': self._normalize_sql_value(row.get('volume')),
                'amount': self._normalize_sql_value(row.get('amount')),
                'pct_chg': self._normalize_sql_value(row.get('pct_chg')),
                'ma5': self._normalize_sql_value(row.get('ma5')),
                'ma10': self._normalize_sql_value(row.get('ma10')),
                'ma20': self._normalize_sql_value(row.get('ma20')),
                'volume_ratio': self._normalize_sql_value(row.get('volume_ratio')),
                'data_source': data_source,
                'created_at': now,
                'updated_at': now,
            }

        if not records_by_date:
            return 0

        records = list(records_by_date.values())
        batch_dates = list(records_by_date.keys())

        def _write(session: Session) -> int:
            if self._is_sqlite_engine:
                # SQLite has a per-statement bind-parameter limit (commonly 999).
                # Each record has ~15 columns, so chunk upserts to stay within bounds.
                _SQLITE_CHUNK = 50
                # `_run_write_transaction()` opens SQLite writes with
                # `BEGIN IMMEDIATE`, so existence checks and upsert execute
                # within one stable write window.
                existing_dates = set()
                _COUNT_CHUNK = 500
                for j in range(0, len(batch_dates), _COUNT_CHUNK):
                    chunk_dates = batch_dates[j : j + _COUNT_CHUNK]
                    if not chunk_dates:
                        continue
                    existing_dates.update(
                        session.execute(
                            select(StockDaily.date).where(
                                and_(
                                    StockDaily.code == code,
                                    StockDaily.date.in_(chunk_dates),
                                )
                            )
                        ).scalars().all()
                    )
                new_records = [
                    record for record in records if record['date'] not in existing_dates
                ]
                for i in range(0, len(records), _SQLITE_CHUNK):
                    chunk = records[i : i + _SQLITE_CHUNK]
                    stmt = sqlite_insert(StockDaily).values(chunk)
                    excluded = stmt.excluded
                    session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=['code', 'date'],
                            set_={
                                'open': excluded.open,
                                'high': excluded.high,
                                'low': excluded.low,
                                'close': excluded.close,
                                'volume': excluded.volume,
                                'amount': excluded.amount,
                                'pct_chg': excluded.pct_chg,
                                'ma5': excluded.ma5,
                                'ma10': excluded.ma10,
                                'ma20': excluded.ma20,
                                'volume_ratio': excluded.volume_ratio,
                                'data_source': excluded.data_source,
                                'updated_at': excluded.updated_at,
                            },
                        )
                    )
                return len(new_records)
            else:
                existing_rows = {
                    row.date: row
                    for row in session.execute(
                        select(StockDaily).where(
                            and_(
                                StockDaily.code == code,
                                StockDaily.date.in_(batch_dates),
                            )
                        )
                    ).scalars().all()
                }
                new_count = 0
                for record in records:
                    existing = existing_rows.get(record['date'])
                    if existing is None:
                        session.add(StockDaily(**record))
                        new_count += 1
                        continue
                    existing.open = record['open']
                    existing.high = record['high']
                    existing.low = record['low']
                    existing.close = record['close']
                    existing.volume = record['volume']
                    existing.amount = record['amount']
                    existing.pct_chg = record['pct_chg']
                    existing.ma5 = record['ma5']
                    existing.ma10 = record['ma10']
                    existing.ma20 = record['ma20']
                    existing.volume_ratio = record['volume_ratio']
                    existing.data_source = record['data_source']
                    existing.updated_at = record['updated_at']
                return new_count

        try:
            saved_count = self._run_write_transaction(
                f"save_daily_data[{code}]",
                _write,
            )
            logger.info(f"保存 {code} 数据成功，新增 {saved_count} 条")
            return saved_count
        except Exception as e:
            logger.error(f"保存 {code} 数据失败: {e}")
            raise
    
    def get_analysis_context(
        self, 
        code: str,
        target_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取分析所需的上下文数据
        
        返回今日数据 + 昨日数据的对比信息
        
        Args:
            code: 股票代码
            target_date: 目标日期（默认今天）
            
        Returns:
            包含今日数据、昨日对比等信息的字典
        """
        if target_date is None:
            target_date = date.today()
        # 注意：尽管入参提供了 target_date，但当前实现实际使用的是“最新两天数据”（get_latest_data），
        # 并不会按 target_date 精确取当日/前一交易日的上下文。
        # 因此若未来需要支持“按历史某天复盘/重算”的可解释性，这里需要调整。
        # 该行为目前保留（按需求不改逻辑）。
        
        # 获取最近2天数据
        recent_data = self.get_latest_data(code, days=2)
        
        if not recent_data:
            logger.warning(f"未找到 {code} 的数据")
            return None
        
        today_data = recent_data[0]
        yesterday_data = recent_data[1] if len(recent_data) > 1 else None
        
        context = {
            'code': code,
            'date': today_data.date.isoformat(),
            'today': today_data.to_dict(),
        }
        
        if yesterday_data:
            context['yesterday'] = yesterday_data.to_dict()
            
            # 计算相比昨日的变化
            if yesterday_data.volume and yesterday_data.volume > 0:
                context['volume_change_ratio'] = round(
                    today_data.volume / yesterday_data.volume, 2
                )
            
            if yesterday_data.close and yesterday_data.close > 0:
                context['price_change_ratio'] = round(
                    (today_data.close - yesterday_data.close) / yesterday_data.close * 100, 2
                )
            
            # 均线形态判断
            context['ma_status'] = self._analyze_ma_status(today_data)
        
        return context
    
    def _analyze_ma_status(self, data: StockDaily) -> str:
        """
        分析均线形态
        
        判断条件：
        - 多头排列：close > ma5 > ma10 > ma20
        - 空头排列：close < ma5 < ma10 < ma20
        - 震荡整理：其他情况
        """
        # 注意：这里的均线形态判断基于“close/ma5/ma10/ma20”静态比较，
        # 未考虑均线拐点、斜率、或不同数据源复权口径差异。
        # 该行为目前保留（按需求不改逻辑）。
        close = data.close or 0
        ma5 = data.ma5 or 0
        ma10 = data.ma10 or 0
        ma20 = data.ma20 or 0
        
        if close > ma5 > ma10 > ma20 > 0:
            return "多头排列 📈"
        elif close < ma5 < ma10 < ma20 and ma20 > 0:
            return "空头排列 📉"
        elif close > ma5 and ma5 > ma10:
            return "短期向好 🔼"
        elif close < ma5 and ma5 < ma10:
            return "短期走弱 🔽"
        else:
            return "震荡整理 ↔️"

    @staticmethod
    def _parse_published_date(value: Optional[str]) -> Optional[datetime]:
        """
        解析发布时间字符串（失败返回 None）
        """
        if not value:
            return None

        if isinstance(value, datetime):
            return value

        text = str(value).strip()
        if not text:
            return None

        # 优先尝试 ISO 格式
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def _safe_json_dumps(data: Any) -> str:
        """
        安全序列化为 JSON 字符串
        """
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            return json.dumps(str(data), ensure_ascii=False)

    @staticmethod
    def _build_raw_result(result: Any) -> Dict[str, Any]:
        """
        生成完整分析结果字典
        """
        data = result.to_dict() if hasattr(result, "to_dict") else {}
        data.update({
            'data_sources': getattr(result, 'data_sources', ''),
            'raw_response': getattr(result, 'raw_response', None),
        })
        return data

    @staticmethod
    def _parse_sniper_value(value: Any) -> Optional[float]:
        return parse_sniper_value(value)

    def _extract_sniper_points(self, result: Any) -> Dict[str, Optional[float]]:
        """Extract normalized sniper point values from an AnalysisResult."""

        return extract_sniper_points(result)

    @staticmethod
    def _build_fallback_url_key(
        code: str,
        title: str,
        source: str,
        published_date: Optional[datetime]
    ) -> str:
        """
        生成无 URL 时的去重键（确保稳定且较短）
        """
        date_str = published_date.isoformat() if published_date else ""
        raw_key = f"{code}|{title}|{source}|{date_str}"
        digest = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
        return f"no-url:{code}:{digest}"

    def save_conversation_message(self, session_id: str, role: str, content: str) -> int:
        """
        保存 Agent 对话消息
        """
        with self.session_scope() as session:
            msg = ConversationMessage(
                session_id=session_id,
                role=role,
                content=content
            )
            session.add(msg)
            session.flush()
            return int(msg.id)

    def get_conversation_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取 Agent 对话历史
        """
        with self.session_scope() as session:
            stmt = select(ConversationMessage).filter(
                ConversationMessage.session_id == session_id
            ).order_by(ConversationMessage.created_at.desc()).limit(limit)
            messages = session.execute(stmt).scalars().all()

            # 倒序返回，保证时间顺序
            return [{"role": msg.role, "content": msg.content} for msg in reversed(messages)]

    def get_visible_conversation_messages(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return visible user/assistant conversation messages in chronological order."""
        with self.session_scope() as session:
            stmt = (
                select(ConversationMessage)
                .where(
                    and_(
                        ConversationMessage.session_id == session_id,
                        ConversationMessage.role.in_(["user", "assistant"]),
                    )
                )
                .order_by(ConversationMessage.created_at, ConversationMessage.id)
            )
            if limit is not None:
                stmt = (
                    stmt.order_by(None)
                    .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
                    .limit(limit)
                )
            messages = session.execute(stmt).scalars().all()
            if limit is not None:
                messages = list(reversed(messages))
            return [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at,
                }
                for msg in messages
                if msg.content
            ]

    def get_conversation_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return the rolling summary for a conversation session, if present."""
        with self.session_scope() as session:
            stmt = select(ConversationSummary).where(
                ConversationSummary.session_id == session_id
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": row.id,
                "session_id": row.session_id,
                "summary": row.summary,
                "covered_message_id": row.covered_message_id,
                "source_message_count": row.source_message_count,
                "estimated_tokens": row.estimated_tokens,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_agent_provider_turn(
        self,
        *,
        session_id: str,
        run_id: str,
        provider: str,
        model: str,
        anchor_user_message_id: int,
        anchor_assistant_message_id: int,
        messages: List[Dict[str, Any]],
        contains_reasoning: bool,
        contains_tool_calls: bool,
        contains_thinking_blocks: bool,
        must_roundtrip: bool,
        estimated_tokens: int,
    ) -> int:
        """Persist one provider protocol trace and enforce per-model retention."""
        with self.session_scope() as session:
            row = AgentProviderTurn(
                session_id=session_id,
                run_id=run_id,
                provider=provider,
                model=model,
                anchor_user_message_id=int(anchor_user_message_id or 0),
                anchor_assistant_message_id=int(anchor_assistant_message_id or 0),
                messages_json=json.dumps(messages or [], ensure_ascii=False, default=str),
                contains_reasoning=bool(contains_reasoning),
                contains_tool_calls=bool(contains_tool_calls),
                contains_thinking_blocks=bool(contains_thinking_blocks),
                must_roundtrip=bool(must_roundtrip),
                estimated_tokens=int(estimated_tokens or 0),
            )
            session.add(row)
            session.flush()
            row_id = int(row.id)
            if row.must_roundtrip:
                self._trim_agent_provider_turns(
                    session=session,
                    session_id=session_id,
                    provider=provider,
                    model=model,
                    keep=PROVIDER_TRACE_RETENTION_LIMIT,
                )
            return row_id

    def get_agent_provider_turns(
        self,
        session_id: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        must_roundtrip_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return provider trace turns in chronological order."""
        with self.session_scope() as session:
            conditions = [AgentProviderTurn.session_id == session_id]
            if provider:
                conditions.append(AgentProviderTurn.provider == provider)
            if model:
                conditions.append(AgentProviderTurn.model == model)
            if must_roundtrip_only:
                conditions.append(AgentProviderTurn.must_roundtrip.is_(True))
            stmt = (
                select(AgentProviderTurn)
                .where(and_(*conditions))
                .order_by(AgentProviderTurn.created_at, AgentProviderTurn.id)
            )
            rows = session.execute(stmt).scalars().all()
            result = []
            for row in rows:
                try:
                    messages = json.loads(row.messages_json or "[]")
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Invalid provider trace messages_json skipped for session %s turn %s: %s",
                        row.session_id,
                        row.id,
                        exc,
                    )
                    messages = []
                result.append({
                    "id": row.id,
                    "session_id": row.session_id,
                    "run_id": row.run_id,
                    "provider": row.provider,
                    "model": row.model,
                    "anchor_user_message_id": row.anchor_user_message_id,
                    "anchor_assistant_message_id": row.anchor_assistant_message_id,
                    "messages": messages if isinstance(messages, list) else [],
                    "messages_json": row.messages_json,
                    "contains_reasoning": row.contains_reasoning,
                    "contains_tool_calls": row.contains_tool_calls,
                    "contains_thinking_blocks": row.contains_thinking_blocks,
                    "must_roundtrip": row.must_roundtrip,
                    "estimated_tokens": row.estimated_tokens,
                    "created_at": row.created_at,
                })
            return result

    def _trim_agent_provider_turns(
        self,
        *,
        session: Session,
        session_id: str,
        provider: str,
        model: str,
        keep: int,
    ) -> int:
        old_ids_stmt = (
            select(AgentProviderTurn.id)
            .where(
                and_(
                    AgentProviderTurn.session_id == session_id,
                    AgentProviderTurn.provider == provider,
                    AgentProviderTurn.model == model,
                    AgentProviderTurn.must_roundtrip.is_(True),
                )
            )
            .order_by(AgentProviderTurn.created_at.desc(), AgentProviderTurn.id.desc())
            .offset(max(0, int(keep)))
        )
        old_ids = list(session.execute(old_ids_stmt).scalars().all())
        if not old_ids:
            return 0
        result = session.execute(
            delete(AgentProviderTurn).where(AgentProviderTurn.id.in_(old_ids))
        )
        return int(result.rowcount or 0)

    def upsert_conversation_summary(
        self,
        session_id: str,
        summary: str,
        covered_message_id: int,
        source_message_count: int,
        estimated_tokens: int,
    ) -> None:
        """Create or update the rolling summary for a conversation session."""
        with self.session_scope() as session:
            now = datetime.now()
            values = {
                "session_id": session_id,
                "summary": summary,
                "covered_message_id": int(covered_message_id or 0),
                "source_message_count": int(source_message_count or 0),
                "estimated_tokens": int(estimated_tokens or 0),
                "updated_at": now,
            }
            stmt = sqlite_insert(ConversationSummary).values(**values)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["session_id"],
                    set_=values,
                )
            )

    def conversation_session_exists(self, session_id: str) -> bool:
        """Return True when at least one message exists for the given session."""
        with self.session_scope() as session:
            stmt = (
                select(ConversationMessage.id)
                .where(ConversationMessage.session_id == session_id)
                .limit(1)
            )
            return session.execute(stmt).scalar() is not None

    def get_chat_sessions(
        self,
        limit: int = 50,
        session_prefix: Optional[str] = None,
        extra_session_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取聊天会话列表（从 conversation_messages 聚合）

        Args:
            limit: Maximum number of sessions to return.
            session_prefix: If provided, only return sessions whose session_id
                starts with this prefix.  Used for per-user isolation (e.g.
                ``"telegram_12345"``).
            extra_session_ids: Optional exact session ids to include in
                addition to the scoped prefix.

        Returns:
            按最近活跃时间倒序的会话列表，每条包含 session_id, title, message_count, last_active
        """
        from sqlalchemy import func

        with self.session_scope() as session:
            normalized_prefix = None
            if session_prefix:
                normalized_prefix = session_prefix if session_prefix.endswith(":") else f"{session_prefix}:"
            exact_ids = [sid for sid in (extra_session_ids or []) if sid]

            # 聚合每个 session 的消息数和最后活跃时间
            base = (
                select(
                    ConversationMessage.session_id,
                    func.count(ConversationMessage.id).label("message_count"),
                    func.min(ConversationMessage.created_at).label("created_at"),
                    func.max(ConversationMessage.created_at).label("last_active"),
                )
            )
            conditions = []
            if normalized_prefix:
                conditions.append(ConversationMessage.session_id.startswith(normalized_prefix))
            if exact_ids:
                conditions.append(ConversationMessage.session_id.in_(exact_ids))
            if conditions:
                base = base.where(or_(*conditions))
            stmt = (
                base
                .group_by(ConversationMessage.session_id)
                .order_by(desc(func.max(ConversationMessage.created_at)))
                .limit(limit)
            )
            rows = session.execute(stmt).all()

            results = []
            for row in rows:
                sid = row.session_id
                # 取该会话第一条 user 消息作为标题
                first_user_msg = session.execute(
                    select(ConversationMessage.content)
                    .where(
                        and_(
                            ConversationMessage.session_id == sid,
                            ConversationMessage.role == "user",
                        )
                    )
                    .order_by(ConversationMessage.created_at)
                    .limit(1)
                ).scalar()
                title = (first_user_msg or "新对话")[:60]

                results.append({
                    "session_id": sid,
                    "title": title,
                    "message_count": row.message_count,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_active": row.last_active.isoformat() if row.last_active else None,
                })
            return results

    def get_conversation_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取单个会话的完整消息列表（用于前端恢复历史）
        """
        with self.session_scope() as session:
            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.session_id == session_id)
                .order_by(ConversationMessage.created_at)
                .limit(limit)
            )
            messages = session.execute(stmt).scalars().all()
            return [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ]

    def delete_conversation_session(self, session_id: str) -> int:
        """
        删除指定会话的所有消息

        Returns:
            删除的消息数
        """
        with self.session_scope() as session:
            session.execute(
                delete(AgentProviderTurn).where(
                    AgentProviderTurn.session_id == session_id
                )
            )
            session.execute(
                delete(ConversationSummary).where(
                    ConversationSummary.session_id == session_id
                )
            )
            result = session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.session_id == session_id
                )
            )
            return result.rowcount

    # ------------------------------------------------------------------
    # LLM usage tracking
    # ------------------------------------------------------------------

    def record_llm_usage(
        self,
        call_type: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        stock_code: Optional[str] = None,
        **telemetry: Any,
    ) -> None:
        """Append one LLM call record to llm_usage."""
        row_values: Dict[str, Any] = {
            "call_type": call_type,
            "model": model or "unknown",
            "stock_code": stock_code,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        for column in _LLM_USAGE_TELEMETRY_COLUMN_SQL:
            row_values[column] = None if column in _LLM_USAGE_DROPPED_FREE_TEXT_COLUMNS else telemetry.get(column)
        row = LLMUsage(**row_values)
        with self.session_scope() as session:
            session.add(row)

    def get_llm_usage_summary(
        self,
        from_dt: datetime,
        to_dt: datetime,
    ) -> Dict[str, Any]:
        """Return aggregated token usage between from_dt and to_dt.

        Returns a dict with keys:
          total_calls, total_prompt_tokens, total_completion_tokens, total_tokens,
          by_call_type: list of {call_type, calls, prompt_tokens,
            completion_tokens, total_tokens},
          by_model: list of {model, calls, prompt_tokens, completion_tokens,
            total_tokens, max_total_tokens}
        """
        with self.session_scope() as session:
            base_filter = and_(
                LLMUsage.called_at >= from_dt,
                LLMUsage.called_at <= to_dt,
            )

            # Overall totals
            totals = session.execute(
                select(
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                ).where(base_filter)
            ).one()

            # Breakdown by call_type
            by_type_rows = session.execute(
                select(
                    LLMUsage.call_type,
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                )
                .where(base_filter)
                .group_by(LLMUsage.call_type)
                .order_by(desc(func.sum(LLMUsage.total_tokens)))
            ).all()

            # Breakdown by model
            by_model_rows = session.execute(
                select(
                    LLMUsage.model,
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                    func.coalesce(func.max(LLMUsage.total_tokens), 0).label("max_total_tokens"),
                )
                .where(base_filter)
                .group_by(LLMUsage.model)
                .order_by(desc(func.sum(LLMUsage.total_tokens)))
            ).all()

        return {
            "total_calls": totals.calls,
            "total_prompt_tokens": totals.prompt_tokens,
            "total_completion_tokens": totals.completion_tokens,
            "total_tokens": totals.tokens,
            "by_call_type": [
                {
                    "call_type": r.call_type,
                    "calls": r.calls,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.tokens,
                }
                for r in by_type_rows
            ],
            "by_model": [
                {
                    "model": r.model,
                    "calls": r.calls,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.tokens,
                    "max_total_tokens": r.max_total_tokens,
                }
                for r in by_model_rows
            ],
        }

    def get_llm_usage_records(
        self,
        from_dt: datetime,
        to_dt: datetime,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return recent LLM usage audit rows between from_dt and to_dt.

        Each row contains id, call_type, model, stock_code, prompt_tokens,
        completion_tokens, total_tokens, and called_at. Results are ordered by
        newest call first, and limit is clamped to the public API range.
        """
        normalized_limit = max(1, min(int(limit or 50), 200))
        with self.session_scope() as session:
            rows = session.execute(
                select(
                    LLMUsage.id,
                    LLMUsage.call_type,
                    LLMUsage.model,
                    LLMUsage.stock_code,
                    LLMUsage.prompt_tokens,
                    LLMUsage.completion_tokens,
                    LLMUsage.total_tokens,
                    LLMUsage.called_at,
                )
                .where(
                    and_(
                        LLMUsage.called_at >= from_dt,
                        LLMUsage.called_at <= to_dt,
                    )
                )
                .order_by(desc(LLMUsage.called_at), desc(LLMUsage.id))
                .limit(normalized_limit)
            ).all()

        return [
            {
                "id": r.id,
                "call_type": r.call_type,
                "model": r.model,
                "stock_code": r.stock_code,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "called_at": r.called_at,
            }
            for r in rows
        ]


# 便捷函数
def get_db() -> DatabaseManager:
    """获取数据库管理器实例的快捷方式"""
    return DatabaseManager.get_instance()


def persist_llm_usage(
    usage: Dict[str, Any],
    model: str,
    call_type: str,
    stock_code: Optional[str] = None,
) -> None:
    """Fire-and-forget: write one LLM call record to llm_usage. Never raises."""
    try:
        if usage is None:
            usage = {}
        prompt_cache_telemetry_disabled = bool(
            getattr(usage, _LLM_PROMPT_CACHE_TELEMETRY_DISABLED_ATTR, False)
        )
        prompt_tokens = _coerce_llm_usage_non_negative_int(usage.get("prompt_tokens")) or 0
        completion_tokens = _coerce_llm_usage_non_negative_int(usage.get("completion_tokens")) or 0
        total_tokens = _coerce_llm_usage_non_negative_int(usage.get("total_tokens")) or 0
        telemetry = {
            column: usage.get(column)
            for column in _LLM_USAGE_TELEMETRY_COLUMN_SQL
        }
        if prompt_cache_telemetry_disabled:
            for column in _LLM_PROMPT_CACHE_TELEMETRY_COLUMNS:
                telemetry[column] = None
        for column in _LLM_USAGE_INTEGER_TELEMETRY_COLUMNS:
            telemetry[column] = _coerce_llm_usage_non_negative_int(telemetry.get(column))
        telemetry["normalized_prompt_tokens"] = (
            telemetry.get("normalized_prompt_tokens")
            if telemetry.get("normalized_prompt_tokens") is not None
            else prompt_tokens
        )
        telemetry["normalized_completion_tokens"] = (
            telemetry.get("normalized_completion_tokens")
            if telemetry.get("normalized_completion_tokens") is not None
            else completion_tokens
        )
        telemetry["normalized_total_tokens"] = (
            telemetry.get("normalized_total_tokens")
            if telemetry.get("normalized_total_tokens") is not None
            else total_tokens
        )
        has_usage_payload = bool(usage.get("provider_usage_json")) or any(
            key in usage
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "normalized_prompt_tokens",
                "normalized_completion_tokens",
                "normalized_total_tokens",
            )
        )
        if not prompt_cache_telemetry_disabled:
            telemetry["cache_capability"] = usage.get("cache_capability") or "unknown"
            telemetry["cache_eligibility"] = usage.get("cache_eligibility") or "unknown"
            telemetry["cache_observation"] = usage.get("cache_observation") or (
                "no_usage" if not has_usage_payload else "unknown"
            )
        db = DatabaseManager.get_instance()
        db.record_llm_usage(
            call_type=call_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            stock_code=stock_code,
            **telemetry,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning("[LLM usage] failed to persist usage record: %s", exc)


def _coerce_llm_usage_non_negative_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value < 0 or not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.isdigit():
            return None
        return int(text)
    return None


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    db = get_db()
    
    print("=== 数据库测试 ===")
    print(f"数据库初始化成功")
    
    # 测试检查今日数据
    has_data = db.has_today_data('600519')
    print(f"茅台今日是否有数据: {has_data}")
    
    # 测试保存数据
    test_df = pd.DataFrame({
        'date': [date.today()],
        'open': [1800.0],
        'high': [1850.0],
        'low': [1780.0],
        'close': [1820.0],
        'volume': [10000000],
        'amount': [18200000000],
        'pct_chg': [1.5],
        'ma5': [1810.0],
        'ma10': [1800.0],
        'ma20': [1790.0],
        'volume_ratio': [1.2],
    })
    
    saved = db.save_daily_data(test_df, '600519', 'TestSource')
    print(f"保存测试数据: {saved} 条")
    
    # 测试获取上下文
    context = db.get_analysis_context('600519')
    print(f"分析上下文: {context}")
