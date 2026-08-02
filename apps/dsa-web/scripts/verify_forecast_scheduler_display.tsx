import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ForecastCenterPage from '../src/pages/ForecastCenterPage';
import JobBoard from '../src/components/scheduler/JobBoard';
import type { ForecastSnapshotResponse } from '../src/types/forecastSnapshot';
import type { SchedulerJob, SchedulerJobRun } from '../src/types/scheduler';

// #8 前瞻预测中心 mock（seedData 注入，跳过 api 调用）
const fcSeed: ForecastSnapshotResponse = {
  code: 0,
  total: 8,
  items: [
    { id: 1, scopeType: 'stock', scopeValue: '600519', cycle: '1w', direction: 'up', lowPct: 1.2, highPct: 4.5, upProb: 0.62, confidence: 0.58, coreDriver: '资金博弈', mainRisk: '地缘', generatedAt: '2026-08-02T15:00:00', jobRunId: 'seed' },
    { id: 2, scopeType: 'stock', scopeValue: '600519', cycle: '6m', direction: 'up', lowPct: 2.0, highPct: 18.0, upProb: 0.64, confidence: 0.48, coreDriver: '产能', mainRisk: '外需', generatedAt: '2026-08-02T15:00:00', jobRunId: 'seed' },
    { id: 3, scopeType: 'industry', scopeValue: 'sw_computers', cycle: '1m', direction: 'oscillation', lowPct: -3.0, highPct: 5.0, upProb: 0.52, confidence: 0.5, coreDriver: '景气分化', mainRisk: '需求', generatedAt: '2026-08-02T15:00:00', jobRunId: 'seed' },
    { id: 4, scopeType: 'event', scopeValue: 'evt_rate_cut', cycle: '2w', direction: 'up', lowPct: 0.5, highPct: 6.0, upProb: 0.6, confidence: 0.55, coreDriver: '政策', mainRisk: '财报', generatedAt: '2026-08-02T15:00:00', jobRunId: 'seed' },
  ],
  byCycle: [
    { cycle: '1w', total: 1, directionCounts: { up: 1, down: 0, oscillation: 0 }, avgConfidence: 0.58 },
    { cycle: '2w', total: 1, directionCounts: { up: 1, down: 0, oscillation: 0 }, avgConfidence: 0.55 },
    { cycle: '1m', total: 1, directionCounts: { up: 0, down: 0, oscillation: 1 }, avgConfidence: 0.5 },
    { cycle: '6m', total: 1, directionCounts: { up: 1, down: 0, oscillation: 0 }, avgConfidence: 0.48 },
  ],
};

// #9 JobBoard mock
const jobs: SchedulerJob[] = [
  { id: 'daily_analysis', name: '每日主分析', group: 'core', description: '18:00 主分析', trigger: { kind: 'daily', time: '18:00' }, triggerLabel: '每天 18:00', enabled: true, lastRunAt: '2026-08-02T18:00:00', lastStatus: 'success', nextRunAt: '2026-08-03T18:00:00', runCount: 12 },
  { id: 'event_monitor', name: '事件监控', group: 'monitor', description: '5min', trigger: { kind: 'interval', seconds: 300 }, triggerLabel: '每 5 分钟', enabled: true, lastRunAt: '2026-08-02T15:40:00', lastStatus: 'success', nextRunAt: '2026-08-02T15:45:00', runCount: 200 },
];
const runs: SchedulerJobRun[] = [
  { id: 1, jobKey: 'daily_analysis', startedAt: '2026-08-02T18:00:00', finishedAt: '2026-08-02T18:05:00', status: 'success', summary: '每日主分析完成', error: null },
  { id: 2, jobKey: 'event_monitor', startedAt: '2026-08-02T15:40:00', finishedAt: null, status: 'failed', summary: null, error: 'timeout' },
];

function main() {
  const htmlFc = renderToStaticMarkup(
    React.createElement(ForecastCenterPage, { seedData: fcSeed })
  );
  const htmlJob = renderToStaticMarkup(
    React.createElement(JobBoard, { jobs, runs })
  );

  const checks: [string, boolean][] = [
    // #8
    ['fc-title', htmlFc.includes('前瞻预测中心')],
    ['fc-cycle-1w', htmlFc.includes('fc-cycle-1w')],
    ['fc-cycle-6m', htmlFc.includes('fc-cycle-6m')],
    ['fc-scope-600519', htmlFc.includes('fc-scope-600519')],
    ['fc-direction-up', htmlFc.includes('看多')],
    ['fc-oscillation', htmlFc.includes('震荡')],
    ['fc-confidence', htmlFc.includes('置信')],
    // #9
    ['job-board', htmlJob.includes('job-board')],
    ['job-daily', htmlJob.includes('job-daily_analysis')],
    ['runs-title', htmlJob.includes('最近运行日志')],
    ['run-success', htmlJob.includes('run-1')],
    ['run-failed-status', htmlJob.includes('failed')],
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
  console.log(
    `DISPLAY_OK html_fc=${htmlFc.length} html_job=${htmlJob.length} checks=${checks.length}`
  );
}

main();
