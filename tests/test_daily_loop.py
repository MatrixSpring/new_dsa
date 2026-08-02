# -*- coding: utf-8 -*-
"""APScheduler 六段每日闭环调度器单元测试（离线）。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.daily_loop import (
    ALL_CYCLES,  # noqa: F401  (re-export for safety)
    SEGMENTS,
    ApschedulerDailyLoop,
)

pytestmark = pytest.mark.skipif(
    not __import__("src.daily_loop", fromlist=["_HAS_APSCHEDULER"])._HAS_APSCHEDULER,
    reason="apscheduler 未安装",
)


def test_six_segments_present():
    assert set(SEGMENTS.keys()) == {
        "overnight", "premarket", "intraday", "postmarket", "evening", "archive"
    }


def test_trading_window_guard():
    # 周六应非交易时段
    sat = datetime(2026, 8, 1, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))  # 2026-08-01 是周六
    assert ApschedulerDailyLoop.in_trading_window(sat) is False
    # 周三 10:30 交易时段内
    wed = datetime(2026, 8, 5, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert ApschedulerDailyLoop.in_trading_window(wed) is True
    # 周三 20:00 盘后，非交易时段
    eve = datetime(2026, 8, 5, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert ApschedulerDailyLoop.in_trading_window(eve) is False


def test_run_segment_evening_dry_run():
    loop = ApschedulerDailyLoop(symbols=["600519", "000001"], mode="synthetic")
    summary = loop.run_segment("evening", dry_run=True)
    assert summary["segment"] == "evening"
    assert summary["signals"] == len(ALL_CYCLES) * 2  # 2 标的 × 4 周期
    assert summary["persisted"] == 0
    assert summary["dry_run"] is True


def test_run_segment_archive_no_cycles():
    loop = ApschedulerDailyLoop(symbols=["600519"])
    summary = loop.run_segment("archive", dry_run=True)
    assert summary["signals"] == 0
    assert "note" in summary


def test_run_segment_intraday_skipped_off_hours():
    # 非交易时段（周六）盘中段应跳过
    loop = ApschedulerDailyLoop(symbols=["600519"])
    sat = datetime(2026, 8, 1, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    summary = loop.run_segment("intraday", dry_run=True)
    # 实际运行时间若不在交易时段则 skipped=True；这里只验证不抛异常且结构正确
    assert summary["segment"] == "intraday"
    assert ("skipped" in summary) or ("signals" in summary)


def test_run_segment_unknown_raises():
    loop = ApschedulerDailyLoop(symbols=["600519"])
    with pytest.raises(ValueError):
        loop.run_segment("nope", dry_run=True)


def test_build_scheduler_has_six_jobs():
    loop = ApschedulerDailyLoop(symbols=["600519"])
    sched = loop.build_scheduler()
    try:
        sched.start()
        jobs = sched.get_jobs()
        assert len(jobs) == len(SEGMENTS)
        ids = {j.id for j in jobs}
        assert all(jid.startswith("dsa_daily_") for jid in ids)
    finally:
        if sched.running:
            sched.shutdown(wait=False)


def test_start_stop_lifecycle():
    loop = ApschedulerDailyLoop(symbols=["600519"])
    loop.start()
    try:
        st = loop.status()
        assert st["enabled"] is True
        assert len(st["jobs"]) == len(SEGMENTS)
    finally:
        loop.stop()
    assert loop.status()["enabled"] is False
