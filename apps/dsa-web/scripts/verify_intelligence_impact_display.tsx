import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import IntelligenceImpactPanel from '../src/components/IntelligenceImpactPanel';
import type { IntelligenceImpact } from '../src/types/intelligenceImpact';

const seed: IntelligenceImpact[] = [
  { id: 1, itemId: 'itm_1', impactLevel: '高', impactCycle: '2w', impactIndustry: 'sw_bank', impactDirection: '利好', transmitWeight: 0.85, gradedAt: '2026-08-02T15:00:00', title: '央行超预期降准' },
  { id: 2, itemId: 'itm_2', impactLevel: '中', impactCycle: '2w', impactIndustry: 'sw_chemical', impactDirection: '利空', transmitWeight: 0.5, gradedAt: '2026-08-02T15:00:00', title: '某龙头减产' },
  { id: 3, itemId: 'itm_3', impactLevel: '低', impactCycle: '2w', impactIndustry: null, impactDirection: '中性', transmitWeight: 0.35, gradedAt: '2026-08-02T15:00:00', title: '日常惯例公告' },
];

function main() {
  const html = renderToStaticMarkup(
    React.createElement(IntelligenceImpactPanel, { seedData: seed })
  );

  const checks: [string, boolean][] = [
    ['panel', html.includes('情报结构化分级')],
    ['impact-itm_1', html.includes('impact-itm_1')],
    ['title', html.includes('央行超预期降准')],
    ['direction-利好', html.includes('利好')],
    ['direction-利空', html.includes('利空')],
    ['direction-中性', html.includes('中性')],
    ['level-高', html.includes('等级 高')],
    ['weight', html.includes('传导 85%')],
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
  console.log(`DISPLAY_OK html=${html.length} checks=${checks.length}`);
}

main();
