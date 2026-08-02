# -*- coding: utf-8 -*-
"""
==================================================
定时任务注册表 — src/services/job_registry.py
==================================================
为「运维后台定时任务可视化」（设计 §4.2 六段可视化之一）提供
可读的任务清单 + 启停状态 + 上次/下次运行时间。

任务来源：
  - DSA-CRAWL-LLM-MERGE-V1.0 定义的爬虫+解析自动任务（07:50 / 15:40 / 17:30 / 周日19:30）
  - 主分析流水线（来自 config.schedule_times，缺省 18:00）
  - 事件监控后台任务（agent_event_monitor，若启用）

设计原则：独立、无重型依赖（不直接 import runtime_scheduler），状态持久化到
data/scheduler_jobs.json，便于验证脚本隔离加载。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "scheduler_jobs.json",
)


def _next_run_daily(hhmm: str, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def _next_run_weekly(dow: int, hhmm: str, now: Optional[datetime] = None) -> str:
    """dow: 0=周一 .. 6=周日"""
    now = now or datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    days_ahead = (dow - now.weekday()) % 7
    if days_ahead == 0:
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            days_ahead = 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=h, minute=m, second=0, microsecond=0
    )
    return candidate.isoformat()


def compute_next_run(trigger: Dict[str, Any], now: Optional[datetime] = None) -> Optional[str]:
    kind = trigger.get("kind")
    try:
        if kind == "daily":
            return _next_run_daily(trigger["time"], now)
        if kind == "weekly":
            return _next_run_weekly(int(trigger["dow"]), trigger["time"], now)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[JobRegistry] 计算 next_run 失败: %s", exc)
    return None


# 默认任务定义（与 DSA-CRAWL-LLM-MERGE-V1.0 时序对齐）
DEFAULT_JOBS: List[Dict[str, Any]] = [
    {
        "id": "daily_analysis",
        "name": "每日主分析流水线",
        "group": "core",
        "trigger": {"kind": "daily", "time": "18:00"},
        "description": "抓取-入库-推演-预测-复盘全自动闭环",
    },
    {
        "id": "crawl_morning_meeting",
        "name": "晨会纪要爬虫",
        "group": "crawl",
        "trigger": {"kind": "daily", "time": "07:50"},
        "description": "抓取券商晨会纪要并推送解析",
    },
    {
        "id": "crawl_postclose_report",
        "name": "盘后调研纪要/公告爬虫",
        "group": "crawl",
        "trigger": {"kind": "daily", "time": "15:40"},
        "description": "收盘后抓取上市公司公告、调研纪要并即时解析",
    },
    {
        "id": "crawl_evening_announcement",
        "name": "晚间公告/招股书爬虫",
        "group": "crawl",
        "trigger": {"kind": "daily", "time": "17:30"},
        "description": "抓取当日晚间公告、招股说明书并深度解析",
    },
    {
        "id": "weekly_report_compare",
        "name": "周报多文档交叉对比",
        "group": "crawl",
        "trigger": {"kind": "weekly", "dow": 6, "time": "19:30"},
        "description": "周日汇总一周行业研报，批量交叉对比更新中长期预判",
    },
    {
        "id": "agent_event_monitor",
        "name": "事件监控后台任务",
        "group": "monitor",
        "trigger": {"kind": "interval", "seconds": 300},
        "description": "分钟级轮询重大事件并触发预警",
    },
]


class JobRegistry:
    """定时任务注册表（内存 + JSON 持久化）。"""

    def __init__(self, state_path: str = DEFAULT_STATE_PATH):
        self._state_path = state_path
        self._lock = threading.RLock()
        self._state: Dict[str, Any] = {"jobs": {}, "runtime": {}}
        self._load()

    # ---- 持久化 ----
    def _load(self) -> None:
        try:
            if os.path.exists(self._state_path):
                with open(self._state_path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[JobRegistry] 读取状态失败，使用默认: %s", exc)
            self._state = {"jobs": {}, "runtime": {}}
        self._state.setdefault("jobs", {})
        self._state.setdefault("runtime", {})

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[JobRegistry] 写入状态失败: %s", exc)

    # ---- 查询 ----
    def list_jobs(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        now = now or datetime.now()
        out: List[Dict[str, Any]] = []
        for defn in DEFAULT_JOBS:
            jid = defn["id"]
            saved = self._state["jobs"].get(jid, {})
            enabled = saved.get("enabled", True)
            trigger = defn["trigger"]
            next_run = compute_next_run(trigger, now) if enabled else None
            out.append({
                "id": jid,
                "name": defn["name"],
                "group": defn["group"],
                "description": defn["description"],
                "trigger": trigger,
                "trigger_label": self._trigger_label(trigger),
                "enabled": enabled,
                "last_run_at": saved.get("last_run_at"),
                "last_status": saved.get("last_status"),
                "next_run_at": next_run,
                "run_count": int(saved.get("run_count", 0)),
            })
        return out

    @staticmethod
    def _trigger_label(trigger: Dict[str, Any]) -> str:
        kind = trigger.get("kind")
        if kind == "daily":
            return f"每日 {trigger.get('time')}"
        if kind == "weekly":
            wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][int(trigger.get("dow", 0))]
            return f"每周{wd} {trigger.get('time')}"
        if kind == "interval":
            sec = int(trigger.get("seconds", 300))
            return f"每 {sec // 60} 分钟" if sec >= 60 else f"每 {sec} 秒"
        return "未知"

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        for j in self.list_jobs():
            if j["id"] == job_id:
                return j
        return None

    # ---- 变更 ----
    def set_enabled(self, job_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        with self._lock:
            saved = self._state["jobs"].setdefault(job_id, {})
            saved["enabled"] = bool(enabled)
            self._save()
        return self.get_job(job_id)

    def record_run(self, job_id: str, status: str = "success") -> None:
        with self._lock:
            saved = self._state["jobs"].setdefault(job_id, {})
            saved["last_run_at"] = datetime.now().isoformat()
            saved["last_status"] = status
            saved["run_count"] = int(saved.get("run_count", 0)) + 1
            self._save()

    def set_runtime_status(self, status: Dict[str, Any]) -> None:
        with self._lock:
            self._state["runtime"] = status
            self._save()

    def get_runtime_status(self) -> Dict[str, Any]:
        return self._state.get("runtime", {})


# 全局单例
_registry_instance: Optional[JobRegistry] = None


def get_job_registry() -> JobRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = JobRegistry()
    return _registry_instance


__all__ = ["JobRegistry", "get_job_registry", "DEFAULT_JOBS"]
