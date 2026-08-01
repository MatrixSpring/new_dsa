# 系统差距分析 + 补充方案 + GitHub 开源借鉴（规划类需求）

- 日期：2026-08-01
- 需求：检查当前系统与业界主流股票分析系统的差距，给出补充方案；调研 GitHub 开源股票项目可借鉴功能并给出合并方案
- 状态：分析完成，方案已出（待排期实施）

## 现状基线（代码调研）
- 优势：AI 多 Agent 分析（六 Agent + 共识）、产业链融合（xzsc↔申万 + curated）、新闻→产业链影响传导、CompanyProfile 56 列、回测（vector_bt+core）、15 渠道推送、调度、bot、双前端。
- 短板：周/月线历史未实现、占位行情、data_quality_checker 为桩、forecast 端点未挂载（死代码）、无一致预期/ESG、无金融 RAG、无实盘执行、产业链深度有限。

## 与主流差距（大项）
实时多资产数据、一致预期、ESG、因子自动挖掘、实盘执行、MCP/Agent 开放接口。

## GitHub 可借鉴 + 合并映射
1. ai-hedge-fund 人格化 Agent → 扩展 `src/multi_agent.py`（加价值/成长/宏观/逆向人格 + PM 决策 + 风控），复用 consensus_engine。
2. Qlib + RD-Agent 自动因子挖掘 → 基于 `alpha_factors.py`+`backtest_service` 建「研究循环」微服务（假设→代码→回测→迭代），可选 pip qlib。
3. vnpy/QMT/xtquant → 扩展 `src/brokers/` 接实盘网关（可选，含执行才做）。
4. backtrader → 适配层做事件驱动回测，与 vector_bt 互补。
5. AkShare/TuShare 一致预期&ESG → 扩展 `data_provider`，并入 `CompanyProfile`。
6. ai_quant_trade/StructBERT → 增强 `indicators/sentiment` + 复用 G6 拓扑做图网络策略。
7. QUANTAXIS/Abu → 借鉴调度与策略遗传淘汰。
8. FinRL/ElegantRL → 可选 RL 策略模块。
9. MCP 开放接口（对标 Wind/同花顺）→ 新建 `mcp/` 把 analysis/industry-chain/company/alerts 暴露为 MCP tools。

## 优先级路线
- P0：一致预期+ESG 数据接入；自动因子挖掘闭环；MCP 开放接口。
- P1：人格化 Agent 决策层；实盘网关(可选)；产业链深化；组合优化/风险归因。
- P2：backtrader 适配；图网络/RL 策略；Excel 导出；社区。

## 原则
复用优先不重写；引入项作可选依赖；实盘需合规/模拟盘；因子/RL 防过拟合（保留未来函数检测）；沿用 git+RAG 约定。

## 交付物
- 详细报告：`reports/gap_analysis_2026-08-01.md`
