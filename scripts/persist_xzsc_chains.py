#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将《新质生产力解析：全景图+58大产业链图谱》梳理后的 58 条产业链
持久化到本地 SQLite 数据层（data/stock_analysis.db，表 xzsc_industry_chain）。

用法（项目根目录执行）：
    .venv/bin/python scripts/persist_xzsc_chains.py

特性：
- 幂等：按 `no` 主键 upsert，重复执行安全。
- 复用项目 DatabaseManager（含 WAL / busy_timeout / 重试），与运行中的后端同库同连接配置。
- 自动建表：XzscIndustryChain 模型已注册到 Base.metadata，create_all 即建表。
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.storage import Base, DatabaseManager, XzscIndustryChain
from src.data.xzsc_chain import XZSC_CHAINS, SOURCE_NAME, SOURCE_URL


def main() -> None:
    db = DatabaseManager()          # 单例；首次触发 Base.metadata.create_all
    Base.metadata.create_all(db._engine)  # 确保 xzsc_industry_chain 已建表

    rows = []
    for c in XZSC_CHAINS:
        rows.append({
            "no": c["no"],
            "name": c["name"],
            "l1": c["l1"],
            "l2": c["l2"],
            "summary": c["summary"],
            "segments": json.dumps(c["segments"], ensure_ascii=False),
            "source_name": SOURCE_NAME,
            "source_url": SOURCE_URL,
            "created_at": datetime.now(),
        })

    with db.session_scope() as session:
        stmt = sqlite_insert(XzscIndustryChain).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[XzscIndustryChain.no],
            set_={
                "name": stmt.excluded.name,
                "l1": stmt.excluded.l1,
                "l2": stmt.excluded.l2,
                "summary": stmt.excluded.summary,
                "segments": stmt.excluded.segments,
                "source_name": stmt.excluded.source_name,
                "source_url": stmt.excluded.source_url,
                "created_at": stmt.excluded.created_at,
            },
        )
        session.execute(stmt)

    # 校验
    with db.session_scope() as session:
        total = session.scalar(select(func.count()).select_from(XzscIndustryChain))
        l1_counter: Counter = Counter()
        for l1 in session.scalars(select(XzscIndustryChain.l1)):
            l1_counter[l1] += 1

    print(f"OK: xzsc_industry_chain 现共 {total} 条（本次写入/更新 {len(rows)} 条）")
    print("按一级赛道分布：")
    for l1, cnt in l1_counter.items():
        print(f"  - {l1}: {cnt}")


if __name__ == "__main__":
    main()
