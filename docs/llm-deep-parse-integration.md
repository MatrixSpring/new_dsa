# 长文本深度解析模块整合落地完整方案文档

- **文档编号**：DSA-OPT-LLM-001
- **版本**：V1.0
- **适用范围**：new_dsa 量化投研系统
- **目标**：整合 GitHub 上成熟开源项目的长文本金融解析能力，落地「政策 / 研报 / 招股书 / 纪要分层拆解、多文档交叉对比、隐藏约束挖掘、长期规划提取」全能力，**无缝嵌入原有 DSA 架构**，不推翻现有量化、自动化、数据库体系。
- **核心原则**：LLM 只做信息提炼与逻辑梳理，量化涨跌、区间、概率依旧由 DSA 数学模型输出。

---

## 0. 前置结论（经 GitHub 真实核查后修订）

1. **GitHub 上确实大量存在**可复用的长文本金融解析开源项目，无需从零开发；但用户原草稿中列出的 4 个项目里有 **1 个（PDF-Query-Fin）经检索未找到真实仓库**，本文已用 3 个经核实的真实项目替代。
2. 额外发现 **FinSight（中国人民大学 RUC-NLPIR，2025-12 开源）** 为当前最契合本系统的开源项目：多 Agent 深度研报、证据溯源、覆盖 A 股/港股/美股、自动图表，可直接覆盖原草稿中「借鉴方向 1 / 2 / 6」的多项诉求，已补入复用清单。
3. 所有新增模块作为**独立中间服务层（llm_parse_service）**接入系统，复用既有 `llm/gateway.py` 统一调用通道，输出标准化 JSON 对接 DSA 传导模型、产业链库、前瞻预测模块。
4. 复用既有验证范式（见 §10）：后端 `scripts/serve_llm_parse.py`（隔离路由 + uvicorn + curl，验证「请求 → 数据」），前端 `scripts/verify_llm_parse_display.tsx`（tsc 编译 + react-dom/server SSR，验证「数据显示」），满足「从请求数据到显示都要验证」的全链路要求。

---

## 一、GitHub 开源项目真实核查与能力筛选

> 核查时间：2026-08-02。筛选标准：金融场景适配、结构化输出、支持 PDF/网页/TXT 解析、支持多文档比对、可私有化部署、轻量化易二次开发。

### 1.1 核查结论表

| 项目 | 真实地址 | 核查状态 | 可取能力模块 | 备注 |
| --- | --- | --- | --- | --- |
| **vibe-research** | `github.com/simonlin1212/Vibe-Research` | ✅ 真实 | 研报/公告上传（PDF/Word/txt/图片）、五维分析框架、事件因果梳理、本地部署 + MCP | 原草稿描述基本准确；自托管、数据不出本地，支持 Claude Code/Codex/MCP 接入 |
| **FinGPT / FinNLP** | `github.com/AI4Finance-Foundation/FinGPT` | ✅ 真实 | 财报结构化提取、FinNLP 信息抽取（NER/关系/数值推理）、长文摘要 | `fingpt/FinGPT_FinancialReportAnalysis` 子模块真实；轻量 LoRA 微调路线，适合本地化 |
| **LangChain 多文档对比模式** | `github.com/KenjiFH/Comparitive-Analyst-Agent`、`github.com/Uziii-man/financial-agentic-rag` | ✅ 真实（模式存在，非单一 repo） | LangChain + ChromaDB/ Qdrant 向量比对、观点冲突识别、SLM/LLM 分级调用 | 原草稿的 "LangChain-Financial-Analyst" 为通用指代；实际对应上述两个生产级实现 |
| **PDF-Query-Fin** | 未检索到 | ❌ **未发现真实仓库** | — | **已从复用清单移除**，替换为下方 3 个经核实的真实项目 |
| ↳ CiteOrDie | `github.com/vanGodLEE/CiteOrDie` | ✅ 真实（强替代） | 证据驱动 PDF 条款提取、qwen-long 1M 上下文、MinerU 版面解析、PageIndex 原文溯源 | 最贴合「隐藏约束挖掘 + 原文定位」诉求 |
| ↳ PactGuard-ERNIE-PP | `github.com/tjujingzong/PactGuard-ERNIE-PP` | ✅ 真实（强替代） | 合同/政策风险条款识别 + 原文定位、布局恢复、风险分级与修订建议 | 条款检索 + 风险分级能力可直接借鉴 |
| ↳ contractex | PyPI `contractex`（Apache-2.0） | ✅ 真实（库级复用） | CUAD 41 类条款、风险检测、财务条款抽取、多 LLM/本地模型支持 | 可作为「隐藏约束挖掘」底层库 |
| **FinSight（RUC）** | `github.com/RUC-NLPIR/FinSight` | ✅ 真实（**强增补**） | 多 Agent 深度研报、证据溯源（Chain-of-Analysis）、覆盖 A股/港股/美股、自动专业图表、2万字报告 | 原草稿未提及；综合覆盖借鉴方向 1/2/6，应作为首选参考架构 |
| **FinIntelAgent** | `github.com/Kaanishkaa/FinIntelAgent-Autonomous-Financial-Report-Analyzer` | ✅ 真实 | SEC 10-K KPI 抽取 + RAG 历史趋势对比 + 风险分析 | 补充「长期规划/财务趋势」抽取 |
| **Wide-Research-for-Finance** | `github.com/Lingsio/Wide-Research-for-Finance` | ✅ 真实 | 每小时新闻聚合 + 情绪识别 + 事件影响评估 | 补强资讯层，可作为爬虫长文本自动触发源 |

