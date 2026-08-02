# -*- coding: utf-8 -*-
"""
===================================
DSA 每日自动闭环 独立运行 / 手动触发 CLI
===================================

用法：
  # 仅手动触发某一段（dry-run，不落库），便于验证与调试
  python scripts/run_daily_loop.py --symbols 600519,000001 --dry-run-once evening

  # 以 APScheduler 常驻运行六段闭环（等价于在 API 生命周期内启动）
  python scripts/run_daily_loop.py --symbols 600519,000001 --serve

环境变量（与 api.app 生命周期保持一致）：
  DSA_DAILY_LOOP_SYMBOLS / DSA_DAILY_LOOP_MODE / DSA_DAILY_LOOP_MARKET
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# 让脚本在「从任意目录调用」时也能导入项目顶层包（src / core / api）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s",
)
logger = logging.getLogger("dsa_daily_loop_cli")


def _parse_symbols(raw: str) -> list:
    return [s.strip() for s in (raw or "").split(",") if s.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DSA 每日自动闭环调度（APScheduler）")
    parser.add_argument("--symbols", default="", help="逗号分隔的标的代码列表")
    parser.add_argument("--market", default="A", help="市场: A / HK / US")
    parser.add_argument("--mode", default="synthetic", help="synthetic | live")
    parser.add_argument(
        "--dry-run-once",
        default=None,
        metavar="SEGMENT",
        help="手动触发单段(dry-run 不落库): overnight/premarket/intraday/"
             "postmarket/evening/archive",
    )
    parser.add_argument("--serve", action="store_true", help="常驻运行六段闭环")
    args = parser.parse_args(argv)

    from src.daily_loop import ApschedulerDailyLoop

    symbols = _parse_symbols(args.symbols)
    loop = ApschedulerDailyLoop(
        symbols=symbols or None, market=args.market, mode=args.mode
    )

    if args.dry_run_once:
        summary = loop.run_segment(args.dry_run_once, dry_run=True)
        logger.info("执行摘要:\n%s", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.serve:
        loop.start()
        logger.info("每日闭环已常驻运行，按 Ctrl+C 退出")
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            loop.stop()
            logger.info("已停止")
        return 0

    # 默认：打印状态并退出（不常驻）
    logger.info("未指定 --serve / --dry-run-once，仅打印当前配置状态")
    logger.info("status: %s", json.dumps(loop.status(), ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
