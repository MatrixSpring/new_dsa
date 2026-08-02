# -*- coding: utf-8 -*-
"""
===================================
基于 APScheduler 的每日自动闭环调度器
===================================

实现设计文档 §6 的「精确到分钟」六段时序（替代原有 schedule 库单日 18:00 单次运行）：

  00:00~07:50  隔夜抓取 + 短线预判初算      -> overnight   (cron 01:00)
  08:00        盘前预处理 + 1周/半月刷新     -> premarket   (cron 08:00)
  09:20~15:00  盘中实时异动 + 微调推送       -> intraday    (interval 60s + 交易时段守卫)
  15:30~18:00  盘后全量落地入库              -> postmarket  (cron 16:00)
  19:00~21:00  全局批量推演 + 四周期预测重算 -> evening     (cron 19:00)
  21:30        报告归档 + 预警更新 + 复盘写入 -> archive     (cron 21:30)

特性：
- 与既有 RuntimeSchedulerService 解耦：本调度器默认独立启停，通过
  api.app 生命周期（env 门控）挂载，不改动原有单日分析链路。
- 离线可测：run_segment(..., dry_run=True) 不落库，仅返回执行摘要，便于单测。
- 交易时段守卫：intraday 段仅在中国交易日 09:20~15:00 真正执行。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, time
from typing import Any, Dict, List, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    _HAS_APSCHEDULER = True
except Exception:  # pragma: no cover - 依赖缺失时给出可读错误
    _HAS_APSCHEDULER = False

from core.dsa_daily_pipeline import (
    ALL_CYCLES,
    SEGMENT_CYCLES,
    ForecastPipeline,
    run_dsa_propagation,
)

logger = logging.getLogger(__name__)


# 六段配置（cron 用 5 字段标准表达式；interval 段用秒级间隔 + 交易时段守卫）
SEGMENTS: Dict[str, Dict[str, Any]] = {
    "overnight": {
        "trigger": "cron", "expr": "0 1 * * *",
        "cycles": SEGMENT_CYCLES["overnight"],
        "desc": "隔夜抓取 + 短线预判初算",
    },
    "premarket": {
        "trigger": "cron", "expr": "0 8 * * *",
        "cycles": SEGMENT_CYCLES["premarket"],
        "desc": "盘前预处理 + 1周/半月批量刷新",
    },
    "intraday": {
        "trigger": "interval", "seconds": 60,
        "cycles": SEGMENT_CYCLES["intraday"],
        "desc": "盘中实时异动 + 短线微调（交易时段守卫）",
    },
    "postmarket": {
        "trigger": "cron", "expr": "0 16 * * *",
        "cycles": SEGMENT_CYCLES["postmarket"],
        "desc": "盘后全量落地入库（1月/半年）",
    },
    "evening": {
        "trigger": "cron", "expr": "0 19 * * *",
        "cycles": SEGMENT_CYCLES["evening"],
        "desc": "全局批量推演 + 四周期预测重算",
    },
    "archive": {
        "trigger": "cron", "expr": "30 21 * * *",
        "cycles": SEGMENT_CYCLES["archive"],
        "desc": "报告归档 + 预警更新 + 复盘记录",
    },
}


class ApschedulerDailyLoop:
    """每日自动闭环调度器（APScheduler 后端）。"""

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        market: str = "A",
        mode: str = "synthetic",
        timezone: str = "Asia/Shanghai",
    ):
        self.symbols = list(symbols) if symbols else []
        self.market = market
        self.mode = mode
        self.timezone = timezone
        self._scheduler: Optional["BackgroundScheduler"] = None
        self._last_summaries: Dict[str, Any] = {}

    # ---- 交易时段守卫（intraday 段使用） ----
    @staticmethod
    def in_trading_window(now: Optional[datetime] = None) -> bool:
        """判断当前是否处于 A 股交易日 09:20~15:00（按 Asia/Shanghai 本地时间）。"""
        from zoneinfo import ZoneInfo

        now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        if now.weekday() >= 5:  # 周六/周日
            return False
        t = now.time()
        return time(9, 20) <= t <= time(15, 0)

    # ---- 单段执行（可独立调用 / 测试） ----
    def run_segment(
        self,
        segment: str,
        dry_run: bool = False,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        执行指定时段的闭环逻辑。

        Args:
            segment: overnight / premarket / intraday / postmarket / evening / archive
            dry_run: True 时不落库，仅返回摘要（测试与手动触发用）
            symbols: 覆盖默认标的列表
        """
        spec = SEGMENTS.get(segment)
        if spec is None:
            raise ValueError(f"未知时段: {segment}，可选: {list(SEGMENTS)}")

        summary: Dict[str, Any] = {
            "segment": segment,
            "desc": spec["desc"],
            "triggered_at": datetime.now().isoformat(),
            "dry_run": dry_run,
        }

        # 盘中段：非交易时段直接跳过
        if segment == "intraday" and not self.in_trading_window():
            summary["skipped"] = True
            summary["reason"] = "non_trading_window"
            self._last_summaries[segment] = summary
            return summary

        syms = symbols if symbols is not None else self.symbols
        cycles = spec["cycles"]

        # 归档段：无预测，仅汇总
        if not cycles:
            summary["signals"] = 0
            summary["note"] = "归档/推送段，无新预测"
            self._last_summaries[segment] = summary
            return summary

        if not syms:
            summary["signals"] = 0
            summary["note"] = "未配置标的，跳过预测"
            self._last_summaries[segment] = summary
            return summary

        pipeline = ForecastPipeline()
        rows = pipeline.run_batch(
            syms,
            market=self.market,
            cycles=cycles,
            mode=self.mode,
            segment=segment,
        )
        summary["signals"] = len(rows)

        if dry_run:
            summary["persisted"] = 0
            summary["note"] = "dry_run，未落库"
        else:
            try:
                from src.storage import DatabaseManager
                db = DatabaseManager.get_instance()
                with db.session_scope() as session:
                    pipeline.persist_signals(rows, session)
                summary["persisted"] = len(rows)
            except Exception as exc:  # 持久化失败不应杀死调度线程
                logger.warning("[%s] 信号持久化失败（已跳过）: %s", segment, exc)
                summary["persist_error"] = str(exc)
                summary["persisted"] = 0

        self._last_summaries[segment] = summary
        return summary

    # ---- 调度器生命周期 ----
    def build_scheduler(self) -> "BackgroundScheduler":
        if not _HAS_APSCHEDULER:
            raise RuntimeError(
                "apscheduler 未安装，请执行: pip install apscheduler（或加入 requirements.txt）"
            )
        scheduler = BackgroundScheduler(timezone=self.timezone)
        for name, spec in SEGMENTS.items():
            if spec["trigger"] == "cron":
                trigger = CronTrigger.from_crontab(spec["expr"])
            else:
                trigger = IntervalTrigger(seconds=spec["seconds"])
            scheduler.add_job(
                self._job_wrapper,
                trigger,
                args=[name],
                id=f"dsa_daily_{name}",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300,
            )
        return scheduler

    def _job_wrapper(self, segment: str) -> None:
        try:
            logger.info("[每日闭环] 触发时段 %s: %s", segment, SEGMENTS[segment]["desc"])
            summary = self.run_segment(segment, dry_run=False)
            logger.info(
                "[每日闭环] 时段 %s 完成，信号数=%s 落库=%s",
                segment, summary.get("signals"), summary.get("persisted"),
            )
        except Exception as exc:  # 单段失败不影响其他段
            logger.exception("[每日闭环] 时段 %s 执行异常: %s", segment, exc)

    def start(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            return
        self._scheduler = self.build_scheduler()
        self._scheduler.start()
        logger.info("[每日闭环] APScheduler 已启动，共 %d 个时段任务", len(SEGMENTS))

    def stop(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._scheduler = None
        logger.info("[每日闭环] APScheduler 已停止")

    def status(self) -> Dict[str, Any]:
        jobs = []
        if self._scheduler is not None and self._scheduler.running:
            for job in self._scheduler.get_jobs():
                jobs.append({
                    "id": job.id,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                })
        return {
            "enabled": self._scheduler is not None and self._scheduler.running,
            "timezone": self.timezone,
            "symbols": self.symbols,
            "mode": self.mode,
            "jobs": jobs,
            "last_summaries": self._last_summaries,
        }

    # ---- 手动触发（运维接口 / 调试） ----
    def trigger_now(self, segment: str, dry_run: bool = False) -> Dict[str, Any]:
        return self.run_segment(segment, dry_run=dry_run)
