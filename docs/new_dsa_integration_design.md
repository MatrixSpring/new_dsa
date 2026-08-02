# new_dsa 全系统详细功能实施设计文档（现有系统融合版 / V1.0-INT）

> 本文档在用户《new_dsa 量化投研平台完整设计文档 V1.0》基础上，**把当前仓库已有接口、引擎、数据库、前端页面全部融合进来**，输出"哪些已有、哪些占位、哪些缺失、怎么改"的开发级落地设计。
> 原则：不推翻现有已落地的 25+ 接口与 40+ 数据表，只补齐设计文档要求的缺口；凡现有能力可复用的一律复用。

---

## 0. 文档说明与现状盘点（必读）

### 0.1 核心结论（3 句话）

1. **设计文档描述的约 90% 能力，仓库内已有对应实现或数据底座**，无需从零造；真正"核心新增"的只有【四周期标准化批量前瞻预测】与【前瞻预测中心 UI 聚合页】两块。
2. **存在 3 个必须拍板的结构性冲突**：前端框架（设计写 Vue3+JointJS，实际是 React+TS）、画布技术（设计写 JointJS，实际是自有 graph JSON + React 渲染）、调度框架（设计写 APScheduler，实际用 `schedule` 库）。
3. **设计文档未覆盖、但仓库已存在的高价值资产**不能丢：决策信号系统 `decision_signals`、因子挖掘 `factor_mining`、图网络/RL 策略 `graph_rl_strategy`、模拟盘 `trading`、社区 `community`、MCP 网关、人格化 Agent `persona_analysis`——这些应并入"运维中枢 / 推演模块"，而非被新设计覆盖掉。

### 0.2 现有系统真实资产清单（已盘点）

**后端 API（`api/v1/endpoints/`，全部挂载于 `/api/v1`，共 25 个模块）：**

| 模块 | 路由前缀 | 关键能力 | 设计文档映射 |
|---|---|---|---|
| `industry_chain` | `/industry-chains*` | 产业链目录/图谱/冲击传导 `propagate`/持仓暴露 | 页面4 产业链维护 + DSA 传导引擎 |
| `company` | `/companies*` | 上市公司列表/详情（PE/PB/ESG/关联产业链） | 页面5 公司维护 |
| `intelligence` | `/intelligence*` | 情报源 CRUD + 抓取 + 结构化条目 | 页面1/2 全球/国内动态（抓取层） |
| `forecast` | `/forecast/multi-model-consensus` | 多模型共识推演（**当前占位实现**） | 页面6/7 预测+推演 |
| `dashboard` | `/market/trend` `/stock/recent` `/risk/overview` `/policy/track` `/game/short` `/game/long` `/system/status` `/forecast/multi-consensus` | 大盘/个股/风控/政策赛道/资金博弈/系统状态 | 页面3 单日动态 + 总览 |
| `alerts` | `/alerts*` | 预警规则/触发/通知（已完整） | 全局预警 |
| `decision_signals` | `/decision-signals*` | 决策信号（含 `horizon` 周期、置信度、区间、归因） | **页面6/前瞻预测核心底座** |
| `analysis` | `/analysis*` | 个股/组合分析（POST 262/521，GET 590/665/774/1025） | AI 推演分析 |
| `agent` | `/agent*` | 多 Agent 对话/研究/会话 | AI 推演辅助 |
| `backtest` / `strategy_backtest` | `/backtest*` `/strategy-backtest*` | 回测引擎 | 复盘/回测 |
| `history` | `/history*` | 历史分析存档（829 行） | 复盘 |
| `factor_mining` | `/factor-mining*` | 自动因子挖掘 | 设计未提及（保留） |
| `graph_rl_strategy` | `/graph-rl*` | 相关性图谱+信号传播+Bandit | 设计未提及（保留） |
| `trading` | `/trading*` | 模拟/实盘交易网关 | 设计中期目标（已提前） |
| `portfolio` / `portfolio_optimization` | `/portfolio*` | 组合/风险归因（含 Brinson 类） | 组合前瞻/复盘 |
| `persona_analysis` | `/persona-analysis` | 人格化投资 Agent | 设计未提及（保留） |
| `community` | `/community*` | 帖子/评论/点赞 | 设计长期社区（已提前） |
| `mcp_gateway` | `/mcp/manifest` | MCP 开放接口 | 设计未提及（保留） |
| `export` | `/portfolio-report` `/portfolio-xlsx` | 报告/Excel 导出 | 短期优化"导出 PDF 研报" |
| `stocks` / `auth` / `system_config` / `usage` / `health` | 各前缀 | 个股/鉴权/系统配置/用量/健康 | 页面8 运维中枢 |

