# -*- coding: utf-8 -*-
"""闭环预警自动化调度（DSA-BACKTRACE-V1.0 #21，外挂，不改动 DSA 内核）。

把 #20 自动化预警扫描包装为可调度任务：
  - 提供 cron 调度配置（默认收盘后 周一至周五 15:30）；
  - 手动 / 定时 / 事件触发入口 `run_scheduled_scan`，包装 scan_alerts 并落「批次聚合」记录；
  - 批次历史 `get_scan_history` 供收盘后定时预警追溯；
  - 轻量 cron 匹配 `should_trigger_now`，便于接入真实调度器（APScheduler / 系统 cron / GitHub Actions）。

设计原则（对齐 §7 决策权坚守）：
  - 全部数学编排与配置校验，不依赖 LLM；
  - 沙箱无外网，扫描仍走确定性 mock，接口契约不变；
  - DSA 内核 propagate_shock 零改动，闭环传导增益经由既有幅度放大通道注入。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.services.closed_loop_scan_service import scan_alerts
from src.storage import BacktraceScanBatch, BacktraceScanSchedule, DatabaseManager

logger = logging.getLogger(__name__)

DEFAULT_CRON = '30 15 * * 1-5'          # 默认：周一至周五 15:30（收盘后）
_CONFIG_KEY = 'default'
_LEVEL_PREFIX = ('强信号', '中性', '弱信号')  # 与 closed_loop_scan_service._level 一致


# ---------------------------------------------------------------------------
# 轻量 cron 匹配（5 段：分 时 日 月 周），支持 * , - / 组合
# ---------------------------------------------------------------------------
def _match_field(field: str, val: int) -> bool:
    """判断单个 cron 字段是否命中整数 val。"""
    field = field.strip()
    if field == '*':
        return True
    for part in field.split(','):
        part = part.strip()
        if not part:
            continue
        if '/' in part:
            rng, step_s = part.split('/')
            step = int(step_s)
            if rng == '*':
                if val % step == 0:
                    return True
            elif '-' in rng:
                lo_s, hi_s = rng.split('-')
                lo, hi = int(lo_s), int(hi_s)
                if lo <= val <= hi and (val - lo) % step == 0:
                    return True
            else:
                base = int(rng)
                if (val - base) % step == 0:
                    return True
        elif '-' in part:
            lo_s, hi_s = part.split('-')
            if int(lo_s) <= val <= int(hi_s):
                return True
        else:
            if int(part) == val:
                return True
    return False


def should_trigger_now(dt: Optional[datetime] = None) -> bool:
    """按当前已落库的 cron 配置判断是否应触发（未配置时使用默认）。"""
    cfg = get_schedule_config().get('data', {})
    if not cfg.get('enabled', True):
        return False
    cron = cfg.get('cron', DEFAULT_CRON)
    return cron_matches(cron, dt)


def cron_matches(cron: str, dt: Optional[datetime] = None) -> bool:
    """解析 5 段 cron 并与 dt（默认 now）比对。"""
    parts = (cron or '').split()
    if len(parts) != 5:
        return False
    dt = dt or datetime.now()
    minute, hour, dom, month, dow = parts
    # 周字段：0/7 表示周日；datetime.weekday() 周一=0..周日=6 → 转成 0(日)..6(六)
    dow_val = (dt.weekday() + 1) % 7
    return (
        _match_field(minute, dt.minute)
        and _match_field(hour, dt.hour)
        and _match_field(dom, dt.day)
        and _match_field(month, dt.month)
        and _match_field(dow, dow_val)
    )


# ---------------------------------------------------------------------------
# 调度配置读写
# ---------------------------------------------------------------------------
def get_schedule_config() -> Dict[str, Any]:
    """读取调度配置；无配置行时回退默认。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = s.query(BacktraceScanSchedule).filter_by(config_key=_CONFIG_KEY).first()
        if not row:
            return {'code': 0, 'msg': 'ok', 'data': {'cron': DEFAULT_CRON, 'enabled': True}}
        return {'code': 0, 'msg': 'ok', 'data': {'cron': row.cron, 'enabled': bool(row.enabled)}}


def set_schedule_config(cron: Optional[str] = None, enabled: Optional[bool] = None) -> Dict[str, Any]:
    """更新调度配置；cron 须为 5 段表达式。"""
    if cron is not None:
        if len((cron or '').split()) != 5:
            return {'code': 3, 'msg': 'cron 表达式需为 5 段（分 时 日 月 周）', 'data': None}
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = s.query(BacktraceScanSchedule).filter_by(config_key=_CONFIG_KEY).first()
        if not row:
            row = BacktraceScanSchedule(config_key=_CONFIG_KEY)
            s.add(row)
        if cron is not None:
            row.cron = cron
        if enabled is not None:
            row.enabled = 1 if enabled else 0
    return get_schedule_config()


# ---------------------------------------------------------------------------
# 调度触发：包装扫描并落批次聚合
# ---------------------------------------------------------------------------
def run_scheduled_scan(
    run_type: str = 'manual',
    watchlist: Optional[list] = None,
    scheduled_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """触发一次闭环预警扫描并落「批次聚合」记录。

    Args:
      run_type:     manual(手动) | schedule(定时) | event(事件)
      watchlist:    显式标的列表；None 回退到当日大涨回溯池；显式空列表由 scan_alerts 拒绝。
      scheduled_at: 计划触发时间（定时任务回填）。手动触发时为 None。

    Returns: {code, msg, data:{ batch:ScanBatchSummary, scan:AlertScanResult }}
    """
    res = scan_alerts(watchlist=watchlist)
    if res.get('code') != 0:
        return res
    scan_data = res['data']
    alerts = scan_data.get('alerts') or []

    strong = sum(1 for a in alerts if a.get('level', '').startswith('强信号'))
    neutral = sum(1 for a in alerts if a.get('level', '').startswith('中性'))
    weak = sum(1 for a in alerts if a.get('level', '').startswith('弱信号'))
    top = alerts[0] if alerts else None

    now = datetime.now()
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        batch = BacktraceScanBatch(
            batch_id=scan_data['scanBatch'],
            run_type=run_type,
            scheduled_at=scheduled_at,
            started_at=scheduled_at or now,
            finished_at=now,
            total_scanned=scan_data['totalScanned'],
            strong_count=strong,
            neutral_count=neutral,
            weak_count=weak,
            top_stock=top.get('stockCode') if top else None,
            top_stock_name=top.get('stockName') if top else None,
            top_composite=top.get('compositeScore', 0.0) if top else 0.0,
        )
        s.add(batch)
        s.flush()
        batch_summary = batch.to_dict()

    summary = {
        'batch': batch_summary,
        'scan': scan_data,
    }
    return {'code': 0, 'msg': 'ok', 'data': summary}


def get_scan_history(limit: int = 20) -> Dict[str, Any]:
    """查询最近批次历史（按时间倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceScanBatch)
            .order_by(BacktraceScanBatch.id.desc())
            .limit(limit)
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'total': len(items), 'items': items}}
