# -*- coding: utf-8 -*-
"""自动爬虫 + 长文本解析流水线 P0 端点（外挂，不改 DSA 内核）。

端点：
- GET  /api/v1/crawl/sources          列出可配置抓取源
- POST /api/v1/crawl/run              运行单源：抓取 → 解析 → 入库
- GET  /api/v1/crawl/documents        已抓取并解析的文档列表（含结构化结果）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body

from src.services.crawl_service import list_documents, list_sources, run_crawl_and_parse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/sources')
def get_sources() -> Dict[str, Any]:
    """列出可配置抓取源及其适配器类型。"""
    return {'code': 0, 'msg': 'ok', 'data': list_sources()}


@router.post('/run')
def run_crawl(source_key: str = Body(..., embed=True)) -> Dict[str, Any]:
    """运行单源全链路：抓取 → LLM 结构化解析 → 入库。"""
    return run_crawl_and_parse(source_key)


@router.get('/documents')
def get_documents(limit: int = 50, status: Optional[str] = None) -> Dict[str, Any]:
    """已抓取文档列表（含解析结果摘要）。"""
    return list_documents(limit=limit, status=status)
