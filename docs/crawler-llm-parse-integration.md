# 自动爬虫 + 长文本解析 全自动流水线整合落地方案

- **文档编号**：`DSA-CRAWL-LLM-MERGE-V1.0`
- **版本**：V1.0
- **适用范围**：new_dsa 量化投研系统（A 股 / 港股 / 美股，地缘 + 政策 + 产业链 + 基本面四维驱动）
- **前置文档**：`docs/llm-deep-parse-integration.md`（`DSA-OPT-LLM-001`，长文本解析层 `llm_parse_service` 设计）
- **目标**：在既有 `llm_parse_service` 解析能力之上，新增 `crawl_service` 自动采集微服务，形成 **【自动抓取 → 清洗转文本 → 分层拆解 / 交叉比对 / 约束挖掘 → 标准化 JSON → 自动灌入 DSA 量化系统】** 全自动闭环，无缝嵌入原 DSA 架构，不推翻现有量化、自动化、数据库体系。

---

## 0. 核查前置结论（GitHub 真实项目验证）

用户询问「有没有自动爬取的 GitHub 项目」。结论：**存在大量成熟开源爬虫项目，完全覆盖 官方公告 / 券商研报 / 会议纪要 / 政策网页 四类采集目标**，可模块化抽取，低成本合入。

下方表格为**逐项目真实核查**结果（已用 WebSearch 验证仓库存在性与能力），并对原始草稿中的两处错误做了修订：

| 采集目标 | 开源项目（已核实） | 仓库地址（核实无误） | 状态 | 可复用模块 |
| --- | --- | --- | --- | --- |
| 招股书 / 财报 / 股东大会纪要 / 监管公告（巨潮官方） | **cninfo-crawler** | https://github.com/sukanka/cninfo-crawler | ✅ 真实 | 巨潮官方接口请求逻辑、按股票/关键词增量抓取、PDF 下载 |
| 同上（分布式 / 入库 / PDF 转文本） | **China_stock_announcement** | https://github.com/feiyilicare/China_stock_announcement | ✅ 真实 | Python 爬虫 + MySQL 持久化 + `2plaintext/` PDF→文本脚本 |
| 同上（Scrapy+Kafka 分布式） | **CninfoDistributedSpider** | https://github.com/flicck/CninfoDistributedSpider | ✅ 真实 | Scrapy 分布式架构、指定股票/时间段全量抓取 |
| 研报 / 纪要 / 公告 / 行情 统一调度 | **a-stock-data** | https://github.com/simonlin1212/a-stock-data | ✅ 真实（V3.6.0，47 端点 / 15 源） | 研报层（东财 reportapi + PDF 下载）、公告层（巨潮 cninfo）、定时调度、去重、标准化 JSON 输出 |
| 网页正文提纯 / 动态页抓取（AI 友好） | **Crawl4AI** | https://github.com/unclecode/crawl4ai | ✅ 真实（50k+ stars） | 网页→纯净 Markdown、语义分片、PDF 解析、异步高速、LLM 抽取策略 |
| 老牌金融数据源框架（辅助补充） | **akshare** | https://github.com/akfamily/akshare | ✅ 真实（规范仓库为 `akfamily/akshare`） | 研报/公告/新闻接口（接口易失效，仅辅助） |
| 金融多源爬虫集群（研报/政策/新闻） | **FinGPT**（DataCrawler） | https://github.com/AI4Finance-Foundation/FinGPT | ✅ 真实 | 7×24 抓取、文本清洗、分片预处理、原生适配 LLM 输入 |
| 抓取 + 分片 + 向量入库一体化 | **WaterCrawl** | https://github.com/watercrawl/watercrawl | ✅ 真实（替代草稿中不存在的 `WebContext-AI`） | Django+Scrapy+Celery，LLM-Ready 输出，Dify/N8N 集成 |
| 轻量 RAG 内容爬虫（分片+向量） | **ai-content-crawler** | https://github.com/kai-agent-free/ai-content-crawler | ✅ 真实（替代 `WebContext-AI`） | 抓取即分块（chunkSize/overlap），直接喂向量库 |

