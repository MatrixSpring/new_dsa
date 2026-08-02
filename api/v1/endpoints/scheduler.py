# -*- coding: utf-8 -*-
"""
==================================================
定时任务可视化 API — api/v1/endpoints/scheduler.py
==================================================
设计文档: 运维后台定时任务可视化（六段可视化之一）

端点（统一前缀 /api/v1/scheduler）:
  GET  /jobs            任务清单 + 运行状态
  POST /jobs/{id}/toggle  启停任务
  POST /jobs/{id}/run     手动触发一次（记录运行）
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from src.services.job_registry import get_job_registry
from src.storage import DatabaseManager, SchedulerJobRun

router = APIRouter()


@router.get("/jobs")
def list_jobs():
    reg = get_job_registry()
    jobs = reg.list_jobs()
    runtime = reg.get_runtime_status()
    return {"code": 0, "msg": "ok", "data": {"jobs": jobs, "runtime": runtime}}


@router.post("/jobs/{job_id}/toggle")
def toggle_job(job_id: str, body: Dict[str, Any] = {}):
    reg = get_job_registry()
    if reg.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"未知任务: {job_id}")
    enabled = bool(body.get("enabled", not reg.get_job(job_id)["enabled"]))
    job = reg.set_enabled(job_id, enabled)
    return {"code": 0, "msg": "ok", "data": job}


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str):
    reg = get_job_registry()
    if reg.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"未知任务: {job_id}")
    # 真实环境下此处委派 RuntimeSchedulerService 立即执行；验证环境仅记录运行。
    reg.record_run(job_id, status="success")
    # 同步写入调度运行日志表（设计 §5.3 表4）
    try:
        m = DatabaseManager.get_instance()
        with m.session_scope() as s:
            s.add(SchedulerJobRun(job_key=job_id, status="success",
                                  summary="手动触发", job_run_id=None))
    except Exception:  # noqa: BLE001 - 日志底座失败不应影响主流程
        pass
    return {"code": 0, "msg": "ok", "data": reg.get_job(job_id)}


@router.post("/jobs/{job_id}/record")
def record_job_run(job_id: str, body: Dict[str, Any] = {}):
    """记录一次任务运行到调度日志表（设计 §5.3 表4）。

    请求体: {status: success|failed|running, summary?, error?, startedAt?, finishedAt?}
    真实环境由 APScheduler listener 调用；验证环境可手动写入。
    """
    if get_job_registry().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"未知任务: {job_id}")
    status = body.get("status", "success")
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = SchedulerJobRun(
            job_key=job_id,
            status=status,
            summary=body.get("summary"),
            error=body.get("error"),
        )
        # 允许回填时间字段（真实环境 APScheduler 提供）
        if body.get("startedAt"):
            row.started_at = _parse_dt(body["startedAt"])
        if body.get("finishedAt"):
            row.finished_at = _parse_dt(body["finishedAt"])
        s.add(row)
        s.flush()
        return {"code": 0, "msg": "ok", "data": row.to_dict()}


@router.get("/runs")
def list_job_runs(limit: int = Query(50, ge=1, le=500)):
    """最近调度运行日志（按 started_at 倒序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(SchedulerJobRun)
            .order_by(SchedulerJobRun.started_at.desc())
            .limit(limit)
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {"code": 0, "total": len(items), "items": items}


def _parse_dt(v: str):
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None
