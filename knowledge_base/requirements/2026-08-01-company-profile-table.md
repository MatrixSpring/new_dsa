# 上市公司全维度信息表（company_profile）

- 日期：2026-08-01
- 需求：建立上市公司信息维度表，补充信息，并将系统已有公司信息合并进新表
- 状态：已完成并验证

## 需求要点
用户要求按以下维度建表并补充/合并数据：
1. 公司基础信息：股本、股东、高管、员工人数、净资产占比、大额商誉、限售解禁、股东户数
2. 股东与分红：十大流通股东、股权质押、股息率、股利支付率、派现融资比
3. 估值指标：总市值、股价、市盈率（PE）、市净率（PB）、市销率（PS）
4. 财务分析：收入、主营占比、毛利润、净利润、扣非净利润、净利率、现金流、资产负债率、营收构成、利润构成、存货周转天数
5. 商业与行业分析：行业周期、政策影响、商业模式、市场规模、行业市占率、产品定价权、业绩驱动因子、客户集中度、供应商集中度
6. 技术与研发：研发费用、研发人数、新增专利、存量专利、技术布局
7. 其他：优点/亮点、主要风险

## 实现方案
- 模型：`src/storage.py` 新增 `CompanyProfile`（56 列），覆盖上述 7 组维度 + 身份字段 + 合并元数据（`data_sources`/`linked_chains`）；JSON 类字段以 Text(JSON 字符串) 存储，`to_dict()` 自动反序列化。
- 合并 ETL：`scripts/build_company_profiles.py` 幂等 upsert，数据来源：
  - `data/cache/stocks.index.json` —— 代码/名称/拼音/别名（身份解析）
  - `fundamental_snapshot` —— 估值（pe/pb/总市值/流通市值）
  - `industry_chain_fusion` —— xzsc/申万/curated 链公司 → `linked_chains`
  - `industry_chain_sandbox_data.json` —— 产业沙盘内置链（lithium/semiconductor/photovoltaic）公司 → `linked_chains`
  - 代码统一归一化为 6 位；仅纳入"系统已有公司信息"集合（fundamental ∪ fusion ∪ builtin），共 179 家。
- 接口：`api/v1/endpoints/company.py` 只读接口 `GET /companies`（搜索/来源过滤/分页）、`GET /companies/{code}`（全维度详情），注册于 `api/v1/router.py`。

## 验证结果
- ETL：179 家公司，全部含名称；7 家含估值（fundamental）；173 家含产业链关联。
- 接口：列表 total=179、详情（如 300750 宁德时代 linked_chains 13 条）、`q=宁德` 搜索、来源过滤 `industry_chain_fusion`(160 家) 均正常。
- 后端 :8000 与前端 localhost:3100 已启动运行。

## 后续扩展
- 富维度（股东/财务/研发/行业等）目前多为空列，待接入行情/财务/公告等数据源做二次 ETL 填充。
- 可选：将全市场股票主表也纳入 seed（当前仅纳入有实际信息的已知公司）。
