---
date: 2026-08-01
requirement: P0-② 自动因子挖掘闭环（借鉴 Qlib + RD-Agent）
status: done
tags: [p0, factor-mining, alpha, rd-agent, qlib, auto-ml]
---

# P0-② 自动因子挖掘闭环

## 需求背景
差距分析指出本系统有静态 Alpha158 因子，但缺 RD-Agent / Qlib 式「自动因子挖掘闭环」
（生成候选 → 回测/IC 验证 → 自动迭代淘汰 → 保留最优）。需补齐该自迭代能力。

## 实现（已落地）
1. **存储模型** `src/storage.py` 新增 `FactorMiningResult` 表：generation / factor_name /
   factor_expr / ic / rank_ic / icir / long_short_return / sharpe / turnover / source / is_active。

2. **闭环引擎** `src/factor_mining.py`：
   - 基础池：`AlphaLibrary` 量价/动量/波动/RSI 因子（ret_1d/5d/20d, ma_gap, ma_cross, vol_20d, rsi_14d）。
   - 进化：对上一代 Top-K 与基础因子做代数组合（加/减/乘/除）生成新候选（`_evolve`）。
   - 评估：`_evaluate` 用 Spearman IC、RankIC、多空年化收益、夏普、换手。
   - 闭环 `mine()`：逐代评估→保留 Top-K 作种子→下一代进化→持久化每代结果→全局最优标 is_active=1。
   - **可插拔数据**：联网 akshare `stock_zh_a_hist` 真实日线；离线/失败降级合成随机游走（标注 online=false），
     保证闭环离线可演示、联网即真实。

3. **触发脚本** `scripts/run_factor_mining.py`：
   `python -m scripts.run_factor_mining [code] [--online] [--gen N] [--top K]`

4. **API** `api/v1/endpoints/factor_mining.py` + router 注册：
   - `POST /api/v1/factor-mining/run?code=&max_gen=&top_k=&online=`
   - `GET  /api/v1/factor-mining/results?generation=&active_only=`

## 验证
- CLI：`python -m scripts.run_factor_mining 600519 --gen 4 --top 5` → active=5，最优因子
  含进化组合 `(ret_1d)/(np.abs(ret_20d)+1e-6)`(ic=0.152, lsr=220%) 等。
- API：POST 返回 active_count=5；GET active_only 返回 5 条 is_active=1 因子。
- 修复：后端 session_scope `autoflush=False` 导致 query 看不到未 flush 的 add → 在查询前显式 `s.flush()`
  并在标记最优前 `UPDATE is_active=0` 重置（避免历史 active 残留）。

## 备注
- 离线合成数据为随机游走，IC/收益为伪信号，仅验证闭环逻辑；联网 `--online` 用真实日线才有意义。
- 当前为「符号组合进化」（非 LLM 生成）。RD-Agent 的 LLM 因子生成可作为后续增强（若 LLM 可用）。
- 多股票/面板数据 ICIR 时序统计为 proxy（单序列 IC），后续可扩展为多标的截面。