> ⚠️ **对原始草稿的两处修订**
> 1. 草稿中的 `WebContext-AI` **经核查无对应 GitHub 仓库**，已用 `WaterCrawl` 与 `kai-agent-free/ai-content-crawler` 替代。
> 2. `report-crawler`（独立研报爬虫）无明确主流仓库；研报抓取直接复用 `a-stock-data` 的「研报层」与 `FinGPT` 爬虫集群即可，无需另起项目。
> 3. `akshare` 规范仓库为 `akfamily/akshare`（非其他 fork）。
> 4. 注：`a-stock-data` 与 `vibe-research` 同作者 `simonlin1212`，但其「研报层 / 公告层」底层调用的是东财 / 同花顺 / 巨潮公开接口，合规边界见 §7。

---

## 1. 需求 5 项核心能力 ↔ 爬虫供给映射

| 解析能力（源于 DSA-OPT-LLM-001） | 由哪类爬虫供给原始素材 | 首选爬虫 |
| --- | --- | --- |
| 长文本分层拆解（短/中/长期） | 单份政策 / 招股书 / 研报 PDF | cninfo-crawler、a-stock-data、Crawl4AI（网页） |
| 多文档交叉对比（2~10 份） | 同行业多篇研报 / 多份政策 | a-stock-data（批量研报）、Crawl4AI（批量网页） |
| 隐藏约束挖掘 | 招股书 / 政策原文 / 纪要 | cninfo-crawler、China_stock_announcement |
| 长期规划提取 | 产业白皮书 / 政策网页 / 招股书 | Crawl4AI、a-stock-data |
| 金融中文场景适配 | A 股公告 / 中文政策 / 股东大会纪要 | cninfo-crawler、a-stock-data（本土优先） |

**结论**：爬虫层只负责「把正确的原始文档搬进来」，所有 5 项解析能力仍在 `llm_parse_service` 完成（见前置文档）。爬虫与解析是**松耦合**两段，通过「文件落盘 + 去重缓存 + 推送队列」衔接。

---

## 2. 系统接入四层架构（从上至下，原有 DSA 内核 100% 不动）

```
┌──────────────────────────────────────────────────────────────────────┐
│ 第一层：多源爬虫采集层（新增 crawl_service 微服务）                      │
│   ├─ 官方公告抓取   → cninfo-crawler / China_stock_announcement         │
│   ├─ 券商研报&纪要  → a-stock-data 研报层 / FinGPT 集群                  │
│   └─ 外网政策网页   → Crawl4AI / WaterCrawl                            │
└───────────────────────────────────┬──────────────────────────────────┘
                                     │ 落盘 PDF/网页 + 元数据
┌───────────────────────────────────▼──────────────────────────────────┐
│ 第二层：预处理清洗层（复用 Docling + 现有文本工具）                       │
│   PDF/网页 → 纯净文本提取、降噪、智能分片、格式标准化                      │
└───────────────────────────────────┬──────────────────────────────────┘
                                     │ 规整长文本
┌───────────────────────────────────▼──────────────────────────────────┐
│ 第三层：LLM 解析层（已有 llm_parse_service，见 DSA-OPT-LLM-001）         │
│   分层拆解 / 多文档比对 / 隐藏约束挖掘 / 长期规划提取 → 固定结构化 JSON     │
└───────────────────────────────────┬──────────────────────────────────┘
                                     │ 标准化 JSON（带 source_refs 溯源）
┌───────────────────────────────────▼──────────────────────────────────┐
│ 第四层：DSA 系统联动层（仅新增「收 JSON → 调既有函数」适配层）            │
│   事件库 / 产业链库 / 个股库 / DSA 预测引擎（core/dsa_daily_pipeline）    │
└──────────────────────────────────────────────────────────────────────┘
```

**本仓库真实接入点（务必对齐，避免重复造轮子）**：

