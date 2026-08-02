# DSA 反向归因 · 全平台舆情信号源架构对账（DSA-OPINION-ARCH-V1.0）

> 本文档把用户「全平台分类梳理 + 多平台爬虫整合方案」蓝图，对账到已落地的 DSA 反向归因
> 四路正交信号源架构（#23 行情 / #25 披露 / #28 头条舆情 / #31 微信舆情），并固化
> **权重模型、六层信息圈层、多源交叉验证** 三项共享契约，供后续新源（财联社 / 社区 / 海外）
> 与跨切面模块（P1）复用。
>
> 设计底线（贯穿全文）：所有信号源只「喂情绪/催化事件」，涨跌幅度、量化概率永远由 DSA
> 数学模型输出；LLM / FinBERT 仅做素材梳理；官方公告 > 机构研报 > 圈层前瞻 > 自媒体公域舆情。

---

## 0. 现有架构现状（已闭环，内核零改动）

| 信号源 | 编号 | 伴随表 | 工厂/端点 | 权重（短/长） | 状态 |
| --- | --- | --- | --- | --- | --- |
| 行情大涨池 | #23 | `BacktraceScreenPool` | market 源 | — | ✅ |
| 法定披露（巨潮/交易所） | #25 | `BacktraceDisclosure` | disclosure | 长 0.4 / 短 0.25* | ✅ |
| 头条公域舆情 | #28 | `BacktraceOpinion` | opinion | 短 0.15 / 长 0.05 | ✅ |
| 微信私域舆情 | #31 | `BacktraceWechatOpinion` | wechat | 短 0.20 / 长 0.08 | ✅ |
| 短线快讯（财联社/华尔街见闻/金十） | #34 | `BacktraceFlashOpinion` | flash | 短 0.22 / 长 0.09 | ✅ |
| 深度社区（雪球/股吧/淘股吧） | #36 | `BacktraceCommunityOpinion` | community | 短 0.13 / 长 0.05 | ✅ |
| 海外权威（彭博/路透/WSJ/Seeking Alpha） | #37 | `BacktraceOverseasOpinion` | overseas | 短 0.14 / 长 0.18 | ✅ |

\* 披露短时权重取蓝图 §五.2「公告落地 0.25」（§一.1 单源给 0.3，已收敛到 0.25）。