### 1.2 最终能力拆分复用规划（更新为真实项目）

| 需求能力 | 主要复用来源 | 取舍说明 |
| --- | --- | --- |
| 基础分层拆解（短/中/长对齐四周期） | vibe-research 五维框架 + FinSight CAVM 任务拆解 | 复用其「按周期分层」方法论，不搬代码 |
| 文本分片 / 版面恢复 | CiteOrDie（MinerU + PageIndex） | 替代原草稿的 PDF-Query-Fin 分片逻辑 |
| 多文档交叉对比 / 冲突识别 | Comparitive-Analyst-Agent（LangChain+ChromaDB） | RAG 向量比对 + 观点冲突检测 |
| 隐藏约束 / 风险条款挖掘 | CiteOrDie + PactGuard-ERNIE-PP + contractex（CUAD） | 多源互补，输出风险分级 |
| 长期规划 / 财务趋势提取 | FinReport/FinGPT 财务结构化 + FinIntelAgent RAG 趋势 | 产能/路线/财务拐点抽取 |
| 证据溯源 / 防幻觉 | FinSight Chain-of-Analysis + CiteOrDie PageIndex | 每条结论绑定原文位置 |

---

## 二、模块整体架构设计（四层独立服务，低耦合接入 DSA）

### 第一层：前端交互接入层（嵌入既有页面，无新页面）

在以下**既有页面**统一新增「长文本智能解析」按钮 + 弹窗入口（这些页面在本仓库已存在，新增仅为增量）：

- **全球动态 / 国内动态 / 单日动态**（已建 `DynamicsCenterPage` + `DynamicsViews` 面板）→ 政策、海外公告、地缘文件、盘后纪要解析；
- **产业链维护页**（`src/ui/pages/industry_chain_editor.py` 对应前端）→ 行业白皮书、产业规划文件；
- **公司信息维护页** → 招股书、财报、股东大会纪要、调研纪要；
- **前瞻预测中心**（`ForecastCenterPage`）→ 多篇券商研报横向对比。

支持格式：网页链接、TXT、PDF、Word、粘贴大段原文。两种模式：
- **快速模式**：本地轻量模型（Qwen-Lite / Llama3），浅层摘要、基础分层（日常高频）；
- **深度模式**：API 大模型精读（复用 `llm/gateway.py` 的 DeepSeek 路由），全能力拆解 + 交叉比对 + 隐藏约束挖掘（重要文件）。

### 第二层：LLM 解析中间服务层（新增 `core/llm_parse_service.py`）

5 个核心子模块，对应需求 5 项能力：