| 层 | 落点 | 复用现有 | 新建 |
| --- | --- | --- | --- |
| 第一层 crawl_service | `data_provider/extended/announcement_crawler.py`、`research_report_crawler.py`、`policy_crawler.py` | `data_provider/provider_router.py` 的 fallback 模式、`data_provider/base.py` 的 Fetcher 基类 | 3 个 crawler 适配 + 去重缓存 |
| 调度注册 | `src/services/runtime_scheduler.py` | `scheduler.set_daily_task(func, run_immediately=)`、`scheduler.add_background_task(...)` | 3~4 个 crawl job 注册 |
| 第二层预处理 | `core/text_preprocess.py`（或并入 `llm_parse_service`） | 现有文本清洗工具 | 接入 Docling（新依赖） |
| 第三层解析 | `core/llm_parse_service.py` | `llm/gateway.py`（统一 LLM 通道，新增 `LLM_PARSE_*` 任务类型） | 5 子模块（见前置文档） |
| 第四层联动 | `core/dsa_daily_pipeline.py` + `src/industry_chain_propagation.py` | 既有 `forecast_symbol` / `propagate_shock` | 仅「收 JSON → 调既有函数」适配层，**不改内部算法** |

---

## 3. crawl_service 详细设计

### 3.1 三大抓取模块（复用开源代码二次封装，非从零）

**(1) 官方公告抓取模块** — 封装 `cninfo-crawler` + `China_stock_announcement`
- 数据源：巨潮（沪深北交易所法定披露平台，公开、稳定、合规风险最低）。
- 定时：
  - 全天轮询：实时抓取晚间公告、临时政策；
  - 每日 17:30：批量下载当日招股书、股东大会决议、业绩说明会纪要。
- 过滤：关键词白名单（招股书 / 股东大会 / 业绩说明会 / 产业政策）自动筛目标文档。
- 复用：`cninfo` 官方公开 API（不模拟浏览器、严格限流），`2plaintext/` 的 PDF→文本脚本。

**(2) 券商研报 & 纪要模块** — 封装 `a-stock-data` 研报层
- 定时：
  - 每日 07:50：抓取券商晨会纪要；
  - 每日 18:00：抓取当日行业深度研报、机构调研纪要。
- 支持自定义行业、券商名单定向抓取；复用 a-stock-data 的「去重 + 标准化 JSON 路径输出」。

**(3) 产业政策网页抓取模块** — 封装 `Crawl4AI`
- 定时：每日 09:00，自动抓取国家部委、地方产业政策白皮书，转为纯净 Markdown。
- 复用：Crawl4AI 的 `fit_markdown`（去噪）、`chunking_strategy`、`LLMExtractionStrategy`（可选）。

### 3.2 统一文件生命周期

```
抓取 PDF/网页 → 文本提取(Docling/2plaintext) → 缓存去重(Redis/本地, 7 天内重复文档跳过)
   → 送入 llm_parse_service 解析 → 结构化 JSON 入库
```

- **去重键**：`hash(原始文档内容)` 或 `公告唯一 ID`；已解析文档永久跳过重复解析（省算力）。
- **元数据**：`source`、`doc_type`、`stock_codes`、`published_at`、`title`、`local_path`。

### 3.3 爬虫 → 解析 自动联动规则

| 触发场景 | 自动启用解析能力 |
| --- | --- |
| 单份政策 / 单份招股书 | 分层拆解 + 隐藏约束挖掘 + 长期规划提取 |
| 同行业 2~10 份研报批量抓取 | 自动启用多文档交叉对比 |
| 纪要类文本（调研/股东大会） | 强化隐性利空、管理层表态挖掘 |
| 网页政策白皮书 | 长期规划提取 + 分层拆解（中长期为主） |

---

## 4. 接入原有 DSA 定时流水线（与现有分时调度完全对齐）

原有 `runtime_scheduler.py` 已有 `set_daily_task` / `add_background_task`。新增爬虫自动任务**严格对齐现有时序**：

| 时间 | 原 DSA 任务 | 新增 crawl 任务 | 衔接 |
| --- | --- | --- | --- |
| 07:50 | — | 抓取券商晨会纪要 | 08:10 自动批量解析入库 |
| 15:40 | 收盘 | 抓取当日调研纪要、上市公司公告 | 即时解析 |
| 17:30 | — | 抓取晚间公告、招股书 | 晚间自动深度解析 |
| 周日 19:30 | 周度汇总 | 一周研报批量抓取 + 交叉对比 | 更新中长期预测 |

