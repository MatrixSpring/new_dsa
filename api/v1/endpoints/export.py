# -*- coding: utf-8 -*-
"""Excel / 报告导出接口 (P2-③)。

- POST /export/portfolio-xlsx   生成并下载 xlsx 投资分析报告（组合优化+风险归因+候选画像+因子）
- POST /export/portfolio-report  返回同样的报告 JSON（便于前端预览/二次处理）
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from src.export_excel import build_portfolio_report, export_report_xlsx

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/portfolio-report")
def portfolio_report_json(
    symbols: List[str] = Body(..., description="标的代码列表"),
    objective: str = Body("max_sharpe", description="max_sharpe / min_variance"),
    risk_parity_mode: bool = Body(False, description="True 时返回风险平价权重"),
    online: bool = Body(False, description="是否用真实日线估计"),
    window: int = Body(120, description="估计窗口"),
    rf: float = Body(0.02, description="无风险利率"),
) -> Dict[str, Any]:
    """返回组合分析报告 JSON（不落盘）。"""
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols 不能为空")
    try:
        return build_portfolio_report(
            symbols=symbols, objective=objective, risk_parity_mode=risk_parity_mode,
            online=online, window=window, rf=rf,
        )
    except Exception as exc:  # noqa: BLE001 — 结构化错误返回，附完整栈
        logger.error("Export report 生成失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"报告生成失败: {exc}") from exc


@router.post("/portfolio-xlsx")
def portfolio_xlsx(
    symbols: List[str] = Body(..., description="标的代码列表"),
    objective: str = Body("max_sharpe", description="max_sharpe / min_variance"),
    risk_parity_mode: bool = Body(False, description="True 时返回风险平价权重"),
    online: bool = Body(False, description="是否用真实日线估计"),
    window: int = Body(120, description="估计窗口"),
    rf: float = Body(0.02, description="无风险利率"),
) -> FileResponse:
    """生成 xlsx 投资分析报告并下载。"""
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols 不能为空")
    try:
        report = build_portfolio_report(
            symbols=symbols, objective=objective, risk_parity_mode=risk_parity_mode,
            online=online, window=window, rf=rf,
        )
        if "error" in report:
            raise HTTPException(status_code=400, detail=report["error"])
        path = export_report_xlsx(report)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — 结构化错误返回，附完整栈
        logger.error("Export xlsx 生成失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"xlsx 生成失败: {exc}") from exc
    return FileResponse(
        path,
        filename=os.path.basename(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=None,
    )
