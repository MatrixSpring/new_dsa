import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import CrawlCenterPage from '../src/pages/CrawlCenterPage';
import type { CrawlDocument, CrawlSource } from '../src/types/crawl';

const seedSources: CrawlSource[] = [
  { key: 'cninfo_announcement', name: '交易所官方公告', docType: 'policy', adapter: 'cninfo', description: '巨潮公告' },
  { key: 'morning_notes', name: '券商晨会纪要', docType: 'minutes', adapter: 'astock', description: '晨会纪要' },
  { key: 'broker_research', name: '券商深度研报', docType: 'report', adapter: 'astock', description: '深度研报' },
];

const seedDocuments: CrawlDocument[] = [
  {
    id: 1,
    sourceKey: 'cninfo_announcement',
    title: '关于新能源汽车购置补贴实施细则的公告',
    docType: 'policy',
    status: 'parsed',
    error: null,
    fetchedAt: '2026-08-02T15:58:01',
    parsedAt: '2026-08-02T15:58:02',
    rawLength: 151,
    parsed: {
      docId: 'crawl-cninfo_announcement',
      docType: 'policy',
      shortTerm1w: '每辆新能源乘用车补贴 1 万元，实施期至 2027 年底',
      midTerm1m: '本地配套率不低于 40% 方可享受补贴',
      longTermHalfyear: '龙头企业 2027 年产能达 500GWh',
      hiddenConstraint: '本地配套率不低于 40%',
      potentialRisk: '若出口限制加码，产业链将面临价格下行压力',
      reliability: '40%',
    },
  },
];

function main() {
  const html = renderToStaticMarkup(
    React.createElement(CrawlCenterPage, { seed: { sources: seedSources, documents: seedDocuments } })
  );

  const checks: [string, boolean][] = [
    ['center', html.includes('自动爬虫')],
    ['source-cninfo', html.includes('source-cninfo_announcement')],
    ['run-cninfo', html.includes('run-cninfo_announcement')],
    ['doc-1', html.includes('doc-1')],
    ['title', html.includes('关于新能源汽车购置补贴实施细则的公告')],
    ['short_term', html.includes('每辆新能源乘用车补贴 1 万元')],
    ['long_term', html.includes('500GWh')],
    ['constraint', html.includes('本地配套率不低于 40%')],
    ['risk', html.includes('出口限制加码')],
    ['reliability', html.includes('40%')],
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
