# -*- coding: utf-8 -*-
"""MCP 工具清单 REST 端点（P0-③ 对齐层）。

GET /api/v1/mcp/manifest  返回本系统暴露给外部 Agent 的 MCP 工具清单。
实际 MCP 服务通过 `python -m mcp.server`（stdio）启动，本端点仅为 Web/Agent 发现用。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from mcp.tools_spec import TOOLS

router = APIRouter()


@router.get("/mcp/manifest")
def mcp_manifest() -> Dict[str, Any]:
    """返回 MCP 工具清单与接入说明。"""
    return {
        "server": "dsa-mcp",
        "version": "1.0.0",
        "transport": "stdio (JSON-RPC 2.0)",
        "launch": "python -m mcp.server",
        "base_url": "http://127.0.0.1:8000/api/v1",
        "tools": TOOLS,
        "note": "外部 Agent（Claude Desktop / Cursor / 自研 Agent）通过 stdio 启动本进程即可调用上述工具，"
                "对标 2026 年 Wind/同花顺的 Agent 开放生态。",
    }
