# -*- coding: utf-8 -*-
"""社区 / 分享层 (P2-④, 对标掘金/雪球 策略分享社区)。

自包含 SQLite 存储（data/community.db），与主分析库解耦：
  - CommunityPost    ：帖子（标题/正文/标签/作者/点赞数）
  - CommunityComment ：评论
  - CommunityLike    ：点赞记录（按 user_name 去重，避免重复点赞）

所有函数对异常做降级，绝不抛出未捕获异常到接口层。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, create_engine, func,
)
from sqlalchemy.orm import declarative_base, relationship, scoped_session, sessionmaker

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join("data", "community.db")
_engine = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})
_Session = scoped_session(sessionmaker(bind=_engine, autoflush=False))
Base = declarative_base()


class CommunityPost(Base):
    __tablename__ = "community_post"
    id = Column(Integer, primary_key=True, autoincrement=True)
    author = Column(String(64), nullable=False, default="匿名")
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False, default="")
    tags = Column(String(255), nullable=False, default="")  # 逗号分隔
    likes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    comments = relationship(
        "CommunityComment", back_populates="post",
        cascade="all, delete-orphan", lazy="dynamic",
    )


class CommunityComment(Base):
    __tablename__ = "community_comment"
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("community_post.id"), nullable=False)
    author = Column(String(64), nullable=False, default="匿名")
    body = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    post = relationship("CommunityPost", back_populates="comments")


class CommunityLike(Base):
    __tablename__ = "community_like"
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("community_post.id"), nullable=False)
    user_name = Column(String(64), nullable=False, default="anonymous")


def init() -> None:
    """建表（幂等）。"""
    try:
        Base.metadata.create_all(_engine)
    except Exception as exc:  # noqa: BLE001
        logger.warning("community 建表失败: %s", exc)


def _session():
    return _Session()


def create_post(author: str, title: str, body: str,
                tags: Optional[List[str]] = None) -> Dict[str, Any]:
    init()
    try:
        with _session() as s:
            p = CommunityPost(
                author=author or "匿名",
                title=title,
                body=body or "",
                tags=",".join(tags or []),
                likes=0,
            )
            s.add(p)
            s.commit()
            return {"id": p.id, "title": p.title, "author": p.author,
                    "tags": p.tags, "likes": p.likes,
                    "created_at": p.created_at.isoformat()}
    except Exception as exc:  # noqa: BLE001
        logger.error("发帖失败: %s", exc)
        return {"error": str(exc)}


def list_posts(tag: Optional[str] = None, sort: str = "new",
               limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    init()
    try:
        with _session() as s:
            q = s.query(CommunityPost)
            if tag:
                q = q.filter(CommunityPost.tags.like(f"%{tag}%"))
            if sort == "hot":
                q = q.order_by(CommunityPost.likes.desc())
            else:
                q = q.order_by(CommunityPost.created_at.desc())
            rows = q.limit(limit).offset(offset).all()
            return [{
                "id": r.id, "title": r.title, "author": r.author,
                "tags": r.tags, "likes": r.likes,
                "comment_count": r.comments.count(),
                "created_at": r.created_at.isoformat(),
            } for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.error("列帖失败: %s", exc)
        return []


def get_post(post_id: int) -> Optional[Dict[str, Any]]:
    init()
    try:
        with _session() as s:
            p = s.get(CommunityPost, post_id)
            if not p:
                return None
            comments = [{
                "id": c.id, "author": c.author, "body": c.body,
                "created_at": c.created_at.isoformat(),
            } for c in p.comments.order_by(CommunityComment.created_at.asc())]
            return {
                "id": p.id, "title": p.title, "author": p.author,
                "body": p.body, "tags": p.tags, "likes": p.likes,
                "created_at": p.created_at.isoformat(),
                "comments": comments,
            }
    except Exception as exc:  # noqa: BLE001
        logger.error("读帖失败: %s", exc)
        return None


def add_comment(post_id: int, author: str, body: str) -> Dict[str, Any]:
    init()
    try:
        with _session() as s:
            p = s.get(CommunityPost, post_id)
            if not p:
                return {"error": "帖子不存在"}
            c = CommunityComment(
                post_id=post_id, author=author or "匿名", body=body or "")
            s.add(c)
            s.commit()
            return {"id": c.id, "post_id": post_id, "author": c.author,
                    "body": c.body, "created_at": c.created_at.isoformat()}
    except Exception as exc:  # noqa: BLE001
        logger.error("评论失败: %s", exc)
        return {"error": str(exc)}


def toggle_like(post_id: int, user_name: Optional[str] = None) -> Dict[str, Any]:
    init()
    user = user_name or "anonymous"
    try:
        with _session() as s:
            p = s.get(CommunityPost, post_id)
            if not p:
                return {"error": "帖子不存在"}
            existing = s.query(CommunityLike).filter_by(
                post_id=post_id, user_name=user).first()
            if existing:
                s.delete(existing)
                p.likes = max(0, p.likes - 1)
                liked = False
            else:
                s.add(CommunityLike(post_id=post_id, user_name=user))
                p.likes += 1
                liked = True
            s.commit()
            return {"post_id": post_id, "likes": p.likes, "liked": liked}
    except Exception as exc:  # noqa: BLE001
        logger.error("点赞失败: %s", exc)
        return {"error": str(exc)}


def stats() -> Dict[str, Any]:
    init()
    try:
        with _session() as s:
            return {
                "posts": int(s.query(func.count(CommunityPost.id)).scalar() or 0),
                "comments": int(s.query(func.count(CommunityComment.id)).scalar() or 0),
            }
    except Exception as exc:  # noqa: BLE001
        logger.error("社区统计失败: %s", exc)
        return {"posts": 0, "comments": 0}