1. `preprocess_chunker` — 文本分片 / 版面恢复（CiteOrDie 思路）；
2. `layered_extractor` — 分层结构化拆解（短/中/长对齐四周期）；
3. `cross_compare` — 多文档交叉对比（LangChain + ChromaDB RAG）；
4. `constraint_miner` — 隐藏约束 & 隐性风险挖掘（CUAD + 条款定位）；
5. `plan_extractor` — 短/中/长期规划提取。

所有子模块统一通过 **`llm/gateway.py` 的 `LLMGateway`** 发起调用（复用其任务路由、限流、重试、结构化 JSON 输出能力），新增 `TaskType`：`LLM_PARSE_LAYERED` / `LLM_PARSE_CONSTRAINT` / `LLM_PARSE_COMPARE`。

新增 prompt 模板文件（置于 `llm/prompts/`）：
- `llm_parse_layered.prompt`
- `llm_parse_constraint.prompt`
- `llm_parse_compare.prompt`

### 第三层：结构化输出对接层（强制固定 JSON 格式）

解析结果统一输出 §四 定义的标准化 JSON，经 `api/v1/endpoints/llm_parse.py` 落地入库。

### 第四层：原有 DSA 系统接收层（既有模块，不改动其内部算法）

结构化数据自动分发至 4 个核心底层模块：

- **事件库**：写入 `data/` 下既有 event 表（全局/国内）及新增 `llm_parse_results` 表；
- **产业链库**：调用 `src/industry_chain_propagation.propagate_shock` 调整对应行业传导系数、供需缺口、景气打分；
- **公司库**：更新个股基本面权重、风险打分（既有 `stock_diagnose` 链路）；
- **预测引擎**：触发 `core/dsa_daily_pipeline.ForecastPipeline.forecast_symbol` 重新计算 1周/半月/1月/半年多周期前瞻。

---

## 三、与 new_dsa 真实架构的接入点清单

| 接入点 | 既有文件 | 改动方式 |
| --- | --- | --- |
| LLM 统一调用 | `llm/gateway.py` | 新增 3 个 `TaskType` + 复用 `analyze_news` 同款结构化输出 |
| 解析服务 | 新增 `core/llm_parse_service.py` | 独立模块，仅 import `llm.gateway` |
| API 路由 | 新增 `api/v1/endpoints/llm_parse.py`，挂载前缀 `/api/v1/llm-parse` | `POST /parse`（单文档）、`POST /compare`（多文档） |
| 定时任务 | `src/services/runtime_scheduler.py`（APScheduler） | 新增 3 个 Cron 任务（见 §六） |
| 下游联动 | `src/industry_chain_propagation.py`、`core/dsa_daily_pipeline.py` | 仅新增「接收结构化 JSON → 调既有函数」的适配层，不改既有算法 |
| 前端入口 | `apps/dsa-web/src/components/dynamics/DynamicsViews.tsx`、`ForecastCenterPage.tsx` 等 | 新增「LLM 深度解读」按钮 + 弹窗组件 `LLMParseModal.tsx` |
| 前端 API | `apps/dsa-web/src/api/`（新增 `llmParse.ts`） | 复用 `apiClient` |
| 存储 | `data/`（sqlite） | 新增 `llm_parse_results` 表 |

---

## 四、标准化 JSON 输出对接层（Schema 定义）

所有解析结果统一输出以下固定结构（在原草稿基础上补充溯源与置信度字段）：

```json
{
  "source_id": "文档唯一编号(MD5)",
  "source_type": "政策|券商研报|招股书|会议纪要|行业白皮书",
  "short_term_1w": {
    "direct_effect": "直接利好/利空内容",
    "scope": "适用行业/个股",
    "trigger_time": "落地生效时间"
  },
  "mid_term_1m": {
    "industry_change": "供需、产能、门槛变化",
    "profit_change": "行业利润变动预判"
  },
  "long_term_halfyear": {
    "industry_plan": "长期路线、产能目标、技术路线",
    "macro_orientation": "宏观长期导向"
  },
  "hidden_constraint": [
    { "content": "约束原文", "risk_level": "高|中|低", "effect_cycle": "生效周期", "quote_ref": "原文段落溯源位置" }
  ],
  "cross_compare_result": [
    { "consistent_view": "多方统一观点", "conflict_view": "观点矛盾分歧点",
      "consensus_optimistic": "普遍利好共识", "consensus_pessimistic": "普遍利空共识",
      "source_refs": ["docA#p12", "docB#p3"] }
  ],
  "risk_mining": [
    { "content": "挖掘到的潜在风险/业绩拐点/远期利空", "risk_level": "高|中|低", "confidence": 0.0 }
  ],
  "reference_origin": "原文段落溯源位置",
  "confidence": 0.0,
  "parsed_at": "ISO8601"
}
```