> 新增任务均以 `scheduler.set_daily_task` 注册（或 `add_background_task` 做后台轮询），**不改变原有分析主流程的触发逻辑**。爬虫失败不应拖垮分析主流程（沿用 AGENTS.md 稳定性护栏：单一数据源失败降级而非 fail-fast）。

---

## 5. 标准化结构化输出（与 DSA-OPT-LLM-001 对齐，含溯源字段）

解析结果统一输出以下 JSON，**强制绑定原文位置**以防幻觉：

```json
{
  "doc_id": "唯一文档编号",
  "doc_type": ["政策|券商研报|招股书|会议纪要|行业白皮书"],
  "source_origin": "原文页码/段落定位",
  "source_refs": ["doc_id#段落索引", "..."],
  "short_term_1w":  { "effect": "即时影响", "scope": "关联行业/个股", "trigger_time": "生效时间" },
  "mid_term_1m":   { "industry_change": "供需/门槛变化", "profit_impact": "利润影响预判" },
  "long_term_halfyear": { "industry_plan": "产能/技术路线", "macro_orientation": "长期宏观导向" },
  "hidden_constraint": [ { "content": "约束原文", "risk_level": "高|中|低", "cycle": "生效周期" } ],
  "cross_compare": { "consensus": "统一观点", "conflict": "分歧点", "optimistic_view": "乐观预判", "pessimistic_view": "悲观隐患" },
  "potential_risk": ["远期利空/业绩拐点/行业瓶颈"],
  "reliability": 0.0
}
```

- `reliability`：置信度 0~1，由 `llm/gateway.py` 的结构化输出校验得出。
- `source_refs`：所有 AI 提炼内容强制原文溯源，无来源支撑自动降权并标注「仅供参考」。

---

## 6. 分阶段落地排期 & 交付物

| 阶段 | 周期 | 交付物 |
| --- | --- | --- |
| **P0 快速落地** | 0~12 天 | `crawl_service` 基础爬虫（cninfo-crawler + a-stock-data 封装）；PDF 批量转文本（Docling）；「爬虫文件自动推送至 `llm_parse_service`」接口；官方公告 + 晨会纪要自动抓取 |
| **P1 完整能力** | 13~30 天 | Crawl4AI 外网政策抓取模块；去重/缓存/异常重试；批量研报自动触发多文档对比、纪要自动风险挖掘；解析结果自动写入数据库、自动更新产业链权重 |
| **P2 稳定优化** | 31~50 天 | 分布式抓取 + 代理池防封禁；爬虫失败告警、文档缺失日志；Agent 接入爬虫实现 AI 自主检索补充冷门资料 |

> 注：P0~P2 与前置文档 `DSA-OPT-LLM-001` 的 Phase 1~4 在时序上**并行推进**——爬虫负责「供料」，解析负责「加工」，两者通过标准化 JSON 解耦，可独立开发与验证。

---

## 7. 防爬与稳定性 + 合规边界（重要）

### 7.1 稳定性
- **官方巨潮接口**：严格限流（单 IP 3 秒 1 次），使用官方公开 API，不模拟浏览器。
- **券商/网页源**：随机 UA、请求间隔随机 1~3 秒、代理池轮换。
- **缓存**：Redis 记录文档唯一标识，已解析文档永久跳过。
- **降级**：接口失效自动切换备用数据源（a-stock-data 已内置 `备用源速查` 降级表），保证采集不中断。

### 7.2 合规与法律风险（必须遵守）
- ✅ **巨潮（沪深北交易所法定披露平台）**：强制公开披露，爬取与本地存储用于研究合规风险最低，首选。
- ⚠️ **券商研报平台（慧博投研 / 发现报告 / 各券商研究所官网）**：多数站点的 ToS 禁止自动抓取与再分发，研报本身受版权保护。**建议仅使用已获授权的数据源**（如机构自身订阅的研报 API），或仅做「个人研究用途的临时缓存、不对外分发」。批量抓取并 redistribution 存在侵权风险。
- ⚠️ **`a-stock-data` 研报层**：底层调用东财 reportapi / 同花顺 / iwencai 公开接口，属灰色地带，商用前需评估合规；**仅作内部研究、不对外提供服务**。
- ✅ **政策网页（发改委 / 工信部等政府网站）**：公开信息，Crawl4AI 抓取合规。
- **底线**：爬虫只采集「公开 / 已授权」素材；本项目所有产出仅用于内部量化研究，不构成投资建议，不对外分发原始文档。

