/**
 * 数据→显示 验证（不依赖 vite/esbuild/vitest）：
 * 用 tsc 编译为 CJS 后，以 react-dom/server 将纯展示组件渲染为静态 HTML，
 * 断言后端返回的结构化数据（情报 / 市场趋势 / 政策赛道 / 个股 / 资金博弈 / 风控）确实出现在 DOM。
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  IntelligenceFeed,
  MarketTrendPanel,
  PolicyTrackPanel,
  StockRecentPanel,
  GameShortPanel,
  GameLongPanel,
  RiskOverviewPanel,
} from '../src/components/dynamics/DynamicsViews';
import type {
  GameLongData,
  GameShortData,
  IntelligenceItemList,
  MarketTrendData,
  PolicyTrackData,
  RiskOverviewData,
  StockRecentData,
} from '../src/types/dynamics';

const intel: IntelligenceItemList = {
  items: [
    { id: 1, sourceType: 'policy', title: '美联储维持利率不变，点阵图暗示年内两次降息', summary: '海外宏观政策落地。', url: 'https://e/1', source: 'Reuters', publishedAt: '2026-08-01T20:00:00', scopeType: 'market', scopeValue: 'us', market: 'us' },
    { id: 2, sourceType: 'industry', title: '工信部发布人形机器人产业中长期发展规划', summary: '明确 2027/2030 产能目标。', url: 'https://e/2', source: '工信部', publishedAt: '2026-08-01T09:30:00', scopeType: 'sector', scopeValue: 'robotics', market: 'cn' },
    { id: 3, sourceType: 'event', title: '中东地缘冲突升级，原油供给收紧预期升温', summary: '地缘事件驱动。', url: 'https://e/3', source: 'Bloomberg', publishedAt: '2026-07-31T22:10:00', scopeType: 'market', scopeValue: 'global', market: 'global' },
  ],
  total: 3, page: 1, pageSize: 50,
};

const marketTrend: MarketTrendData = {
  indexList: [{ name: '上证指数', code: '000001', trend: [], changePct: 1.2 }],
  trendScore: 58.5,
  trendStatus: '偏强',
  industryHotList: [{ name: '半导体', boomScore: 82, rankDesc: '领涨' }],
  abnormalTip: '',
};

const policyTrack: PolicyTrackData = {
  tracks: [{ trackName: '半导体国产化', policyDesc: '加速替代', policyLevel: '强力支持', trendScore: 70, financeScore: 60, fundScore: 55, boomScore: 80, rankDesc: '景气上行', topStockList: [] }],
};

const stockRecent: StockRecentData = {
  type: 'select',
  stocks: [{ stockCode: '600519', stockName: '贵州茅台', price: 1700, changeRate: 1.5, volumeRatio: 1.2, rsi: 55, mainNetIn: 3.2e8, riskLevel: '中', totalScore: 78, industry: '白酒', filterReason: '', isAbnormal: false }],
};

const gameShort: GameShortData = {
  mainFundList: [{ code: '600519', name: '贵州茅台', mainNetIn: 5e8, turnover: 1e9 }],
  northFundList: [{ code: '000001', name: '平安银行', northNetIn: 2e8 }],
  gameScore: 62,
  abnormalStockList: [],
};

const gameLong: GameLongData = {
  industryRotateList: [{ name: '新能源', boomScore: 70, fundScore: 65, rankDesc: '轮动' }],
  institutionTrackList: [],
  baseGameScore: 55,
};

const riskOverview: RiskOverviewData = {
  riskStat: { 高: 3, 中: 12, 低: 30 },
  riskStockList: [],
  systemRisk: { interfaceFailRate: 1.2, cacheHitRate: 98.5, reconnectCount: 0 },
  blackListCount: 2,
};

const html = renderToStaticMarkup(
  React.createElement(
    'div',
    null,
    React.createElement(IntelligenceFeed, { data: intel }),
    React.createElement(MarketTrendPanel, { data: marketTrend }),
    React.createElement(PolicyTrackPanel, { data: policyTrack }),
    React.createElement(StockRecentPanel, { data: stockRecent }),
    React.createElement(GameShortPanel, { data: gameShort }),
    React.createElement(GameLongPanel, { data: gameLong }),
    React.createElement(RiskOverviewPanel, { data: riskOverview }),
  )
);

const mustContain = [
  '工信部发布人形机器人产业中长期发展规划', // 情报标题
  '中国', // cn 市场徽标
  '全球', // global 市场徽标
  '美股', // us 市场徽标
  '趋势评分', // 市场趋势
  '58.5', // trendScore 数值
  '半导体', // 行业热度
  '国家政策赛道', // 政策赛道
  '半导体国产化', // track 名
  '个股速览', // 个股
  '600519', // 股票代码
  '短线资金博弈', // 短线资金
  '博弈评分',
  '长线赛道轮动', // 长线
  '基础博弈分',
  '风控概览', // 风控
  '接口失败率',
];

const missing = mustContain.filter((s) => !html.includes(s));
if (missing.length > 0) {
  console.error('DISPLAY_FAIL missing:', missing);
  console.error('HTML_LEN', html.length);
  process.exit(1);
}
console.log('DISPLAY_OK html_len=' + html.length + ' panels=7 intel_items=' + intel.items.length);