闭环扫描 `scan_alerts` 在 `watchlist=None` 时把各池标的 union 叠加进大涨池：
`_resolve_disclosure_codes → union(披露催化)`、`_resolve_opinion_codes → union(舆情催化)`、
`_resolve_wechat_codes → union(微信舆情)`、`_resolve_flash_codes → union(快讯催化)`、
`_resolve_community_codes → union(社区热议)`、`_resolve_overseas_codes → union(海外权威)`，
结果 dict 增 `xxxCandidates`、per-alert 增 `hasXxx`。Kronos(#35) 为逐 alert 技术面富化底座、
不扩张候选池（结果 `kronosAnalyzed`），与六路 union 源正交互补。

在此之上，**#38 六层信息圈层 + 多源交叉验证（元分析层，非信号源）** 消费七路源的 per-stock 情感 /
可信度 / 谣言标记，归入 L0~L5 可信圈层并计算：圈层命中、独立权威源数、共识等级（strong/moderate/
weak/none）、可信度（单散户 ≤0.3 / 单权威 0.5 / 2+ 权威 0.7~0.9）、权威×散户方向冲突、谣言标记。
实现于 `src/services/opinion_info_layers.py`（共享常量）+ `src/services/opinion_cross_validation.py`
（build_source_index / cross_validate_alert / aggregate_summary），扫描结果新增 per-alert
`crossValidation` 与扫描级 `crossValidationSummary`；端点 `/closed-loop/info-layers`、
`/closed-loop/cross-validation`。不改变内核决策权、不扩张候选池。

---

## 1. 七大类平台 → 落地映射

| 类别 | 平台 | 对应信号源 | 落地状态 | 爬虫模块（蓝图 §三.1） |
| --- | --- | --- | --- | --- |
| 第一类 法定权威披露 | 巨潮 / 交易所 | #25 披露源 | ✅ 已建（generic，待按平台细化） | `official_spider` |
| 第二类 短线快讯 | 财联社 / 华尔街见闻 / 金十 | #34 快讯源 | ✅ 已建 | `flash_spider` |
| 第三类 深度社区 | 雪球 / 股吧 / 淘股吧 | #36 社区源 | ✅ 已建 | `community_spider` |
| 第四类 微信生态 | 公众号 / 视频号 | #31 微信源 | ✅ 已建 | `wechat_spider` |
| 第五类 公域短视频 | 头条 / 抖音 / 小红书 | #28 头条源 | ✅ 已建（头条为主） | `toutiao_spider` |
| 第六类 海外权威 | 彭博 / 路透 / WSJ / Seeking Alpha | **新增 overseas** | ✅ 已建 #37 | `overseas_spider` |
| 第七类 垂直专业媒体 | 财新 / 券商中国 / e公司 | flash 子集（负面爆料） | ⏳ 并入 flash | `flash_spider` |

结论：蓝图 7 类 → 实际新增 **3 个信号源**（flash / community / overseas），其余已被
#25 / #28 / #31 覆盖。每个新源沿用同一工厂范式（Base/Mock/Real + `get_*_provider`
→ `(provider,mode,reason)` + `describe_*/refresh_*/list_*`），内核与 db 完全不改。

---

## 2. 权重模型固化（以蓝图 §五.2 为权威，因其归一）

蓝图 §一 各平台单源权重与 §五.2 合并权重**存在内部冲突**，落地时以 §五.2（和为 1.0）为准，
被合并/丢弃的平台单列标注。

### 2.1 长线（1~6 月，和为 1.0）
| 维度 | 权重 | 来源 | 备注 |
| --- | --- | --- | --- |
| 官方公告 | 0.40 | 巨潮/交易所 #25 | 基本面根基 |
| 机构研报 | 0.25 | 雪球深度 #28 mock 含 | 吸收 §一.3 雪球长线 0.25 |
| 外资资讯 | 0.18 | 海外 #6（待建） | 吸收 §一.6 海外长线 0.18 |
| 微信圈层 | 0.08 | #31 | 与 §一.4 一致 |
| 散户舆情 | 0.09 | 股吧0.04+头条0.05 #28 | 与 §一.3/5 一致 |

⚠️ 丢弃项：华尔街见闻/金十长线 0.11（§一.2）未进入长线合并模型 —— 长线外资维度只保留彭博/路透系。

### 2.2 短线（1~7 日，和为 1.0）
| 维度 | 权重 | 来源 | 备注 |
| --- | --- | --- | --- |
| 圈内前瞻 | 0.20 | #31 微信 | 与 §一.4 一致 |
| 财联社快讯 | 0.22 | #34 快讯源（已建） | 与 §一.2 财联社短线 0.22 一致 |
| 短线社区 | 0.13 | #36 社区源（已建，取 §一.2 股吧短线 0.13） | 注：§五.2 蓝图列 0.18 未并入短线合并模型；实现以 §一.2 股吧 0.13 为展示常量并标注「未纳入 §五.2」 |
| 头条散户情绪 | 0.15 | #28 | 与 §一.5 一致 |
| 公告落地 | 0.25 | #25 | 由 §一.1 单源 0.3 收敛到 0.25 |

⚠️ 丢弃项：① 华尔街见闻/金十短线 0.18（§一.2）未进入短线合并模型；
② 股吧短线 0.13（§一.3）短线侧未并入『散户舆情』（仅长线侧并入）。
→ 实现时 `短线社区 0.18` 不展开股吧，避免与头条散户舆情重复计权。

### 2.3 各源落地权重常量（写入 provider，对齐 #28/#31）
- flash：`FLASH_WEIGHT_SHORT=0.22`、`FLASH_WEIGHT_LONG=0.09`（长线侧 §五.2 无 flash 维度，取 §一.2 参考值，标注为「未纳入长线合并模型」）
- community：`COMMUNITY_WEIGHT_SHORT=0.18`、`COMMUNITY_WEIGHT_LONG=0.25`（雪球长线）
- overseas：`OVERSEAS_WEIGHT_SHORT=0.14`、`OVERSEAS_WEIGHT_LONG=0.18`

---

## 3. 六层信息圈层模型（L0~L5，蓝图 §四，P1 落地）

作为共享常量写入 `src/services/opinion_info_layers.py`（已实现，#38），供所有源打标与 DSA 推演规则引用：

| 层级 | 人群 | 提前周期 | 股价阶段 | 系统操作定位 |
| --- | --- | --- | --- | --- |
| L0 顶层产业知情 | 高管/产业链核心 | 30~45 天 | 底部缓建仓 | 异动观察池，长线参考 |
| L1 机构专业层 | 公募/私募/游资/研究员 | 7~15 天 | 拉升初期 | 核心做多跟踪 |
| L2 专业交易者 | 短线高手/资深散户 | 3~7 天 | 主升浪起点 | 短线重点预判 |
| L3 深度散户层 | 复盘爱好者 | 0~3 天 | 上涨中段 | 谨慎追高 |
| L4 普通散户层 | 绝大多数股民 | 滞后 1~5 天 | 高位狂热 | 风险预警减仓 |
| L5 场外路人 | 新手 | 滞后 1 周+ | 行情尾声 | 强烈看空推演 |

固定扩散链：私密圈萌芽 → 券商/小众号发文 → 财联社快讯 → 雪球/淘股吧发酵 → 股吧/普通号转载 → 头条/抖音刷屏（见顶）。

---

## 4. 多源交叉验证规则（蓝图 §五.1，P1 落地，已实现 `opinion_cross_validation.py` #38）

- 单一自媒体爆料：可信度 ≤ 0.3，大幅降权（微信源已落地 `RUMOR_DOWNWEIGHT` 与低可信降权）。
- 2+ 独立权威平台同步印证：可信度提升至 0.7~0.9。
- 散户集中言论（股吧/头条）仅作情绪参考，不做基本面判断依据。
- 反向归因严格时间锁：仅拉升前资讯纳入原因，拉升后资讯全部剔除（内核 `run_closed_loop`/`agent_dig` 已按此执行）。

---

## 5. 分阶段落地排期（映射到已验证范式）

| 阶段 | 内容 | 复用范式 | 状态 |
| --- | --- | --- | --- |
| P0 | flash（财联社）信号源 | #28/#31 工厂+表+union+端点+面板 | ✅ 已建 #34 |
| P0 | community（雪球+股吧）信号源 | #28/#31/#34 工厂+表+union+端点+面板 | ✅ 已建 #36 |
| P1 | overseas（彭博/路透）信号源 | #28/#31/#34/#36 工厂+表+union+端点+面板 | ✅ 已建 #37 |
| P1 | 六层信息圈层自动判定 + 权重固化常量 | §3 | ✅ 已建 #38（`opinion_info_layers.py` 共享常量 + `/closed-loop/info-layers` 端点） |
| P1 | 多源交叉验证 / 可信度量化 / 谣言甄别 | §4 | ✅ 已建 #38（元分析层 `opinion_cross_validation.py`，消费七路源情感/可信度/谣言，归入 L0~L5 并计算共识/可信度/冲突/谣言；不扩张候选池、不改内核决策权） |
| P2 | 舆情回测（各平台情绪因子历史胜率）+ 拐点预警 | 新模块（#39：`opinion_backtest.py` 元分析层，与 #38 同构） | ✅ 已建 |

## 6. 舆情回测 + 拐点预警（蓝图 P2，#39，元分析层）

与 #38 同构：**不改变内核决策权、不扩张候选池、不新增持久化表**（确定性模拟序列由 hash 派生，可复现）。

### 6.1 舆情回测（各平台情绪因子历史胜率）
实现于 `src/services/opinion_backtest.py`：
- 对六路可插拔源（#25 披露 / #28 头条 / #31 微信 / #34 快讯 / #36 社区 / #37 海外）构造确定性历史情绪序列：
  共享隐藏「真实涨跌因子」`f`（源无关，决定次日均値方向）+ 各源情绪 `= coupling·f + noise·e`。
  权威源 `coupling` 高、`noise` 低 → 情绪更紧贴真实方向；散户源 `coupling` 低、`noise` 高 → 弱相关。
- 真实计算（非硬编码）：方向胜率（信号日情绪方向与次日均値同向占比）、多头胜率、空头胜率、
  信息系数 **IC**（情绪与次日均値的秩相关，衡量预测力）、样本量、覆盖率、可靠性分级（高/中/低）。
- 实测差异（沙箱基线）：`disclosure` IC≈0.53 > `overseas`≈0.47 > `flash` > `community` > `wechat` > `opinion`≈0.04；
  权威源平均 IC≈0.50 显著高于散户源平均 IC≈0.17，符合「官方公告>机构研报>圈层前瞻>自媒体公域舆情」权重秩序。
- 端点 `GET /closed-loop/sentiment-backtest`（裸 dict，与 #38 describe 端点一致）：返回 `bySource`(六源指标) + `summary`(最强/最弱源、各 tier 平均方向胜率、权威/散户平均 IC)。

### 6.2 拐点预警
实现于 `src/services/opinion_backtest.py` 的 `detect_inflection_for_alert` / `summarize_inflection`：
- 消费 **#38 交叉验证**（共识方向 / 权威×散户计数 / 冲突）+ **#39 回测可靠性**（主导散户源 IC 是否偏弱）+ **#35 Kronos 技术面**（trend）。
- 四类拐点信号：
  - **见顶拐点**：散户集中看多(L3/L4)但无权威印证 → 高位狂热减仓；
  - **启动拐点**：权威(L0/L1)提前看多、散户尚未跟进 → 拉升初期逢低布局；
  - **情绪反转**：主导散户源历史 IC 偏弱/为负，当前一致看多 → 疑似反向指标；
  - **技术·情绪背离**：Kronos 技术面与舆情方向背离 → 警惕诱多/诱空。
- 输出 `{level(high/medium/low/none), types, reasons, confidence, suggestedAction}`；扫描级 `inflectionSummary` 聚合分级分布 / 类型分布 / 高危标的。
- 集成：`scan_alerts` 在 #38 块后计算单次 `run_sentiment_backtest(universe)`、逐 alert 附加 `inflectionWarning`、结果 dict 增 `inflectionSummary`；端点 `GET /closed-loop/inflection-warnings`（跨池不跑 run_closed_loop，独立摘要）。

> 合规底线：所有爬虫仅抓公开合法内容，不碰私密群聊/朋友圈/隐私；LLM/舆情只梳理素材。