---

## 8. 核心原则（坚守 DSA 壁垒不变）

1. **爬虫只负责原始素材采集，LLM 只做文本整理挖掘**；量化预测、权重计算始终由 DSA 数学模型（`core/dsa_daily_pipeline.py` + `src/industry_chain_propagation.py`）输出。
2. **所有新增模块均为外挂微服务**（`crawl_service` / `llm_parse_service`），不修改原有 DSA 内核、画布、数据库结构；第四层联动仅新增「收 JSON → 调既有函数」适配层。
3. **全链路可溯源**：爬虫来源、文本段落、AI 提炼内容全程标记，防控幻觉。
4. **故障隔离**：单一爬虫源失败降级而非 fail-fast，不拖垮分析主流程（AGENTS.md 稳定性护栏）。

---

## 9. 验证方案（复用「请求→数据→显示」范式）

沿用既有验证体系（`scripts/serve_predict.py` 的隔离路由 + `uvicorn` + `curl`；前端 `tsc` + `react-dom/server` SSR），新增爬虫链路验证：

**(a) 后端「请求→数据」验证**
- 新增 `scripts/serve_crawl_parse.py`：以独立模块加载 `crawl_service` 的 mock 适配层（用本地样例 PDF/网页替代真实外网请求，避免沙箱网络依赖与合规风险），挂载 `/api/v1/crawl/ingest` 与 `/api/v1/llm-parse/run`。
- `uvicorn` 起服务 + `curl` 验证：POST 样例文档 → 返回标准化 JSON（含 `source_refs`、`reliability`）→ 验证「爬虫落盘 → 解析 → 结构化 JSON」全链路。
- pytest 覆盖：去重缓存命中、联动规则（单文档 vs 多文档）、降级路径（源失效不抛异常）。

**(b) 前端「数据显示」验证**
- 在已建的 `DynamicsViews` / `ForecastCenterPage` 上新增「LLM 深度解读」弹窗（符合 DSA-OPT-LLM-001 第一层前端接入），用 `scripts/verify_llm_parse_display.tsx`（`tsc` 编译 + `react-dom/server` SSR）断言解析结果（约束条数 / 周期分层 / 溯源标记）出现在 HTML。

**(c) 调度验证**
- 单元测试直接调用 `runtime_scheduler` 注册函数，断言 crawl job 已挂入 scheduler 且 cron 表达式与 §4 时序一致（不真实等待定时触发）。

---

## 10. 最终全自动工作流总览

```
定时自动爬取【政策 / 招股书 / 研报 / 会议纪要】
   → PDF / 网页清洗分片（Docling / Crawl4AI）
   → LLM 分层拆解、多文档比对、隐藏约束挖掘、长期规划提取（llm_parse_service）
   → 标准化结构化数据入库（带 source_refs 溯源）
   → 自动更新产业链、个股参数（industry_chain_propagation）
   → DSA 模型重新计算 1 周 / 半月 / 1 月 / 半年预测（dsa_daily_pipeline）
   → 可视化画布同步更新推演因子
```

---

## 11. 与既有文档关系 & 下一步

- 本方案是 `DSA-OPT-LLM-001`（解析层）的**上游供料扩展**，二者通过标准化 JSON 解耦。
- 原始草稿中的 `DSA-MERGE-LLM-RAG-V1.0`（6 项目解析版）可合并回 `docs/llm-deep-parse-integration.md`，将解析层项目清单从 4 个扩为 6 个（增补 Docling / FinRobot / DISC-FinLLM）——如需我同步修订可告知。
- **下一步建议**（延续「依次实现、测试验证」节奏，二选一）：
  1. 先收尾被本研究打断的**三聚合页前端**（全球/国内/单日动态，底层已就绪，缺页面+路由+验证）；或
  2. 直接动手 **Phase 1（P0）**：搭 `crawl_service` 适配器 + `llm_parse_service` 接口 + 前端弹窗，并用 §9 验证范式跑通全链路。