**核心引擎（`src/` + `core/`）：**
- `src/industry_chain_propagation.py`：**DSA 传导引擎本体** `propagate_shock()`（BFS 沿 `edges` 的 `coeff`/`lag` 传导，衰减 `1/(1+lag/30)`）+ `chain_exposure_from_holdings()`（持仓→产业链暴露/HHI）。
- `core/multi_model_forecast.py`：多模型预测框架（343 行，**占位，待接真实模型**）。
- `src/scheduler.py`：调度器（基于 `schedule` 库，单日 18:00 + 30s 后台轮询）。
- `src/storage.py`：40+ SQLAlchemy 表（见第 5 章）。
- `src/services/intelligence_service.py`、`alert_service.py`、`quant_scorer.py`、`industry_chain`（macro）等。

**前端（`apps/dsa-web`，React + TypeScript + Vite，lucide-react 图标）：**
- 现有导航 5 大模块：`数据总览仪表盘 /dashboard`、`智能策略管理中心 /strategy`、`风控与绩效监控 /risk`、`投研报告输出中心 /research`、`系统运维与配置 /ops`。
- 已存在页面组件：`HomePage`、`DashboardPage`、`DecisionSignalsPage`、`MultiConsensusPage`、`AlertsPage`、`BacktestPage`、`PortfolioPage`、`StockScreeningPage`、`ChatPage`、`SettingsPage`、`GameEnginePage`、`ResearchPlatformPage`、`LoginPage` 等 18 个。
- 另有 Streamlit 旧前端（`Home.py` + `pages/`：main_workspace / industry_chain / capital_game 等）——属遗留，新设计以 React 前端为准。

**抓取层（`data_provider/`，19 个 fetcher）：** akshare / tushare / tencent / yfinance / finnhub / longbridge / baostock / efinance / pytdx / alphavantage / dragon_tiger(龙虎榜) / chip_intraday(筹码) / consensus_esg / industry_fetcher(产业链) / tw_institutional(台股机构) / us_index_mapping / tickflow / fundamental_adapter / yfinance_fundamental_adapter。**完全覆盖设计文档 L1 四类抓取（全球/国内/个股/产业链）。**

### 0.3 三大结构性冲突（需用户决策，见第 7 章）

| 冲突点 | 设计文档要求 | 仓库现状 | 风险 |
|---|---|---|---|
| 前端框架 | Vue3 + JointJS + ECharts + D3 | React + TS + Vite + lucide-react（无 Vue、无 JointJS） | 若强行切 Vue 等于重写前端，18 个页面报废 |
| 画布/建模 | JointJS 画布拖拽 | 自有 `nodes/edges/companies` JSON 图谱 + React 渲染（IndustryChainSandbox） | 重选画布库需重构建模交互 |
| 调度框架 | APScheduler 分钟级 7×24 | `schedule` 库，单日 18:00 一次 + 30s 轮询 | 现有无法支撑设计"00:00-21:30 分段闭环" |

### 0.4 设计文档未提及、但已存在且应保留的资产

- **决策信号 `decision_signals` + `decision_signal_outcomes` + `decision_signal_feedback`**：已是"多周期预测+复盘"的现成底座（见 §3.2）。
- **因子挖掘 / 图 RL / 模拟盘 / 社区 / MCP / 人格 Agent**：设计中期/长期目标，仓库已提前实现，应并入运维中枢与推演模块，避免重复造轮子。

---

## 1. 现有接口 → 新设计 映射总表（核心交付）

> 成熟度标记：**✅已落地** / **🟡部分/占位** / **❌缺失需新建**

