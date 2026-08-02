/**
 * 数据→显示 验证（不依赖 vite/esbuild/vitest）：
 * 用 tsc 编译后，以 react-dom/server 将纯展示组件 ForecastTable 渲染为静态 HTML，
 * 断言后端返回的四周期标准化预测字段确实出现在 DOM 中。
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ForecastTable } from '../src/components/forecast/ForecastViews';
import type { SymbolForecast } from '../src/types/forecast';

const symbolsData: Record<string, SymbolForecast> = {
  '600519': {
    symbol: '600519',
    name: '600519',
    market: 'A',
    cycles: {
      '1w': { cycle: '1w', cycleDays: 5, designDays: 5, direction: 'up', directionLabel: '震荡偏强', consensusScore: 0.62, upProbability: 65, confidence: 0.72, priceRange: { low: 1680, high: 1750 }, volatilityRangePct: { low: 0.02, high: 0.04 }, coreDrivers: ['地缘原油涨价'], mainRisks: ['美联储临时讲话'], subModelScores: { timing: 0.6, fund_flow: 0.7 } },
      '2w': { cycle: '2w', cycleDays: 10, designDays: 10, direction: 'up', directionLabel: '上行', consensusScore: 0.7, upProbability: 70, confidence: 0.75, priceRange: { low: 1670, high: 1780 }, volatilityRangePct: { low: 0.03, high: 0.07 }, coreDrivers: ['行业涨价落地'], mainRisks: ['产能临时投放'], subModelScores: { timing: 0.65, fund_flow: 0.68 } },
      '1m': { cycle: '1m', cycleDays: 22, designDays: 22, direction: 'up', directionLabel: '稳步上行', consensusScore: 0.76, upProbability: 76, confidence: 0.78, priceRange: { low: 1650, high: 1820 }, volatilityRangePct: { low: 0.06, high: 0.12 }, coreDrivers: ['财报高增'], mainRisks: ['需求不及预期'], subModelScores: { timing: 0.7, fund_flow: 0.66 } },
      '6m': { cycle: '6m', cycleDays: 120, designDays: 120, direction: 'up', directionLabel: '趋势上行', consensusScore: 0.81, upProbability: 81, confidence: 0.83, priceRange: { low: 1600, high: 1900 }, volatilityRangePct: { low: 0.15, high: 0.3 }, coreDrivers: ['长期产业扶持'], mainRisks: ['全球经济衰退'], subModelScores: { timing: 0.8, fund_flow: 0.6 } },
    },
  },
};

const html = renderToStaticMarkup(
  React.createElement(ForecastTable, {
    symbolsData,
    selectedCycle: '1w',
    onSelectCycle: () => {},
  })
);

const mustContain = [
  'row-600519',
  'cell-600519-1w',
  'cell-600519-6m',
  '1周',
  '半月',
  '1月',
  '半年',
  '震荡偏强',
  '65%',
  '72%',
  '区间',
  '600519',
];

const missing = mustContain.filter((s) => !html.includes(s));
if (missing.length > 0) {
  console.error('DISPLAY_FAIL missing:', missing);
  console.error('HTML_LEN', html.length);
  process.exit(1);
}
console.log('DISPLAY_OK html_len=' + html.length + ' symbols=1 cycles=4');