**入库映射规则**：
- `short/mid/long_term_*` → 写入 `llm_parse_results` 对应周期列，并作为 `forecast_symbol` 的额外因子输入；
- `hidden_constraint` 高风险项 → 自动下调对应行业/个股权重，同步悲观情景推演参数；
- `cross_compare_result.conflict_view` → 标记「不确定中性因子」，降低对应预测置信度；共识项 → 加大对应行业传导权重；
- `reference_origin` / `quote_ref` → 持久化，供复盘时一键回溯原文。

---

## 五、5 项核心能力详细落地实施方案

### 能力 1：长篇文本分层拆解（P0，7 天）
- 复用：CiteOrDie 滑动窗口分片 + vibe-research 五维分层 + FinSight 任务拆解。
- 分层标准严格对齐系统四周期：**短期（1周/半月）、中期（1个月）、长期（半年）**。
- 层级：表层层（摘要/主旨/适用范围）→ 短期层（即时条款/刺激/限制）→ 中期层（目标/门槛/补贴）→ 长期层（规划/产能约束/技术路线）。
- 联动：拆解完成自动标记关联行业、个股，一键绑定画布节点，作为 DSA 推演因子。

### 能力 2：多文档交叉对比（P0，10 天）
- 复用：Comparitive-Analyst-Agent（LangChain + ChromaDB）RAG 向量比对、冲突识别。
- 支持同时上传 2~10 份文档；输出共识看多/看空、观点分歧、乐观/悲观假设；**每条结论标注来源文档与段落**（FinSight 溯源思路），杜绝幻觉。
- 联动：分歧点 → 降置信度中性因子；共识点 → 加大传导权重。

### 能力 3：隐藏约束挖掘（P0，10 天）
- 复用：CiteOrDie + PactGuard-ERNIE-PP + contractex（CUAD 41 类条款）。
- 挖掘范围：政策附加门槛/配额/退出机制；招股书对赌/质押/商誉；纪要委婉利空/订单不确定性；研报乐观假设背后的苛刻前提。
- 联动：高风险约束 → 自动标记利空，下调权重，同步悲观情景参数。

### 能力 4：长期规划提取（P0，8 天）
- 复用：FinReport/FinGPT 财务结构化 + FinIntelAgent RAG 趋势 + vibe 长周期模板。
- 提取：产能规划、政策路线、技术路线、宏观导向。
- 联动：直接写入产业链长期景气度模型，作为半年周期预测核心输入。

### 能力 5：隐性风险深度挖掘（P1，15 天）
- 从财报措辞、管理层发言、调研纪要挖掘业绩拐点、订单下滑；结合同业对比识别竞争力弱化。
- 风险自动量化打分，同步更新公司风险系数（既有 `stock_diagnose`）。

---

## 六、与原有自动化流水线融合方案

复用既有 `src/services/runtime_scheduler.py`（APScheduler），新增 3 个定时任务，**原每日时序调度不变**：

| 任务 | Cron | 动作 |
| --- | --- | --- |
| 隔夜重磅解析 | 每日 08:10 | 抓取隔夜海外政策/券商研报，批量分层解析入库 |
| 盘后公告解析 | 每日 15:40 | 解析 A 股收盘后晚间公告、调研纪要 |
| 周度行业对比 | 每周日 19:30 | 汇总一周行业研报，多文档交叉对比，更新中长期预判 |

- **手动触发**：用户随时上传文件即时解析（`POST /api/v1/llm-parse/parse`）；
- **自动触发**：爬虫抓取长文本后自动调用解析服务（Wide-Research-for-Finance 模式可作为触发源参考）。

---

## 七、部署方案（复用 litellm_config 多模型路由）

`litellm_config.yaml` 已支持多模型路由，解析服务直接复用：