| 设计文档概念 | 对应现有接口/模块 | 成熟度 | 融合动作 |
|---|---|---|---|
| L1 数据采集-全球资讯/汇率/大宗 | `intelligence` + `data_provider`（yfinance/finnhub/alphavantage） | 🟡 | 补"全球地缘/战争/外交"专用源模板；结构化 5 字段（等级/周期/行业/方向/权重）落地到 `intelligence_items` |
| L1 数据采集-国内政策/宏观 | `intelligence`（国务院/央行/证监会模板）+ `dashboard/policy/track` | 🟡 | 政策 AI 拆解（扶持/限制/补贴）接入 `agent` 摘要；写入产业链系数覆盖表 |
| L1 数据采集-个股公告/财报 | `data_provider/fundamental_adapter` + `company_profile` 表 | ✅ | 直接复用；补"利好/利空关键词识别"写 `company_profile.risk` 字段 |
| L1 数据采集-产业链供需 | `data_provider/industry_fetcher` + `xzsc_industry_chain` 表 | ✅ | 复用；补每日盘后自动刷新调度 |
| 页面1 全球动态 | `intelligence/items` + `dashboard/market/trend` + `game/long` | 🟡 | 前端聚合为"全球动态页"；补左侧分类树 + 历史同类事件回溯（查 `history`） |
| 页面2 国内动态 | `intelligence/items`（scope=domestic）+ `dashboard/policy/track` | 🟡 | 前端聚合为"国内动态页"；补政策原文+AI 精简+生效时间 |
| 页面3 单日动态 | `dashboard/market/trend` `/stock/recent` `/game/short` `/risk/overview` | 🟡 | 前端聚合"单日动态页"；补早/中/晚盘分段 + 当日简报自动生成（接 `analysis` 或 `agent`） |
| 页面4 产业链维护 | `industry_chain`（`/industry-chains` `/{id}` `/propagate`） | ✅ | 直接复用图谱编辑；补"自定义传导系数默认值"写库 + 一键导出画布模板 |
| 页面5 公司维护 | `company`（`/companies` `/{code}`） | ✅ | 复用；补 Tab 化（财务/股东/解禁/减持/诉讼/评级）与风险高亮卡片 |
| 页面6 股票AI预测 | `forecast/multi-model-consensus` + `decision_signals` | 🟡 | **关键**：以 `decision_signals` 为存储底座，补"四周期（1周/半月/1月/半年）叠加曲线 + 权重面板"UI；forecast 占位需接真实模型 |
| 页面7 AI推演 | `forecast/multi-model-consensus` + `analysis` + `graph_rl_strategy` | 🟡 | 三情景（基准/乐观/悲观）接 `core/multi_model_forecast` 真实引擎；补因子贡献占比 |
| **页面8（设计写系统维护）** | `system_config` + `system/status_api` + `alerts` + `scheduler` | ✅ | 直接复用；补"定时任务可视化启停"（接 APScheduler 迁移后） |
| **前瞻预测中心（核心新增）** | `decision_signals` + `forecast` + `dashboard` + `portfolio_optimization` | 🟡 | **新建 UI 聚合页** + 补"批量四周期预测"后端任务 + 补"预测复盘归因"接 `decision_signal_outcomes` |
| DSA 产业链传导引擎 | `src/industry_chain_propagation.propagate_shock` | 🟡 | 补设计规则：递归深度≤20、双向衰减0.85、利空衰减0.7、多因子加权(25/25/35/15) |
| 多周期预测引擎 | `core/multi_model_forecast`（占位）+ `decision_signals` | 🟡 | 落地真实模型（Prophet/ARIMA/事件归因），按周期差异化权重 |
| 情景压力测试 | `graph_rl_strategy` + `src/stress_test.py` | 🟡 | 对接三情景并行推演 |
| 回测/复盘迭代 | `backtest` + `history` + `decision_signal_outcomes` | ✅ | 直接复用；补 Brinson 归因拆解（接 `portfolio_optimization/risk-attribution`） |
| 预警推送 | `alerts`（规则/触发/通知完整） | ✅ | 直接复用；补企业微信/邮箱通道（已有 notification 模块） |
| 自动化每日闭环 | `src/scheduler.py`（`schedule` 库） | 🟡 | 迁移到 APScheduler，按设计 6 段时序重写 job |
| 数据库 | `src/storage.py`（40+ 表） | ✅ | 复用绝大多数；补 3~4 张新表（见 §5.3） |

---

## 2. 九大业务页面落地映射（组件级）

> 设计文档"8 大基础页面 + 前瞻预测中心"= 9 页。下表给出每页**现有对应页/组件、复用点、缺失项、改造动作**。

### 2.1 页面1 全球动态（Global Dynamics）
- **现有对应**：`intelligence/items`（scope=global） + `dashboard/market/trend` + `game/long` + 前端无独立页（需新建 `GlobalDynamicsPage.tsx`）。
- **复用**：情报条目列表、全球指数/行业热度数据、跨境资金。
- **缺失**：
  1. 左侧分类树（地缘冲突/国际战争/海外央行/外交/汇率/全球股市/大宗/跨境资金）——用 `intelligence_sources.source_type` + `scope_type` 过滤实现。
  2. 每条事件【高/中/低影响】+【影响周期】+【关联行业】标签——需在 `intelligence_items` 落结构化 5 字段（见 §2.0 规则）。
  3. 历史同类事件回溯按钮——查 `history` + 同 `source_type` 历史事件。
  4. 右侧"加入推演因子/绑定画布/新建预警"快捷操作——分别调 `forecast` / `industry_chain/propagate` / `alerts/rules`。
- **改造动作**：新建页面，复用 `intelligence` 接口与 `DashboardPage` 的图表组件；结构化字段由 `intelligence_service` 在 fetch 时 AI 分级写入。

### 2.2 页面2 国内动态（Domestic Dynamics）
- **现有对应**：`intelligence/items`（scope=domestic） + `dashboard/policy/track`。
- **复用**：政策赛道分析、扶持力度。
- **缺失**：政策原文 + AI 精简解读（接 `agent` 摘要）、生效时间/短期-中长期属性标注、政策受益/受损行业排序。
- **改造动作**：复用 `policy/track` 的 8 条政策赛道，补 AI 拆解（调 `agent/research` 或 LLM 摘要），写入产业链系数覆盖表触发预测刷新。

