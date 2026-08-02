# -*- coding: utf-8 -*-
"""
==================================================
长文本深度解析 API — api/v1/endpoints/llm_parse.py
==================================================
设计文档: DSA-OPT-LLM-001 / DSA-CRAWL-LLM-MERGE-V1.0

端点（统一前缀 /api/v1/llm-parse）:
  POST /document    单文档分层拆解 + 约束挖掘 + 长期规划 + 隐性风险
  POST /compare     多文档交叉对比（2~10 份）
  POST /constraints 隐藏约束挖掘
  POST /long-term   长期规划提取
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.llm_parse_service import DOC_TYPES, VALID_MODES, get_llm_parse_service

router = APIRouter()


# ---- 请求体 ----
class ParseDocumentRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待解析文本")
    doc_type: str = Field("other", description="文档类型: policy/broker_report/prospectus/meeting_minutes/industry_white_paper/other")
    mode: str = Field("deep", description="解析模式: fast(本地轻量)/deep(API精读)")


class CompareDocumentItem(BaseModel):
    title: str = ""
    text: str = Field(..., min_length=1)


class CompareRequest(BaseModel):
    documents: List[CompareDocumentItem] = Field(..., min_length=1, max_length=10)


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1)


class LongTermRequest(BaseModel):
    text: str = Field(..., min_length=1)


def _envelope(payload: Dict[str, Any]):
    """将 service 返回的 {code,msg,data} 转 HTTP 响应；业务错误码透传。"""
    if payload.get("code") not in (0, None):
        return payload
    return payload


@router.post("/document")
def parse_document(req: ParseDocumentRequest):
    if req.doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type 必须是 {sorted(DOC_TYPES)} 之一")
    if req.mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode 必须是 {sorted(VALID_MODES)} 之一")
    svc = get_llm_parse_service()
    return _envelope(svc.parse_document(text=req.text, doc_type=req.doc_type, mode=req.mode))


@router.post("/compare")
def compare_documents(req: CompareRequest):
    svc = get_llm_parse_service()
    docs = [{"title": d.title, "text": d.text} for d in req.documents]
    return _envelope(svc.compare_documents(docs))


@router.post("/constraints")
def mine_constraints(req: TextRequest):
    svc = get_llm_parse_service()
    return _envelope(svc.mine_constraints(req.text))


@router.post("/long-term")
def extract_long_term(req: LongTermRequest):
    svc = get_llm_parse_service()
    return _envelope(svc.extract_long_term_plan(req.text))
