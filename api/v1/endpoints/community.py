# -*- coding: utf-8 -*-
"""社区 / 分享层接口 (P2-④)。

帖子 CRUD + 评论 + 点赞（去重）+ 统计。自包含 SQLite（data/community.db）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query

from src import community as community_svc

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats")
def get_stats() -> Dict[str, Any]:
    """社区总览统计。"""
    return community_svc.stats()


@router.post("/posts")
def create_post(
    author: str = Body("匿名", description="作者"),
    title: str = Body(..., description="标题"),
    body: str = Body("", description="正文"),
    tags: Optional[List[str]] = Body(None, description="标签列表"),
) -> Dict[str, Any]:
    """发布帖子。"""
    if not title or not title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")
    return community_svc.create_post(author=author, title=title,
                                     body=body, tags=tags)


@router.get("/posts")
def list_posts(
    tag: Optional[str] = Query(None, description="按标签筛选"),
    sort: str = Query("new", description="new=最新 / hot=最热"),
    limit: int = Query(50, description="返回条数上限"),
    offset: int = Query(0, description="偏移"),
) -> List[Dict[str, Any]]:
    """帖子列表。"""
    return community_svc.list_posts(tag=tag, sort=sort, limit=limit, offset=offset)


@router.get("/posts/{post_id}")
def get_post(
    post_id: int = Path(..., description="帖子 id"),
) -> Dict[str, Any]:
    """帖子详情（含评论）。"""
    p = community_svc.get_post(post_id)
    if not p:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return p


@router.post("/posts/{post_id}/comments")
def add_comment(
    post_id: int = Path(..., description="帖子 id"),
    author: str = Body("匿名", description="评论者"),
    body: str = Body(..., description="评论内容"),
) -> Dict[str, Any]:
    """给帖子添加评论。"""
    if not body or not body.strip():
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    res = community_svc.add_comment(post_id=post_id, author=author, body=body)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res


@router.post("/posts/{post_id}/like")
def like_post(
    post_id: int = Path(..., description="帖子 id"),
    user_name: Optional[str] = Query(None, description="点赞用户(URL 查询参数, 推荐)"),
    body: Optional[Dict[str, Any]] = Body(None, description="可选 JSON 兼容: {\"user_name\": \"alice\"}"),
) -> Dict[str, Any]:
    """点赞 / 取消点赞（同一 user_name 幂等）。

    兼容两种调用:
    - 推荐: POST /posts/{id}/like?user_name=alice （无请求体）
    - 兼容: POST /posts/{id}/like  Body {"user_name":"alice"}
    """
    if user_name is None and body and isinstance(body, dict) and body.get("user_name"):
        user_name = body["user_name"]
    res = community_svc.toggle_like(post_id=post_id, user_name=user_name)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res