### 2.3 页面3 单日动态（Daily Dynamics）
- **现有对应**：`dashboard/market/trend` `/stock/recent` `/game/short` `/risk/overview`（数据已齐）。
- **复用**：涨跌家数/成交额/涨跌停（`market/trend`）、北向/主力（`game/short`）、风险概览。
- **缺失**：早/中/晚盘分段资讯（接 `intelligence/items` 按时间过滤）、当日主线题材自动提炼（接 `agent` 或规则）、明日关键事件提醒（查 `intelligence_items` 未来日期）、1 周预测微调结果（查 `decision_signals` horizon=1w）。
- **改造动作**：新建 `DailyDynamicsPage.tsx`，聚合 4 个 dashboard 接口 + intelligence 时间分段；简报生成接 `analysis` 或定时任务。

### 2.4 页面4 产业链信息维护（Industry Maintenance）✅ 基本就绪
- **现有对应**：`industry_chain` 全套 + 前端 `IndustryChainSandbox`（React 渲染 nodes/edges/companies）。
- **复用**：图谱展示、冲击传导 `propagate`、持仓暴露。
- **缺失**：① 节点增删改 UI；② 自定义上下游传导系数默认值写库（当前 `edges.coeff` 默认 0.6，需支持编辑持久化）；③ 行业异常（涨价/减产/过剩）自动标记风险；④ 一键导出画布模板存入模板库。
- **改造动作**：在 `industry_chain` 增 `PUT /industry-chains/{id}`（编辑 nodes/edges coeff/lag）、`POST /industry-chains/{id}/risk-flag`；模板库复用 `xzsc_industry_chain` 或新建 `chain_templates` 表。

### 2.5 页面5 公司信息维护（Company Maintenance）✅ 基本就绪
- **现有对应**：`company`（`/companies` `/{code}`，`company_profile` 表含 PE/PB/PS/市值/ESG/关联产业链/共识评级）。
- **复用**：搜索、详情、`to_dict()` 全维度。
- **缺失**：① Tab 分类（基础/财务/股东/解禁/减持/诉讼/评级/主营）；② 自动利好/利空识别写风险标签；③ 风险高亮卡片；④ 个股自动归类产业链节点。
- **改造动作**：前端 `CompanyPage.tsx` 用 Tab 组织 `to_dict()` 字段；风险标签由 `fundamental_adapter` 抓取时经 `agent` 摘要生成，写入 `company_profile.risk_json`。

### 2.6 页面6 股票 AI 预测（Stock AI Forecast）🟡 底座在，UI 缺
- **现有对应**：`decision_signals`（已含 `horizon` 周期、`confidence`、`entry_low/high`、`stop_loss`、`target_price`、`action`、`reason`、`evidence_json`、`expires_at`）+ `forecast/multi-model-consensus`（占位）。
- **复用**：`decision_signals` 作为"单股多周期预测"存储与查询底座；`MultiConsensusPage.tsx` 已有推演 UI 可改造。
- **缺失**：① 四周期（1周/半月/1月/半年）叠加曲线；② 左侧权重调节面板（宏观/政策/产业链/个股/资金）；③ 风控约束（利空强制下调、最大回撤阈值）；④ 历史预测准确率统计。
- **改造动作**：
  - 后端：新增 `POST /decision-signals/multi-cycle` 批量生成四周期信号（复用 `propagate_shock` + 真实预测模型）。
  - 前端：`StockForecastPage.tsx` 复用 `DecisionSignalsPage` 组件，新增周期选择 + 权重滑块 + ECharts 叠加曲线。
  - **强约束落地**：预测输入必须来自 `intelligence_items` + `xzsc_industry_chain` + `company_profile`，禁止纯 K 线（在 `decision_signals.evidence_json` 强制记录溯源）。

### 2.7 页面7 AI 推演模块（Advanced Simulation）🟡
- **现有对应**：`forecast/multi-model-consensus`（占位） + `analysis` + `graph_rl_strategy` + `src/stress_test.py`。
- **复用**：五模型权重配置（DEFAULT_WEIGHT_CONFIG）、分歧校验逻辑、因子贡献框架。
- **缺失**：① 三情景（基准/乐观/悲观）并行；② 宏观/政策/供需/资金/个股利空各自贡献占比；③ 全市场批量推演筛选潜力/高危赛道；④ 推演报告自动存档复盘。
- **改造动作**：将 `core/multi_model_forecast.py` 占位替换为真实引擎（接 `src/multi_agent.py` 各 Agent）；三情景由 `stress_test` 提供悲观/乐观参数；批量筛选复用 `dashboard/policy/track` + `game/long` 赛道评分。

### 2.8 页面8 系统信息维护后台（Ops Center）✅ 基本就绪
- **现有对应**：`system_config`（接口监控/限流/权限/日志/版本） + `system/status_api`（监控/任务队列/健康检查/清缓存/数据源检查） + `alerts` + `scheduler`。
- **复用**：全部。
- **缺失**：① 定时任务**可视化启停/改周期/看日志**（现有 `scheduler` 无 REST 暴露）；② DSA 全局参数统一管控（递归深度/系数阈值/风险衰减）持久化。
- **改造动作**：APScheduler 迁移后暴露 `GET/POST /system/jobs`；DSA 参数存入 `system_config` 表或新增 `dsa_global_params` 表。

