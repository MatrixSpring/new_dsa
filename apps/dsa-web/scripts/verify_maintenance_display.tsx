/**
 * 前端「数据 → 显示」验证：tsc 编译 + react-dom/server SSR 渲染
 * #5 产业链维护 / #6 公司维护 / #7 DSA 全局参数（含 seed 数据，断言关键字段出现）。
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import IndustryMaintenancePage from '../src/pages/IndustryMaintenancePage';
import CompanyMaintenancePage from '../src/pages/CompanyMaintenancePage';
import DsaParamsPage from '../src/pages/DsaParamsPage';
import type { ChainEdgeOverride, ChainRiskFlag, IndustryChainListItem } from '../src/types/industryChain';
import type { CompanyDetail } from '../src/types/company';
import type { DsaParam } from '../src/types/dsaParams';

const chain: IndustryChainListItem = {
  id: 'lithium', name: '锂电池产业链', icon: '🔋', color: '190 100% 50%',
  category: '内置 · 产业链沙盘', l1: '内置', l2: '', summary: '锂电', source: 'sandbox', nodeCount: 14,
};
const overrides: ChainEdgeOverride[] = [
  { id: 1, chainId: 'lithium', sourceNode: '锂矿', targetNode: '正极材料', coeff: 0.85, lag: 3, updatedAt: null },
];
const flags: ChainRiskFlag[] = [
  { id: 1, chainId: 'lithium', node: '碳酸锂', riskType: 'price_up', severity: '高', note: '价格上涨超阈值', createdAt: '2026-08-02' },
];

const company: CompanyDetail = {
  code: '600519', name: '贵州茅台', pe: 25, pb: 9, ps: 12, price: 1680,
  totalMarketCap: 2100000000000, floatMarketCap: 2100000000000,
  consensusRating: '买入', consensusTargetPrice: 2000, esgRating: 'AAA',
  linkedChainsCount: 3, dataSources: ['industry_chain_fusion'],
  riskTags: [
    { tag: '增长', level: '利好', note: '文本命中关键词「增长」', source: 'heuristic' },
    { tag: '下滑', level: '利空', note: '文本命中关键词「下滑」', source: 'heuristic' },
  ],
};

const params: DsaParam[] = [
  { id: 1, paramKey: 'recursion_depth', paramValue: 20, paramDesc: 'DSA 传导递归深度上限', updatedAt: null },
  { id: 2, paramKey: 'coeff_threshold', paramValue: 0.85, paramDesc: '双向传导系数阈值', updatedAt: null },
];

function main() {
  const htmlIm = renderToStaticMarkup(
    React.createElement(IndustryMaintenancePage, { seed: { chains: [chain], overrides, flags } })
  );
  const htmlCm = renderToStaticMarkup(
    React.createElement(CompanyMaintenancePage, { seed: { detail: company } })
  );
  const htmlDp = renderToStaticMarkup(
    React.createElement(DsaParamsPage, { seed: { params } })
  );

  const checks: [string, boolean][] = [
    ['im_title', htmlIm.includes('产业链信息维护')],
    ['im_edge_panel', htmlIm.includes('自定义传导系数')],
    ['im_override_val', htmlIm.includes('锂矿') && htmlIm.includes('正极材料') && htmlIm.includes('0.85')],
    ['im_risk_panel', htmlIm.includes('产业链环节风险标记')],
    ['im_flag', htmlIm.includes('碳酸锂') && htmlIm.includes('价格上涨超阈值')],
    ['im_export', htmlIm.includes('一键导出画布模板')],

    ['cm_title', htmlCm.includes('公司信息维护')],
    ['cm_name', htmlCm.includes('贵州茅台')],
    ['cm_good', htmlCm.includes('利好') && htmlCm.includes('增长')],
    ['cm_bad', htmlCm.includes('利空') && htmlCm.includes('下滑')],
    ['cm_recognize', htmlCm.includes('自动识别写库')],

    ['dp_title', htmlDp.includes('DSA 全局模型参数')],
    ['dp_key', htmlDp.includes('coeff_threshold')],
    ['dp_val', htmlDp.includes('0.85')],
    ['dp_seed', htmlDp.includes('写入种子参数')],
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
    `DISPLAY_OK html_im=${htmlIm.length} html_cm=${htmlCm.length} html_dp=${htmlDp.length} checks=${checks.length}`
  );
}

main();
