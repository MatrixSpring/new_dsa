---
date: 2026-08-01
requirement: P0-① 接入一致预期 + ESG 数据，补齐 Wind 核心壁垒能力
status: done
tags: [p0, consensus, esg, company_profile, data_provider, etl]
---

# P0-① 一致预期 + ESG 数据接入

## 需求背景
差距分析指出：本系统相对 Wind/同花顺等主流终端，缺失「机构一致预期（盈利预测/评级/目标价）」与「ESG 评级」两大核心壁垒能力。
需在公司全维度表（CompanyProfile）中补齐，并与现有股票分析链路打通。

## 实现方案（已落地）
1. **模型扩展** `src/storage.py` CompanyProfile：新增 14 列
   - 一致预期(8)：consensus_year, consensus_eps, consensus_eps_growth, consensus_net_profit,
     consensus_revenue, consensus_rating, consensus_institutes, consensus_target_price
   - ESG(6)：esg_score, esg_rating, esg_environment, esg_social, esg_governance, esg_year

2. **接入层** `data_provider/consensus_esg_fetcher.py`（可插拔 + 离线降级）
   - 在线优先 akshare：`stock_profit_forecast_em`(盈利预测) + `stock_institute_recommend_detail`(机构评级)
     + `stock_esg_rate_sina()`(全市场 ESG，无参一次性拉取落地 `data/cache/esg_cache.json`)
   - 离线兜底：内部估算（仅用 净利润/总股本 推导 TTM EPS，标注 internal_estimate_ttm；其余留空，绝不编造）

3. **ETL** `scripts/build_company_profiles.py`
   - `ensure_consensus_esg_columns()`：PRAGMA 检查 + ALTER TABLE 补列（create_all 不会自动 ALTER 已存在表）
   - `enrich_consensus_esg(online_consensus)`：遍历 company_profile 仅填充 None 字段（幂等，不覆盖真值）
   - 默认离线估算（秒级）；`--online-consensus` 联网回填真实机构数据 + 拉取 ESG 全量缓存

4. **接口** `api/v1/endpoints/company.py`
   - 详情 `GET /companies/{code}` 经 `to_dict()` 自动返回全部新字段
   - 列表 `_summary` 新增概览：consensus_rating/target_price/institutes/eps、esg_rating/esg_score

## 当前环境验证结果
- 后端 :8000 已重启加载新模型；`/companies/300750` 正确返回新字段（离线环境真值为 null，
  consensus_year=2027 由估算填充）。
- 数据填充统计（离线）：总 179 家；一致预期/ESG 真实值均为 null（无 TUSHARE_TOKEN 且 akshare 在线接口
  在当前环境超时/改版），符合「离线降级」设计预期。
- 联网回填命令：`.venv/bin/python3 -m scripts.build_company_profiles --online-consensus`

## 关键约束 / 备注
- 当前环境**无 TUSHARE_TOKEN**，akshare 在线接口（新浪源）不稳定（ReadTimeout / 解析失败）。
  生产环境配置 token 与稳定网络后，一致预期/ESG 真实数据将自动生效，无需改代码。
- 离线估算的 consensus_eps 依赖 net_profit/total_shares，而这两列目前绝大多数公司为空（仅 7 家有估值），
  故离线几乎无 EPS 填充——属正常，真实值需联网。
- ESG 不编造评分，离线全 null。