### 2.9 前瞻预测中心（新增核心大模块）🟡 骨架在，需聚合+批量
- **现有对应**：`decision_signals`（事件/行业/个股/组合信号均有 `horizon`）+ `dashboard` + `portfolio_optimization/risk-attribution`（Brinson 类）+ `history`（复盘）。
- **5 子页面落地**：
  1. **事件驱动前瞻**：复用 `intelligence_items` + `industry_chain/propagate`（三层拆解：直接冲击→二级传导→个股）。
  2. **行业产业链前瞻**：复用 `xzsc_industry_chain` + `dashboard/policy/track` + `game/long`，补景气度打分。
  3. **个股前瞻**：复用 `decision_signals`（horizon 四周期）+ `company_profile`。
  4. **组合/大类资产前瞻**：复用 `portfolio_optimization`（宏观多情景：加息/降息/地缘/复苏）。
  5. **预测复盘归因**：复用 `decision_signal_outcomes` + `portfolio_optimization/risk-attribution`（Brinson 归因：事件错误/数据偏差/系数不合理/黑天鹅）。
- **缺失**：① 批量四周期预测调度任务；② 统一报告模板（影响因素拆解+多周期结论表）；③ 子页面导航聚合。
- **改造动作**：新建 `ForecastCenterPage.tsx`（左栏 5 分组），后端新增批量预测 job（见 §4）+ 报告生成（复用 `export`）。

---

## 3. AI 推演 + 多周期预测 详细计算规则（融合现有引擎）

### 3.1 DSA 产业链传导引擎（融合 `propagate_shock`）
现有 `propagate_shock(graph, shock)` 已实现 BFS 沿 `edges` 传导，使用 `coeff`（默认0.6）与 `lag`（默认5），衰减 `decay = 1/(1+lag/30)`。需补设计规则：

| 设计规则 | 现有实现 | 融合改造 |
|---|---|---|
| 最大迭代深度 20 层 | BFS 无显式深度限制（靠 `abs(child)>1e-4` 截断） | 加 `max_depth=20` 参数，超深终止 |
| 传导系数区间 0~1 校验 | `coeff` 取自 edge，未校验 | 写入时 `clamp(coeff,0,1)` |
| 双向传导衰减 0.85 | 无向邻接（已双向），无额外衰减 | 叠加 `0.85` 乘子（双向边二次传导） |
| 风险利空衰减 0.7 | 无区分利好/利空 | `shock.kind=negative` 时路径乘 `0.7` |
| 多因子加权 宏观25/政策25/产业链35/资金15 | 纯图谱传导，无因子加权 | 在 `node_impacts` 汇总层叠加因子权重（接 `dashboard` 评分） |

> 改造点集中在 `src/industry_chain_propagation.py` 与 `industry_chain.py` 的 `propagate` 接口入参，向后兼容（旧调用不传新参数时走默认）。

### 3.2 多周期预测（融合 `decision_signals` + `core/multi_model_forecast`）
**关键认知**：`decision_signals` 表已有 `horizon` 字段（周期维度）、`confidence`、`entry_low/high`、`stop_loss`、`target_price`、`action`(涨跌方向)、`reason`(核心驱动)、`risk_summary`(主要风险)、`evidence_json`(溯源)、`expires_at`(周期到期)——**设计的"多周期结论表"字段已天然存在**。

设计 §3.4 四周期差异化权重映射到 `decision_signals` 生成逻辑：

| 周期 | 设计权重（资金/事件/产业/基本面/宏观） | 落地方式 |
|---|---|---|
| 1周 | 40/35/15/10/- | `decision_signals.horizon='1w'`，因子取 `game/short`+`intelligence` 突发 |
| 半月 | 35/30/25/10/- | `horizon='2w'`，取 `policy/track`+供需边际 |
| 1月 | 10/20/45/20/5 | `horizon='1m'`，取财报+产业落地 |
| 半年 | 5/15/50/15/30* | `horizon='6m'`，取产能周期+宏观（*注：设计半年未单列宏观，实际应含宏观30，建议合并为产业50+宏观30+基本面15+资金5） |

> `core/multi_model_forecast.py` 当前为**占位框架**（确定性哈希/随机），必须接入真实模型：时序（Prophet/ARIMA 接 `stock_daily`）、事件归因（接 `intelligence_items`）、多情景（接 `stress_test`）。

