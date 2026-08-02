/**
 * 前端「数据 → 显示」验证：tsc 编译 + react-dom/server SSR 渲染 JobBoard，
 * 断言任务名 / 触发标签 / 状态出现在 HTML。
 */
import { renderToStaticMarkup } from 'react-dom/server';
import JobBoard from '../src/components/scheduler/JobBoard';
import type { SchedulerJob } from '../src/types/scheduler';

const sampleJobs: SchedulerJob[] = [
  {
    id: 'daily_analysis',
    name: '每日主分析流水线',
    group: 'core',
    description: '抓取-入库-推演-预测-复盘全自动闭环',
    trigger: { kind: 'daily', time: '18:00' },
    triggerLabel: '每日 18:00',
    enabled: true,
    lastRunAt: '2026-08-01T18:00:12',
    lastStatus: 'success',
    nextRunAt: '2026-08-02T18:00:00',
    runCount: 42,
  },
  {
    id: 'weekly_report_compare',
    name: '周报多文档交叉对比',
    group: 'crawl',
    description: '周日汇总一周行业研报，批量交叉对比',
    trigger: { kind: 'weekly', dow: 6, time: '19:30' },
    triggerLabel: '每周周日 19:30',
    enabled: true,
    lastRunAt: null,
    lastStatus: null,
    nextRunAt: '2026-08-02T19:30:00',
    runCount: 0,
  },
  {
    id: 'agent_event_monitor',
    name: '事件监控后台任务',
    group: 'monitor',
    description: '分钟级轮询重大事件并触发预警',
    trigger: { kind: 'interval', seconds: 300 },
    triggerLabel: '每 5 分钟',
    enabled: false,
    lastRunAt: '2026-08-01T12:00:00',
    lastStatus: 'success',
    nextRunAt: null,
    runCount: 128,
  },
];

function main() {
  const html = renderToStaticMarkup(JobBoard({ jobs: sampleJobs }));
  const checks: [string, boolean][] = [
    ['job_name', html.includes('每日主分析流水线')],
    ['weekly_label', html.includes('每周周日 19:30')],
    ['interval_label', html.includes('每 5 分钟')],
    ['enabled', html.includes('启用')],
    ['disabled', html.includes('停用')],
    ['next_run', html.includes('2026-08-02 18:00:00')],
    ['run_count', html.includes('>42<')],
    ['job_row_testid', html.includes('job-daily_analysis')],
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
  console.log(`DISPLAY_OK html_len=${html.length} checks=${checks.length}`);
}

main();