- **模式 1（轻量本地）**：快速解析用 Qwen-Lite / Llama3 本地模型，离线运行，无 API 费用；
- **模式 2（深度精读）**：调用第三方 API（DeepSeek 等），经 `llm/gateway.py` 限流、缓存复用；
- **模式 3（机构私有化）**：本地部署 7B/70B 金融微调模型，RAG 知识库本地持久化。

通用优化：解析结果 Redis 缓存（相同文档 7 天内直接读取）；长文档分片**异步解析**，前端不阻塞。

---

## 八、分阶段落地排期与交付物（映射到本仓库实际目录）

| 阶段 | 周期 | 优先级 | 交付物 | 落库位置 |
| --- | --- | --- | --- | --- |
| 一、快速上线 | 0~10 天 | P0 | `core/llm_parse_service.py`（preprocess + layered）、`api/v1/endpoints/llm_parse.py`、`llm/prompts/llm_parse_layered.prompt`、前端 `LLMParseModal.tsx` + `api/llmParse.ts`、单文档解析打通 | 新增文件，不改既有算法 |
| 二、对比与约束挖掘 | 11~20 天 | P0 | `cross_compare` + `constraint_miner` + `plan_extractor` 子模块、`llm_parse_constraint.prompt`/`llm_parse_compare.prompt`、结构化数据自动写入产业链/公司库 | 同上 |
| 三、自动化融合与风险挖掘 | 21~35 天 | P1 | `runtime_scheduler.py` 新增 3 个定时任务、`risk_mining` 模块、全链路压测 + 幻觉过滤 | 同上 |
| 四、深度优化 | 36~60 天 | P2 | 本地私有 RAG 知识库、对接四大智能 Agent（见 §九）、Prompt 优化降幻觉 | 同上 |

---

## 九、四大智能 Agent 研究员架构（对应原草稿「借鉴方向 2」，作为 P1+ 延伸）

基于 FinSight 多 Agent 思路，在既有量化引擎之上叠加 4 个固定 Agent：

| Agent | 职责 | 与 DSA 联动 |
| --- | --- | --- |
| 宏观 Agent | 地缘/汇率/全球货币政策跟踪，自主检索海外突发 | 补充爬虫遗漏，更新全球动态库与宏观因子权重 |
| 产业链 Agent | 供需/产能/上下游对比/新技术跟踪 | 巡检产业链库，优化传导系数 |
| 个股 Agent | 财报拆解/管理层讲话/同业对标/拐点挖掘 | 定期巡检持仓股，更新风险打分 |
| 复盘 Agent | 历史事件匹配/因果梳理/案例库 | 预测到期后自动复盘，微调 DSA 全局参数 |

前端新增**全系统悬浮 AI 指令对话面板**（复用 `llm/gateway.py` 的 `CHAT_PROFESSIONAL` 路由），支持自然语言下发任务，指令经对应 Agent 协同后输出结构化报告并自动更新前瞻预测。

---

## 十、验证方案（复用既有「请求 → 数据 → 显示」全链路范式）

延续本仓库已验证的轻量验证范式（沙箱无 vite/vitest 原生打包器，改用 tsc + react-dom/server SSR + 隔离 uvicorn）：

### 10.1 后端「请求 → 数据」验证
- 新增 `scripts/serve_llm_parse.py`：隔离加载 `api.v1.endpoints.llm_parse` 路由（前缀 `/api/v1/llm-parse`），`--serve` 用 uvicorn 起真实 HTTP；
- `curl -X POST http://127.0.0.1:8000/api/v1/llm-parse/parse -d '{"text":"...","mode":"deep"}'` 断言返回 200 + 标准化 JSON（含 `short_term_1w` / `hidden_constraint` / `reference_origin`）。

### 10.2 前端「数据显示」验证
- 新增 `apps/dsa-web/scripts/verify_llm_parse_display.tsx`：用 `tsc` 编译为 CJS + `react-dom/server` `renderToStaticMarkup` 渲染 `LLMParseModal` 解析结果卡片，断言方向/约束/溯源信息出现在 HTML（`DISPLAY_OK`）。