### 3.3 预测准确率自动复盘（直接复用现有）
- `decision_signal_outcomes` 表：**已是预测到期复盘表**（记录信号实际涨跌 vs 预判）。
- `decision_signal_feedback` 表：反馈微调。
- 融合动作：每日 21:30 闭环中扫描 `decision_signals` 中 `expires_at < now` 且未复盘的记录 → 比对 `stock_daily` 真实行情 → 写 `outcomes` → 统计胜率/偏差 → 微调 `dsa_global_params` 权重。

---

## 4. 每日全自动时序调度（融合现有 scheduler → APScheduler）

### 4.1 现状 Gap
现有 `src/scheduler.py` 基于 `schedule` 库：**仅支持单日 18:00 一次 daily job + 后台任务 30s 轮询**，无法表达设计 §6 的"00:00-21:30 六段式分钟级闭环"。全仓库**无 APScheduler**。

### 4.2 融合方案（保留现有任务函数，迁移触发器）
- **不重写业务逻辑**：现有 `intelligence_service.fetch_enabled_sources()`、`propagate_shock`、`decision_signals` 生成、`backtest` 复盘均为可复用函数。
- **引入 APScheduler 替代 `schedule` 库**，在 `src/scheduler.py` 新增 `APSchedulerBackend`，注册 6 段 cron job：

| 时段 | 设计动作 | 复用现有函数 | 新增 job |
|---|---|---|---|
| 00:00-07:50 | 隔夜全球抓取+分级+短线初算 | `intelligence.fetch_enabled_sources(scope=global)` + `agent` 分级 | `job_overnight_crawl` |
| 08:00 | 盘前简报+1周/半月批量预测更新 | `intelligence(scope=domestic)` + `decision_signals` 批量生成(1w/2w) | `job_preopen` |
| 09:20-15:00 | 盘中实时异动+临时推演+预警 | `dashboard/market/trend` 轮询 + `alerts` 触发 | `job_intraday`(每30s) |
| 15:30-18:00 | 全量行情/财报/产业链落地 | `data_provider` 全量 + `company_profile` 刷新 + `xzsc` 刷新 | `job_postclose` |
| 19:00-21:00 | 全行业批量推演+四周期预测 | `forecast` 真实引擎 + `decision_signals` 批量(全周期) + `dashboard` 赛道筛选 | `job_batch_forecast` |
| 21:30 | 归档+推送+复盘写入 | `export` 报告 + `notification` 推送 + `decision_signal_outcomes` 复盘 | `job_archive_review` |

- **可视化启停**：APScheduler 迁移后在 `system_config` 暴露 `GET/POST /system/jobs`（列出/启停/改 cron），满足设计页面8需求。
- **优雅退出**：保留现有 `GracefulShutdown`（SIGTERM/SIGINT）。

---

## 5. 数据库结构融合（可直接建表）

### 5.1 现有可直接复用的表（设计文档所需，仓库已有）
| 设计需求 | 现有表 | 备注 |
|---|---|---|
| 产业链库 | `xzsc_industry_chain`（58条L1赛道，segments 上下游客结构） | 直接复用，补每日价格/供需刷新 |
| 产业链图谱运行时 | 内存 graph（nodes/edges/companies JSON） | 由 `xzsc_industry_chain` + 沙盘构建，可不落库 |
| 公司信息库 | `company_profile` | 含 PE/PB/ESG/关联产业链/共识评级 |
| 全球/国内事件库 | `intelligence_items` + `intelligence_sources` | 补结构化 5 字段列 |
| 每日动态库 | `news_intel` + `intelligence_items`（按日） | 直接复用 |
| 决策信号/多周期预测 | `decision_signals` | **核心**，含 horizon/置信度/区间/归因 |
| 预测复盘 | `decision_signal_outcomes` + `decision_signal_feedback` | 直接复用 |
| 预警 | `alert_rules` / `alert_triggers` / `alert_notifications` / `alert_cooldowns` | 完整 |
| 回测 | `backtest_results` / `backtest_summaries` | 直接复用 |
| 组合/资产 | `portfolio_*`(10张) | 大类资产前瞻复用 |
| 分析历史 | `analysis_history` | 复盘复用 |
| 系统配置 | `schema_migrations` + `system_config` 相关 | 复用 |

### 5.2 现有表需补的列（轻量 ALTER，不新建）
- `intelligence_items` 增加：`impact_level`(高/中/低)、`impact_cycle`(1w/2w/1m/6m)、`impact_industry`(关联产业链id)、`impact_direction`(利好/利空/中性)、`transmit_weight`(0~1)。——落实设计 §2.2 结构化 5 字段。
- `company_profile` 增加：`risk_json`(暴雷/减持/亏损标签)、`linked_chains` 已存在（补自动匹配逻辑）。
- `xzsc_industry_chain` 或新建运行表增加：`price`/`inventory`/`utilization`/`supply_gap`（每日盘后刷新）。

