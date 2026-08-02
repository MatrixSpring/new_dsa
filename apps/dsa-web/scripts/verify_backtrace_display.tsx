import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import BacktracePage from '../src/pages/BacktracePage';
import type { BacktraceSeed } from '../src/types/backtrace';
import seedRaw from './backtrace_seed.json';

const seed = seedRaw as unknown as BacktraceSeed;

function main() {
  // 分别渲染「个股」「板块」「回测」三个 Tab，确保全链路可见性可被断言
  const stockHtml = renderToStaticMarkup(
    React.createElement(BacktracePage, { seed, initialTab: 'stock' })
  );
  const sectorHtml = renderToStaticMarkup(
    React.createElement(BacktracePage, { seed, initialTab: 'sector' })
  );
  const backtestHtml = renderToStaticMarkup(
    React.createElement(BacktracePage, { seed, initialTab: 'backtest' })
  );
  const agentHtml = renderToStaticMarkup(
    React.createElement(BacktracePage, { seed, initialTab: 'agent' })
  );
  const factorHtml = renderToStaticMarkup(
    React.createElement(BacktracePage, { seed, initialTab: 'factor' })
  );
  const propagateHtml = renderToStaticMarkup(
    React.createElement(BacktracePage, { seed, initialTab: 'propagate' })
  );
  const loopHtml = renderToStaticMarkup(
    React.createElement(BacktracePage, { seed, initialTab: 'loop' })
  );
  const alertHtml = renderToStaticMarkup(
    React.createElement(BacktracePage, { seed, initialTab: 'alert' })
  );

  const checks: Array<[string, boolean]> = [
    ['页面标题', stockHtml.includes('大涨个股反向新闻归因回溯中心')],
    ['防幻觉标题', stockHtml.includes('外挂微服务，不改动 DSA 内核')],
    ['Tab 切换存在(板块)', stockHtml.includes('批量板块复盘')],
    ['Tab 切换存在(回测)', stockHtml.includes('归因回测校验')],
    // —— 个股 Tab ——
    ['回溯池首只标的', stockHtml.includes('中芯国际')],
    ['涨幅展示', stockHtml.includes('+9.83%')],
    ['模块①标题', stockHtml.includes('每日大涨回溯池')],
    ['驱动分类 badge', stockHtml.includes('基本面事件驱动')],
    ['趋势判断 badge', stockHtml.includes('长期主升')],
    ['核心强驱动因子', stockHtml.includes('核心强驱动')],
    ['情绪炒作因子', stockHtml.includes('情绪炒作')],
    ['权重合计护栏', stockHtml.includes('权重合计校验：100/100')],
    ['时间约束护栏', stockHtml.includes('时间约束：仅采用拉升前资讯')],
    ['事后新闻剔除护栏', stockHtml.includes('事后新闻已剔除')],
    ['相似历史对标区块', stockHtml.includes('相似历史行情对标')],
    ['DSA 调整建议区块', stockHtml.includes('DSA 模型参数调整建议')],
    ['联动按钮', stockHtml.includes('联动 DSA 系统')],
    ['联动四周期重算 chip', stockHtml.includes('四周期预测重算')],
    // —— 板块复盘 Tab (§3.6) ——
    ['板块景气判断', sectorHtml.includes('板块景气：')],
    ['景气值展示', sectorHtml.includes('景气主升') || sectorHtml.includes('景气上行') || sectorHtml.includes('情绪脉冲')],
    ['板块轮动逻辑区块', sectorHtml.includes('板块轮动逻辑')],
    ['上下游传导链区块', sectorHtml.includes('上下游传导链')],
    ['传导链节点', sectorHtml.includes('锂矿开采')],
    ['共同前置事件区块', sectorHtml.includes('共同前置事件分布')],
    ['共同催化项', sectorHtml.includes('业绩 / 订单超预期')],
    ['个股归因画像区块', sectorHtml.includes('板块内个股归因画像')],
    ['板块成分股', sectorHtml.includes('比亚迪') && sectorHtml.includes('宁德时代')],
    ['板块驱动分类 badge', sectorHtml.includes('基本面事件驱动')],
    // —— 归因回测校验 Tab (§3.7) ——
    ['回测选择框', backtestHtml.includes('选择归因记录：')],
    ['回测运行按钮', backtestHtml.includes('运行归因回测校验')],
    ['回测有效性判定', backtestHtml.includes('有效性判定：')],
    ['回测历史样本', backtestHtml.includes('历史样本：')],
    ['回测胜率指标', backtestHtml.includes('历史胜率')],
    ['回测期望收益指标', backtestHtml.includes('期望 1 月净收益')],
    ['回测置信度修正区块', backtestHtml.includes('置信度回测修正')],
    ['回测原置信度', backtestHtml.includes('归因原置信度')],
    ['回测修正后置信度', backtestHtml.includes('回测修正后')],
    ['回测匹配明细区块', backtestHtml.includes('驱动因子 → 历史样本桶匹配明细')],
    ['回测样本桶', backtestHtml.includes('业绩订单') || backtestHtml.includes('产业政策') || backtestHtml.includes('情绪游资')],
    // —— Agent 自主深挖 Tab（增强模块）——
    ['Tab 切换存在(Agent)', stockHtml.includes('Agent 深挖信号')],
    ['Agent 说明区块', agentHtml.includes('Agent 在反向回溯基础上')],
    ['Agent 运行按钮', agentHtml.includes('运行 Agent 自主深挖')],
    ['Agent 信号总数 badge', agentHtml.includes('隐藏信号总数：')],
    ['Agent 小众早期信号 badge', agentHtml.includes('小众早期信号：')],
    ['Agent 信号类型分布区块', agentHtml.includes('隐藏信号类型分布')],
    ['Agent 机构调研信号', agentHtml.includes('机构调研')],
    ['Agent 产业链异动信号', agentHtml.includes('产业链异动')],
    ['Agent 舆情小道消息信号', agentHtml.includes('舆情小道消息')],
    ['Agent 游资动向信号', agentHtml.includes('游资动向')],
    ['Agent 信号评分展示', agentHtml.includes('评分')],
    ['Agent 时间线区块', agentHtml.includes('拉升前隐藏信号时间线')],
    ['Agent 小众早期标记', agentHtml.includes('★ 小众早期信号') || agentHtml.includes('小众早期')],
    // —— 上涨因子库 Tab（增强模块）——
    ['Tab 切换存在(上涨因子库)', stockHtml.includes('上涨因子库')],
    ['因子库沉淀按钮', factorHtml.includes('沉淀上涨因子库')],
    ['因子库榜单区块', factorHtml.includes('标准化上涨因子库')],
    ['因子库预设因子展示', factorHtml.includes('业绩订单超预期') || factorHtml.includes('机构密集调研')],
    ['因子库出现次数列', factorHtml.includes('出现次数')],
    ['因子库历史胜率列', factorHtml.includes('历史胜率')],
    ['因子库置信度列', factorHtml.includes('置信度')],
    ['正向预判面板区块', factorHtml.includes('正向预判')],
    ['正向预判输入占位', factorHtml.includes('输入早期信号')],
    ['正向预判运行按钮', factorHtml.includes('运行正向预判')],
    ['正向预判概率指标', factorHtml.includes('预测上涨概率')],
    ['正向预判命中明细区块', factorHtml.includes('命中因子明细')],
    ['正向预判建议文本', factorHtml.includes('强信号') || factorHtml.includes('中性偏多') || factorHtml.includes('审慎')],
    // —— #24 因子库累积统计面板（数据驱动可视化）——
    ['因子库累积统计区块', factorHtml.includes('因子库累积统计')],
    ['累积统计·基类预设因子', factorHtml.includes('基类预设因子')],
    ['累积统计·真实归因落库', factorHtml.includes('真实归因落库')],
    ['累积统计·DB 新发掘因子', factorHtml.includes('DB 新发掘因子')],
    ['累积统计·被强化基线因子', factorHtml.includes('被强化基线因子')],
    ['累积统计·因子库总数', factorHtml.includes('因子库总数')],
    ['累积统计·数据驱动说明', factorHtml.includes('BacktraceAttribution')],
    // —— 因子传导 → DSA 内核 Tab（闭环增强，内核零改动）——
    ['Tab 切换存在(因子传导)', stockHtml.includes('因子传导 (内核)')],
    ['因子传导运行按钮', propagateHtml.includes('运行因子传导桥接')],
    ['因子传导说明区块', propagateHtml.includes('把 #17 沉淀的标准化上涨因子库')],
    ['因子传导冲击环节 badge', propagateHtml.includes('冲击环节：')],
    ['因子传导注入因子 badge', propagateHtml.includes('注入因子：')],
    ['因子传导增益 badge', propagateHtml.includes('冲击幅度增益')],
    ['因子传导对比区块', propagateHtml.includes('基线 vs 因子增强')],
    ['因子传导基线最大冲击指标', propagateHtml.includes('基线最大冲击')],
    ['因子传导增强最大冲击指标', propagateHtml.includes('增强最大冲击')],
    ['因子传导最大冲击提升指标', propagateHtml.includes('最大冲击提升')],
    ['因子传导四周期预测区块', propagateHtml.includes('四周期正向传导预测')],
    ['因子传导周期标签 1w', propagateHtml.includes('1w')],
    ['因子传导周期标签 1m', propagateHtml.includes('1m')],
    ['因子传导权重明细区块', propagateHtml.includes('注入 DSA 内核的因子权重')],
    ['因子传导注入因子展示', propagateHtml.includes('业绩订单超预期') || propagateHtml.includes('机构密集调研') || propagateHtml.includes('产业链供需缺口')],
    // —— #22 结构化边注入（按因子类别差异化增强对应边）——
    ['因子传导结构化注入区块', propagateHtml.includes('结构化边注入（#22') || propagateHtml.includes('结构化边注入')],
    ['因子传导类别→边拆解', propagateHtml.includes('类别 → 边 贡献拆解')],
    ['因子传导被注入边表头', propagateHtml.includes('覆盖系数')],
    ['因子传导边类型列', propagateHtml.includes('边类型')],
    ['因子传导基线系数列', propagateHtml.includes('基线系数')],
    ['因子传导结构化注入边 badge', propagateHtml.includes('结构化注入边：')],
    // —— 一键闭环 Tab（收尾闭环：深挖 → 预判 → 内核传导）——
    ['Tab 切换存在(一键闭环)', stockHtml.includes('一键闭环')],
    ['闭环运行按钮', loopHtml.includes('运行一键闭环')],
    ['闭环说明区块', loopHtml.includes('Agent 自主深挖') && loopHtml.includes('因子正向预判') && loopHtml.includes('DSA 内核传导')],
    ['闭环阶段一标题', loopHtml.includes('阶段一 · Agent 自主深挖')],
    ['闭环阶段二标题', loopHtml.includes('阶段二 · 因子正向预判')],
    ['闭环阶段三标题', loopHtml.includes('阶段三 · 因子')],
    ['闭环深挖信号 badge', loopHtml.includes('隐藏信号：')],
    ['闭环小众早期 badge', loopHtml.includes('小众早期：')],
    ['闭环预判概率指标', loopHtml.includes('预测上涨概率')],
    ['闭环注入因子 badge', loopHtml.includes('注入因子：')],
    ['闭环增益 badge', loopHtml.includes('冲击幅度增益')],
    ['闭环基线最大冲击指标', loopHtml.includes('基线最大冲击')],
    ['闭环增强最大冲击指标', loopHtml.includes('增强最大冲击')],
    ['闭环四周期预测区块', loopHtml.includes('四周期正向传导预测')],
    ['闭环注入因子明细区块', loopHtml.includes('注入 DSA 内核的因子权重（闭环联动）')],
    ['闭环结构化注入边 badge', loopHtml.includes('结构化注入边：')],
    // —— 自动化闭环预警扫描 Tab（#20：批量跑闭环并分级预警）——
    ['Tab 切换存在(自动化闭环预警)', stockHtml.includes('自动化闭环预警')],
    ['预警扫描运行按钮', alertHtml.includes('立即运行闭环预警（调度入口）')],
    ['预警扫描说明区块', alertHtml.includes('批量自动化预警')],
    ['预警概览 badge', alertHtml.includes('扫描标的：')],
    ['预警分级看板区块', alertHtml.includes('闭环预警分级看板')],
    ['预警综合评分表头', alertHtml.includes('综合评分')],
    ['预警级别展示', alertHtml.includes('强信号') || alertHtml.includes('中性') || alertHtml.includes('弱信号')],
    ['预警评分分布区块', alertHtml.includes('综合预警评分分布')],
    ['预警命中因子表头', alertHtml.includes('命中因子')],
    // —— 闭环预警自动化调度（#21：定时/事件触发 + 批次历史）——
    ['调度配置 badge', alertHtml.includes('调度配置：')],
    ['定时触发状态 badge', alertHtml.includes('定时触发：已启用')],
    ['立即运行按钮（调度入口）', alertHtml.includes('立即运行闭环预警（调度入口）')],
    ['调度 cron 展示', alertHtml.includes('cron：30 15 * * 1-5')],
    ['批次历史区块', alertHtml.includes('闭环预警扫描批次历史')],
    ['批次触发方式表头', alertHtml.includes('触发方式')],
    ['批次 Top 标的表头', alertHtml.includes('Top 标的')],
    ['批次运行时间表头', alertHtml.includes('运行时间')],
    ['批次历史含批次号', alertHtml.includes((seed.scanHistory && seed.scanHistory[0] && seed.scanHistory[0].batchId) || '__no_batch__')],
    // #23 可插拔数据源标识
    ['数据源 badge（模拟/实时）', alertHtml.includes('数据源：模拟') || alertHtml.includes('数据源：实时')],
    ['数据源 provider 标识', alertHtml.includes((seed.dataSource && seed.dataSource.provider) || '__no_provider__')],
    // —— #25 可插拔公开披露源（cninfo / 财报 / 研报）——
    ['公开披露数据源 badge', alertHtml.includes('公开披露：模拟') || alertHtml.includes('公开披露：实时')],
    ['公开披露面板标题', alertHtml.includes('公开披露催化事件池（#25')],
    ['公开披露说明文案', alertHtml.includes('扫描时作为基本面筛选叠加')],
    ['公开披露事件表头·标的', alertHtml.includes('标的')],
    ['公开披露事件表头·类别', alertHtml.includes('类别')],
    ['公开披露事件表头·情绪', alertHtml.includes('情绪')],
    ['公开披露事件·业绩预告', alertHtml.includes('业绩预告') || alertHtml.includes('重大合同') || alertHtml.includes('股权激励') || alertHtml.includes('财报') || alertHtml.includes('研报点评')],
    ['公开披露事件·利好情绪', alertHtml.includes('利好')],
    ['公开披露 provider 标识', alertHtml.includes((seed.disclosureSource && seed.disclosureSource.provider) || '__no_disc_provider__')],

    // —— #28 可插拔公开舆情源（头条爬虫 + FinBERT）——
    ['头条舆情数据源 badge', alertHtml.includes('头条舆情：模拟') || alertHtml.includes('头条舆情：实时')],
    ['头条舆情面板标题', alertHtml.includes('头条舆情催化事件池（#28')],
    ['头条舆情说明文案', alertHtml.includes('扫描时作为情绪面筛选叠加')],
    ['头条舆情事件表头·标的', alertHtml.includes('标的')],
    ['头条舆情事件表头·阶段', alertHtml.includes('阶段')],
    ['头条舆情事件表头·热度', alertHtml.includes('热度')],
    ['头条舆情事件·谣言降权', alertHtml.includes('疑似谣言')],
    ['头条舆情 provider 标识', alertHtml.includes((seed.opinionSource && seed.opinionSource.provider) || '__no_opinion_provider__')],
    ['预警分级看板·舆情催化列', alertHtml.includes('舆情催化')],

    // —— #31 可插拔微信私域舆情源（公众号/视频号爬虫 + FinBERT + 可信度分级）——
    ['微信舆情数据源 badge', alertHtml.includes('微信舆情：模拟') || alertHtml.includes('微信舆情：实时')],
    ['微信舆情面板标题', alertHtml.includes('微信舆情催化事件池（#31')],
    ['微信舆情说明文案', alertHtml.includes('仅公众号/视频号可抓取')],
    ['微信舆情事件表头·标的', alertHtml.includes('标的')],
    ['微信舆情事件表头·载体', alertHtml.includes('载体')],
    ['微信舆情事件表头·可信度', alertHtml.includes('可信度')],
    ['微信舆情事件·券商公众号载体', alertHtml.includes('券商公众号') || alertHtml.includes('产业垂直号') || alertHtml.includes('财经视频号') || alertHtml.includes('付费社群线索')],
    ['微信舆情事件·高可信', alertHtml.includes('高')],
    ['微信舆情事件·谣言降权', alertHtml.includes('疑似谣言')],
    ['微信舆情 provider 标识', alertHtml.includes((seed.wechatSource && seed.wechatSource.provider) || '__no_wechat_provider__')],
    ['预警分级看板·微信催化列', alertHtml.includes('微信催化')],

    // —— #34 可插拔短线快讯舆情源（财联社/华尔街见闻/金十爬虫 + 垂直媒体 + FinBERT + 谣言降权）——
    ['财联社快讯数据源 badge', alertHtml.includes('财联社快讯：模拟') || alertHtml.includes('财联社快讯：实时')],
    ['短线快讯面板标题', alertHtml.includes('短线快讯催化事件池（#34')],
    ['短线快讯说明文案', alertHtml.includes('财联社为 A 股短线第一舆情平台') || alertHtml.includes('扫描时作为短线情绪面筛选叠加')],
    ['短线快讯事件表头·标的', alertHtml.includes('标的')],
    ['短线快讯事件表头·类型', alertHtml.includes('类型')],
    ['短线快讯事件表头·突发', alertHtml.includes('突发')],
    ['短线快讯事件·深度媒体', alertHtml.includes('深度媒体')],
    ['短线快讯事件·盘中突发', alertHtml.includes('盘中突发')],
    ['短线快讯事件·谣言降权', alertHtml.includes('疑似谣言')],
    ['短线快讯 provider 标识', alertHtml.includes((seed.flashSource && seed.flashSource.provider) || '__no_flash_provider__')],
    ['预警分级看板·快讯催化列', alertHtml.includes('快讯催化')],

    // —— #36 可插拔深度社区舆情源（雪球/东财股吧/淘股吧爬虫 + 质量分层 + FinBERT + 谣言降权）——
    ['深度社区舆情数据源 badge', alertHtml.includes('深度社区舆情：模拟') || alertHtml.includes('深度社区舆情：实时')],
    ['深度社区舆情面板标题', alertHtml.includes('深度社区舆情催化事件池（#36')],
    ['深度社区舆情说明文案', alertHtml.includes('雪球偏理性中长线') || alertHtml.includes('扫描时作为社区情绪面筛选叠加')],
    ['深度社区事件表头·标的', alertHtml.includes('标的')],
    ['深度社区事件表头·平台', alertHtml.includes('平台')],
    ['深度社区事件表头·质量', alertHtml.includes('质量')],
    ['深度社区事件·雪球高质量', alertHtml.includes('雪球') && alertHtml.includes('高质量')],
    ['深度社区事件·登热榜', alertHtml.includes('登热榜')],
    ['深度社区事件·谣言降权', alertHtml.includes('疑似谣言')],
    ['深度社区 provider 标识', alertHtml.includes((seed.communitySource && seed.communitySource.provider) || '__no_community_provider__')],
    ['预警分级看板·社区热议列', alertHtml.includes('社区热议')],
    // —— #37 可插拔海外权威舆情源（彭博/路透/WSJ/Seeking Alpha 抓取 + 机构评级 + 外资流向）——
    ['海外权威数据源 badge', alertHtml.includes('海外权威：模拟') || alertHtml.includes('海外权威：实时')],
    ['海外权威面板标题', alertHtml.includes('海外权威资讯催化事件池（#37')],
    ['海外权威说明文案', alertHtml.includes('彭博/路透偏外资流向') || alertHtml.includes('长线外资维度')],
    ['海外权威事件表头·平台', alertHtml.includes('平台')],
    ['海外权威事件表头·机构', alertHtml.includes('机构')],
    ['海外权威事件表头·评级', alertHtml.includes('评级')],
    ['海外权威事件·彭博平台', alertHtml.includes('彭博')],
    ['海外权威 provider 标识', alertHtml.includes((seed.overseasSource && seed.overseasSource.provider) || '__no_overseas_provider__')],
    ['预警分级看板·海外权威列', alertHtml.includes('海外权威')],
    // —— #35 Kronos 技术面算力底座 ——
    ['Kronos 技术面 badge', alertHtml.includes('Kronos 技术面：')],
    ['Kronos 算力底座面板标题', alertHtml.includes('Kronos 技术面算力底座（#35 · DSA-KRONOS-V1.0）')],
    ['Kronos 风控约束声明', alertHtml.includes('Kronos 仅输出技术参考，最终涨跌量化')],
    ['Kronos 三类选股池·短线强势池', alertHtml.includes('短线强势池')],
    ['Kronos 三类选股池·趋势反转池', alertHtml.includes('趋势反转池')],
    ['Kronos 三类选股池·风险预警池', alertHtml.includes('风险预警池')],
    ['预警分级看板·Kronos趋势列', alertHtml.includes('Kronos趋势')],
    ['预警分级看板·Kronos拐点列', alertHtml.includes('拐点')],
    ['预警分级看板·Kronos涨概列', alertHtml.includes('Kronos涨概')],
    // —— #38 六层信息圈层 + 多源交叉验证（元分析层）——
    ['六层信息圈层面板标题', alertHtml.includes('六层信息圈层 + 多源交叉验证（#38')],
    ['圈层命中矩阵·六层标签', alertHtml.includes('顶层产业知情') && alertHtml.includes('场外路人')],
    ['共识分布·强共识标签', alertHtml.includes('强共识（2+权威）')],
    ['交叉验证指标·权威×散户冲突', alertHtml.includes('权威×散户冲突')],
    ['交叉验证指标·谣言待甄别', alertHtml.includes('谣言待甄别')],
    ['§4 可信度阈值说明', alertHtml.includes('单一自媒体/散户爆料')],
    ['预警分级看板·共识列', alertHtml.includes('共识/可信度')],
    ['预警分级看板·共识badge(强/中/弱)', alertHtml.includes('强共识') || alertHtml.includes('中等') || alertHtml.includes('弱(散户)')],
    // —— #39 舆情回测 + 拐点预警（P2）——
    ['舆情回测面板标题', alertHtml.includes('舆情回测 + 拐点预警（#39')],
    ['舆情回测表·方向胜率列', alertHtml.includes('方向胜率')],
    ['舆情回测表·IC列', alertHtml.includes('IC')],
    ['舆情回测表·可靠性列', alertHtml.includes('可靠性')],
    ['舆情回测·最强预测源摘要', alertHtml.includes('最强预测源')],
    ['拐点预警面板·摘要标题', alertHtml.includes('拐点预警摘要')],
    ['拐点预警·类型标签(技术·情绪背离)', alertHtml.includes('技术·情绪背离')],
    ['预警分级看板·拐点预警列', alertHtml.includes('拐点预警')],
  ];

  let ok = true;
  for (const [name, pass] of checks) {
    console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}`);
    if (!pass) ok = false;
  }
  console.log(`\nDISPLAY_CHECKS=${checks.length}`);
  console.log(ok ? 'DISPLAY_OK' : 'DISPLAY_FAIL');
  process.exit(ok ? 0 : 1);
}

main();