### 10.3 类型与单测
- 对 `types/llmParse.ts`、`api/llmParse.ts` 做 `tsc` 类型检查；
- 后端 `tests/test_llm_parse_endpoint.py`：断言 schema 字段完整、约束高风险项联动逻辑正确。

---

## 十一、风险管控与核心原则（守住 DSA 原有壁垒）

1. **量化决策权归属 DSA 模型**：LLM 仅负责信息提炼/逻辑梳理/风险挖掘；所有涨跌幅区间、上涨概率、量化权重一律由 DSA 数学模型计算，大模型**禁止输出数值预测**，杜绝主观化。
2. **幻觉防控 = 原文溯源**：所有 AI 提炼内容必须标注 `reference_origin` / `quote_ref`；系统自动校验，无原文支撑的观点自动降权并标记「仅供参考」。
3. **不重构原有架构**：新增模块均为外挂服务，原有数据库、画布、推演引擎、预测算法完全不动，只做数据输入扩充。
4. **成本控制**：高频轻量解析走本地模型，深度精读按需调 API，缓存复用减少重复调用。
5. **许可证合规**：复用前确认各开源项目许可证（FinGPT/MIT、CiteOrDie/MIT、contractex/Apache-2.0、FinSight 需向 RUC 确认商用授权）；仅借鉴方法论与 prompt，避免直接复制受传染许可代码。

---

## 十二、合入后系统整体能力升级总结

- **信息广度**：从浅层资讯抓取升级为长文本深度挖掘（显性信息 + 隐性约束 + 远期风险）；
- **信息精度**：单一资料解读升级为多文档交叉验证，过滤片面观点，统一市场共识；
- **预测可靠性**：为 DSA 模型补充深度长期逻辑素材，短/中/长周期预判准确度同步提升；
- **自动化升级**：从人工筛选资料升级为系统自动精读海量研报政策，全自动闭环更成熟；
- **对比 vibe / 普通开源项目**：保留量化稳定性优势，补齐 AI 文本理解短板，综合能力超越单一开源项目。

---

## 附录 A：标准化 Prompt 模板（直接投入开发）

### A.1 分层拆解（对应 `llm_parse_layered.prompt`）
```
你是专业金融研究员，对给定文本做严格三段分层整理，只输出指定 JSON 结构：
1. 短期（1周-半月）：即时落地内容、适用范围、生效时间；
2. 中期（1个月）：行业供需、利润、门槛变化；
3. 长期（半年）：产业规划、产能目标、技术路线；
每条内容标注对应原文位置（quote_ref），禁止编造无依据内容。
```

### A.2 隐藏约束挖掘（对应 `llm_parse_constraint.prompt`）
```
通读全文，找出所有隐藏限制、附加条件、远期利空、苛刻前提、配额约束、退出机制，
划分风险高/中/低，标注生效周期与原文位置（quote_ref），输出为 JSON 数组。
```

### A.3 多文档对比（对应 `llm_parse_compare.prompt`）
```
对比多篇文档，整理：共识看多、共识看空、观点分歧、乐观假设、悲观隐患，
每条结论标注来源文档与段落（source_refs），不主观臆断，输出为 JSON。
```

---

## 附录 B：新增文件清单

```
core/llm_parse_service.py                 # 解析中间服务（5 子模块）
api/v1/endpoints/llm_parse.py             # 路由 /api/v1/llm-parse
llm/prompts/llm_parse_layered.prompt      # 分层拆解 prompt
llm/prompts/llm_parse_constraint.prompt   # 隐藏约束 prompt
llm/prompts/llm_parse_compare.prompt      # 多文档对比 prompt
apps/dsa-web/src/types/llmParse.ts        # 前端类型
apps/dsa-web/src/api/llmParse.ts          # 前端 API
apps/dsa-web/src/components/llm/LLMParseModal.tsx  # 解析弹窗
scripts/serve_llm_parse.py                # 后端验证服务
apps/dsa-web/scripts/verify_llm_parse_display.tsx  # 前端显示验证
tests/test_llm_parse_endpoint.py          # 后端单测
```

> 注：本文档为整合落地方案（规划），实际编码与测试按 §八 排期推进，每阶段均按 §十 完成「请求 → 数据 → 显示」全链路验证后再进入下一阶段。