### 5.3 需新建的表（仅 4 张，补齐设计缺口）
```sql
-- 1. 多周期前瞻预测批量结果（聚合 decision_signals 的四周期快照，便于中心页查询）
CREATE TABLE forecast_batch_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scope_type VARCHAR(16) NOT NULL,      -- event/industry/stock/portfolio
  scope_value VARCHAR(64),              -- 事件id/产业链id/股票code
  cycle VARCHAR(8) NOT NULL,            -- 1w/2w/1m/6m
  direction VARCHAR(8),                 -- up/down/oscillation
  low_pct REAL, high_pct REAL,          -- 波动区间
  up_prob REAL, confidence REAL,
  core_driver TEXT, main_risk TEXT,
  generated_at DATETIME, job_run_id VARCHAR(64)
);
CREATE INDEX ix_fbs_scope_cycle ON forecast_batch_snapshot(scope_type, scope_value, cycle);

-- 2. 产业链传导系数覆盖（页面4"自定义传导系数默认值"持久化）
CREATE TABLE chain_edge_override (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chain_id VARCHAR(32) NOT NULL,
  source_node VARCHAR(64) NOT NULL,
  target_node VARCHAR(64) NOT NULL,
  coeff REAL NOT NULL DEFAULT 0.6,
  lag INTEGER DEFAULT 5,
  updated_at DATETIME,
  UNIQUE(chain_id, source_node, target_node)
);

-- 3. DSA 全局模型参数（页面8 统一管控：递归深度/系数阈值/风险衰减）
CREATE TABLE dsa_global_params (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  param_key VARCHAR(48) NOT NULL UNIQUE,  -- max_depth/decay_bidirectional/decay_bearish/weight_macro...
  param_value REAL NOT NULL,
  updated_at DATETIME
);

-- 4. 自动化任务运行日志（设计 §4.2 六段闭环可视化的日志底座，替代现有内存日志）
CREATE TABLE scheduler_job_run (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_key VARCHAR(32) NOT NULL,          -- overnight/preopen/intraday/postclose/batch/archive
  started_at DATETIME, finished_at DATETIME,
  status VARCHAR(16),                    -- success/failed/running
  summary TEXT, error TEXT
);
CREATE INDEX ix_sjr_job_key ON scheduler_job_run(job_key, started_at);
```

---

## 6. 前后端联动协议融合

### 6.1 设计文档提出的四层 vs 现有 `/api/v1`
设计 §4.1 提出：`/api/crawl/*` `/api/db/*` `/api/dsa/*` `/api/predict/*` `/api/backtest/*`。
**建议不推翻现有 `/api/v1` 体系**（已 25 模块、前端已对接），而是**把设计四层映射为现有分组**，避免前端大规模返工：

| 设计层 | 映射现有 | 说明 |
|---|---|---|
| 第一层 数据采集 | `intelligence/*` + `data_provider`（后端定时调用，前端不直接调） | 前端只通过 `intelligence/items` 读结果 |
| 第二层 数据库读写 | `company/*` `industry_chain/*` `intelligence/*`（读） + 新增编辑接口 | 写操作加鉴权（现有 `auth`） |
| 第三层 计算引擎 | `industry_chain/propagate`(DSA) `forecast/*`(推演) `decision-signals/*`(预测) `backtest/*`(回测) | 直接对应 |
| 第四层 上层业务 | 所有页面调上述层，前端只展示/配置/触发 | 一致 |

> **结论**：设计文档的"分层接口架构"在语义上已存在，只是命名不同。新增接口（如批量四周期 `POST /decision-signals/multi-cycle`、编辑 `PUT /industry-chains/{id}`、APScheduler `GET /system/jobs`）按现有 `api/v1/endpoints` 规范追加即可，**不要新建 `/api/crawl` 等平行前缀**。

### 6.2 前端联动规则（设计 §4.3）
现有前端已具备"画布修改→实时重算"雏形（`industry_chain/propagate` 是同步接口）。补：
- 画布改系数 → 写 `chain_edge_override` → 前端重调 `propagate` 刷新预测。
- 新增事件/政策 → 写 `intelligence_items` → 一键触发 `POST /decision-signals/multi-cycle` 重算。
- 每日自动结果 → 各页面 `useEffect` 拉取 `decision_signals` + `forecast_batch_snapshot`。

---

## 7. 关键冲突与决策建议（需用户拍板）

### D1. 前端框架：Vue3+JointJS vs 现有 React
- **现状**：`apps/dsa-web` 是 React+TS+Vite+lucide-react，18 个页面已成型；无 Vue、无 JointJS。设计文档写的是 Vue3+JointJS。
- **建议（强烈）**：**保留 React**，不要切 Vue。切框架 = 重写全部前端，成本极高且无收益。JointJS 画布可用现有 `nodes/edges` JSON + React 渲染（或引入 React 版图库如 `reactflow`/`cytoscape`）替代，建模交互已具备。
- **影响**：设计文档"前端技术栈"章节需改；UI 统一规范（深色 #0F172A / 主色 #165DFF / 涨红跌绿）直接套用现有 `theme`。

