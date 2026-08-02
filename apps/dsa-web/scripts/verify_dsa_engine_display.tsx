/**
 * 前端「数据 → 显示」验证：react-dom/server SSR 渲染
 * #12 DSA 传导引擎（设计 §3.1 引擎规则 + 三情景并行传导），含 seed 数据，断言关键字段出现。
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import DsaEnginePage from '../src/pages/DsaEnginePage';
import type { PropagateResult, ScenarioResult } from '../src/types/industryChain';
import seedRaw from './dsa_engine_seed.json';

const seedJson: any = seedRaw;
const propagate = seedJson.propagate as PropagateResult;
const scenarios = seedJson.scenarios as ScenarioResult;

function main() {
  const html = renderToStaticMarkup(
    React.createElement(DsaEnginePage, {
      seed: {
        chains: seedJson.chains,
        params: seedJson.params,
        propagate,
        scenarios,
      },
    })
  );

  const checks: [string, boolean][] = [
    ['engine_title', html.includes('DSA 传导引擎')],
    ['rule_depth', html.includes('递归深度')],
    ['rule_bidirectional', html.includes('双向衰减')],
    ['rule_bearish', html.includes('利空衰减')],
    ['rule_coeff_range', html.includes('系数区间')],
    ['rule_override', html.includes('覆盖系数接入')],
    ['single_title', html.includes('单冲击传导结果')],
    ['single_shock', html.includes(propagate.shockLabel || '')],
    ['single_summary', html.includes('受影响环节') && html.includes('受影响公司')],
    ['single_top_nodes', html.includes('Top 环节冲击')],
    ['single_top_companies', html.includes('Top 公司冲击')],
    ['scenario_title', html.includes('三情景并行传导')],
    ['scenario_base', html.includes('基准 Base')],
    ['scenario_optimistic', html.includes('乐观 Optimistic')],
    ['scenario_pessimistic', html.includes('悲观 Pessimistic')],
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
    `DISPLAY_OK html=${html.length} checks=${checks.length} shock=${propagate.shockLabel} ` +
    `impacted=${propagate.summary.impactedNodes} companies=${propagate.summary.affectedCompanies}`
  );
}

main();
