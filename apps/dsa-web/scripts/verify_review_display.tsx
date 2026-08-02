/**
 * 前端「数据 → 显示」验证：tsc 编译 + react-dom/server SSR 渲染
 * ReviewReportView + ReviewScoreView，断言准确率 / 三层归因 / 周期命中率出现。
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { ReviewReportView, ReviewScoreView } from '../src/components/review/ReviewBoard';
import type {
  ReviewReportData,
  ReviewScoreData,
} from '../src/types/review';

const report: ReviewReportData = {
  total: 2,
  accuracyRate: 0.75,
  avgLayerHealth: { data_layer: 0.6, model_layer: 0.55, logic_layer: 0.8 },
  weakestLayer: 'model_layer',
  byCycle: {
    '1w': { n: 2, accuracyRate: 0.5, directionHitRate: 0.5, rangeHitRate: 0.5 },
    '1m': { n: 2, accuracyRate: 1.0, directionHitRate: 1.0, rangeHitRate: 1.0 },
    '6m': { n: 1, accuracyRate: 1.0, directionHitRate: 1.0, rangeHitRate: 1.0 },
  },
};

const score: ReviewScoreData = {
  symbol: '600519',
  name: '贵州茅台',
  scoredAt: 0,
  cycles: [
    {
      cycle: '1w',
      predictedDirection: 'up',
      actualDirection: 'up',
      actualReturnPct: 4.2,
      directionHit: true,
      rangeHit: true,
      accuracyScore: 1.0,
      attribution: {
        dataLayer: { score: 0.7, note: '共识分充足' },
        modelLayer: { score: 0.8, note: '方向命中，DSA 稳定' },
        logicLayer: { score: 1.0, note: '传导路径一致' },
      },
    },
    {
      cycle: '1m',
      predictedDirection: 'up',
      actualDirection: 'oscillation',
      actualReturnPct: 1.1,
      directionHit: true,
      rangeHit: false,
      accuracyScore: 0.5,
      attribution: {
        dataLayer: { score: 0.55, note: '共识分偏低' },
        modelLayer: { score: 0.7, note: '方向命中' },
        logicLayer: { score: 0.5, note: '波动区间偏差' },
      },
    },
  ],
  accuracyRate: 0.75,
  avgLayerHealth: { data_layer: 0.625, model_layer: 0.75, logic_layer: 0.75 },
  weakestLayer: 'data_layer',
  sampleSize: 2,
};

function main() {
  const htmlRep = renderToStaticMarkup(ReviewReportView({ data: report }));
  const htmlScore = renderToStaticMarkup(ReviewScoreView({ data: score }));
  const checks: [string, boolean][] = [
    ['acc_rate', htmlRep.includes('75.0%')],
    ['weakest', htmlRep.includes('模型层')],
    ['layer_data', htmlRep.includes('数据层')],
    ['layer_logic', htmlRep.includes('逻辑层')],
    ['by_cycle_1w', htmlRep.includes('1w')],
    ['score_symbol', htmlScore.includes('600519')],
    ['direction_hit', htmlScore.includes('方向✓')],
    ['range_miss', htmlScore.includes('区间✗')],
    ['attribution_note', htmlScore.includes('传导路径一致')],
  ];
  let ok = true;
  for (const [name, pass] of checks) {
    if (!pass) {
      ok = false;
      console.log('MISSING:', name);
    }
  }
  if (!ok) {
    console.log('DISPLAY_FAIL');
    process.exit(1);
  }
  console.log(`DISPLAY_OK html_rep=${htmlRep.length} html_score=${htmlScore.length} checks=${checks.length}`);
}

main();