### D2. 调度框架：APScheduler vs 现有 `schedule` 库
- **建议**：**引入 APScheduler** 替代 `schedule` 库（仅调度触发器替换，业务逻辑函数全复用），以支撑设计六段式分钟级闭环与可视化启停。
- **影响**：`src/scheduler.py` 增加 `APSchedulerBackend`；现有 `Scheduler`/`GracefulShutdown` 保留兼容。

### D3. 占位模型如何真实化
- **现状**：`core/multi_model_forecast.py` 与 `forecast/multi-model-consensus` 均为占位（哈希/随机）。
- **建议路径**：① 时序模型接 `stock_daily` + Prophet/ARIMA；② 事件归因接 `intelligence_items` 结构化字段；③ 多 Agent 共识接 `src/multi_agent.py` 真实 Agent；④ 三情景接 `src/stress_test.py`。分阶段替换，先让 `decision_signals` 四周期有真实值再迭代权重。

### D4. 设计"8 页面"与现有"5 大模块导航"如何统一
- **建议**：以**现有 5 大模块导航为骨架**（仪表盘/策略/风控/投研/运维），把设计的 9 页**融入**而非另起一套：
  - 全球/国内/单日动态 → 归入"仪表盘"下的 3 个子页（或新建"资讯中心"模块）。
  - 产业链/公司维护 → 归入"策略/投研"。
  - 股票预测/AI 推演/前瞻预测中心 → 归入"策略中心/投研报告"。
  - 系统维护 → 现有"运维配置"。
- **影响**：避免导航体系分裂，用户学习成本最低。

---

## 8. 开发落地优先级（基于现有，重新排）

> 设计文档 4 阶段大体成立，但**第一阶段重点从"搭页面"改为"补缺口"**，因为页面与接口大多已存在。

### 第一阶段（0~30 天）：补齐缺口 + 协议融合
- [ ] 引入 APScheduler，迁移 6 段闭环（D2），暴露 `/system/jobs`（页面8）。
- [ ] `intelligence_items` 补结构化 5 字段 + AI 分级（页面1/2 数据底座）。
- [ ] 新建"全球/国内/单日动态"3 个前端聚合页（复用 dashboard+intelligence）。
- [ ] `industry_chain` 增编辑/风险标记/模板导出接口（页面4 收尾）。
- [ ] `company_profile` 增 `risk_json` + Tab 化前端（页面5 收尾）。
- [ ] 新建 `forecast_batch_snapshot` 等 4 张表（§5.3）。

### 第二阶段（31~60 天）：核心计算真实化
- [ ] `core/multi_model_forecast` 接真实模型（D3），`decision_signals` 四周期有真实输出。
- [ ] 前瞻预测中心 UI 聚合页（5 子页）上线，接 `forecast_batch_snapshot`。
- [ ] DSA 引擎补设计规则（深度20/双向0.85/利空0.7/因子加权）（§3.1）。
- [ ] 三情景并行推演（接 `stress_test` + `graph_rl`）。

### 第三阶段（61~90 天）：业务联动 + 复盘闭环
- [ ] 所有页面互通联动（画布改→重算→预测刷新）。
- [ ] 预测复盘归因完整上线（接 `decision_signal_outcomes` + `portfolio_optimization/risk-attribution` Brinson）。
- [ ] 预警完整通道（企业微信/邮箱，复用 `notification`）。
- [ ] Sentry 运维监控（现有 `system/status_api` 增强）。

### 第四阶段（90 天+）：迭代升级
- [ ] 模拟盘对接（`trading` 已存在，接预测信号）。
- [ ] 大模型深度解读（`agent`/`persona` 已存在）。
- [ ] 协同编辑、移动端、社区生态（现有 `community` 已提前）。

---

## 9. 最终能力总结（融合后）

融合现有系统后，new_dsa 实际**已具备**：情报自动抓取分级、产业链自定义图谱与冲击传导、公司全维度库、决策信号多周期预测底座、预警、回测、组合优化、因子挖掘、图RL、模拟盘、社区、MCP、Agent 研究——远超设计文档描述的"8 页+前瞻中心"。

**真正待补的"最后一公里"**（本文档交付重点）：
1. 把分散在 `dashboard`/`intelligence`/`decision_signals` 的能力**聚合为设计定义的 9 个标准页面**（尤其全球/国内/单日动态 3 个资讯页与前瞻预测中心）。
2. 把 `forecast`/`multi_model_forecast` 的**占位模型替换为真实引擎**，让四周期预测有真值。
3. 把 `schedule` 库**迁移到 APScheduler**，落地设计 §6 的六段式全自动闭环。
4. 补齐 **4 张新表 + 少量 ALTER**，固化设计的"结构化 5 字段 / 自定义传导系数 / DSA 全局参数 / 调度日志"。

> 一句话：现有系统是"内核已强、外壳待整合"，本融合文档的目标不是重建，而是**收口与标准化**。
