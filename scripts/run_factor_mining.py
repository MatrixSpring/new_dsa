# -*- coding: utf-8 -*-
"""运行自动因子挖掘闭环 (P0-②)。

用法:
  python -m scripts.run_factor_mining [code] [--online] [--gen N] [--top K]

默认离线(合成数据演示闭环)；--online 联网用 akshare 真实日线评估。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.factor_mining import mine  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", default="600519", help="股票代码(6位)")
    ap.add_argument("--online", action="store_true", help="联网用真实日线评估(默认离线合成)")
    ap.add_argument("--gen", type=int, default=4, help="进化代次")
    ap.add_argument("--top", type=int, default=5, help="每代保留 Top-K")
    args = ap.parse_args()

    res = mine(code=args.code, online=args.online, max_gen=args.gen, top_k=args.top)
    print("=== 自动因子挖掘闭环完成 ===")
    print(f"  code={res['code']} online={res['online']} generations={res['generations']} "
          f"top_k={res['top_k']} active={res['active_count']}")
    print("  全局最优因子:")
    for b in res["best"]:
        print(f"    - {b['name']:12s} ic={b['ic']:.4f} lsr={b['long_short_return']:.2f}% "
              f"src={b['source']} expr={b['expr']}")


if __name__ == "__main__":
    main()
