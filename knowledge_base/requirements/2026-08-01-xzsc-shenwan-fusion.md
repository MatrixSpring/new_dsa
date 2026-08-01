# xzsc 新质生产力产业链 与 申万产业链 数据融合（L2 交叉映射增强）

**日期**：2026-08-01
**需求**：将新质生产力产业链（xzsc，58 条）与申万产业链（252 条 L3）进行融合，让 xzsc 链获得真实上市公司，并修复 impact_analyzer 的申万回链断链。
**状态**：已完成（含 19 条主题链 curated 补全）

## 背景
两套数据分类体系不同、无共享主键：xzsc = 主题赛道（含上下游环节拓扑，无公司）；申万 = 官方行业分类（含龙头公司名、无代码、无拓扑）。不能直接 union，需互补桥接。

## 关键决策
- 新建 `src/data/industry_chain_fusion.py`：
  - `load_stock_name_index()` 读 `data/cache/stocks.index.json`（31678 条）建 名称/别名→代码 索引；
  - `load_shenwan_items()` 读申万全量 252 L3（仅 29 条带 leaders）；
  - `build_xzsc_shenwan_fusion()` 用 xzsc 名称/l2/环节名 子串匹配申万 l3/上下游，建双向映射，申万龙头名解析为代码；
  - `match_shenwan_by_text()` 中文感知匹配，修复 impact_analyzer 原空格分词对中文失效。
- 后端 `industry_chain.py`：`_build_xzsc_graph` 把融合公司按节点挂接；目录加 `companyCount`；返回 `fusion` 元数据（shenwanRefs/curatedRefs/companyCount/curatedCount）。
- 修复 `impact_analyzer.py`：`shenwan_chains` 从 `find_affected_chains(title.split())`（查不全的 shenwan_chain_ledger + 中文空格分词→恒空）改为 `match_shenwan_by_text(f"{title} {content}")`。
- A 项：19 条主题链（元宇宙/算力/人工智能/量子通信等）其申万对应 L3 未带 leader 标签，新增 `CURATED_XZSC_COMPANIES`（链 no→[(公司名,环节提示)]）人工梳理映射，按图谱节点精准挂接。

## 覆盖
- xzsc 58 条链现 100% 含公司（39 自动 + 19 curated，去重 435+ 家）。
- 9 个初选名因更名/退市替换：粤水电→广东建工、丸美股份→丸美生物、苏宁易购→百联股份、云从科技→虹软科技、易华录→广电运通/云赛智联、联创股份→昊华科技、星环科技→拓尔思。

## 覆盖边界 / 后续
- curated 公司属主题映射增强（非申万官方 leader 字段）。
- 可选后续：B 项 L1 申万落库 + 统一目录（`/industry-chains` 加 `source=shenwan` 同列表展示）。

## 关联
- 上游需求：产业链沙盘原型集成对接（见 `2026-08-01-industry-chain-sandbox-integration.md`）。
- 数据源：xzsc_industry_chain 表；sw_industry_chain_dict（申万）；stocks.index.json（代码索引）。
