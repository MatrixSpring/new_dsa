/**
 * 前端「数据 → 显示」验证：用 tsc 编译为 CJS + react-dom/server SSR 渲染
 * 纯展示组件 ParseResultView，断言解析结果关键字段出现在 HTML。
 *
 * 运行：node_modules/.bin/tsc scripts/verify_llm_parse_display.tsx --rootDir . \
 *        --outDir /tmp/... --jsx react-jsx --module commonjs --target es2019 \
 *        --esModuleInterop --skipLibCheck --moduleResolution node --resolveJsonModule
 *       NODE_PATH=$(pwd)/node_modules node /tmp/.../scripts/verify_llm_parse_display.js
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ParseResultView from '../src/components/llm-parse/ParseResultView';
import type {
  CompareData,
  ConstraintData,
  LongTermData,
  ParseDocumentData,
} from '../src/types/llmParse';

const sampleDoc: ParseDocumentData = {
  docId: 'abc123def456',
  docType: 'policy',
  mode: 'deep',
  shortTerm1w: {
    effect: '即日起对新能源乘用车给予每辆1万元补贴，立即生效',
    scope: '新能源汽车行业',
    triggerTime: '发布当日',
  },
  midTerm1m: {
    industryChange: '各地出台地方配套补贴，设定准入门槛，供需改善',
    profitImpact: '行业利润环比提升',
  },
  longTermHalfyear: {
    industryPlan: '规划10个动力电池产业园，产能上限500GWh，技术路线向固态电池倾斜',
    macroOrientation: '长期扶持自主可控',
  },
  hiddenConstraint: [
    { content: '补贴对象须满足动力电池本地配套率不低于40%的前置条件', riskLevel: '中', cycle: '生效周期待核实', sourceOrigin: '附加条件…' },
    { content: '未达标企业退出补贴名单', riskLevel: '高', cycle: '立即', sourceOrigin: '退出机制…' },
  ],
  potentialRisk: ['下游需求不及预期', '库存减值风险'],
  reliability: 0.82,
  source: 'llm',
};

const sampleCompare: CompareData = {
  docCount: 2,
  docTitles: ['政策A', '研报B'],
  consensus: '新能源长期景气共识',
  conflict: '短期补贴力度分歧',
  optimisticView: '固态电池路线突破',
  pessimisticView: '出口限制加码',
  source: 'llm',
};

const sampleConstraint: ConstraintData = {
  hiddenConstraint: [
    { content: '对赌协议要求2026年净利润不低于5亿，否则补偿', riskLevel: '高', cycle: '2026年报', sourceOrigin: '业绩承诺…' },
    { content: '控股股东质押比例达65%，存在平仓风险', riskLevel: '中', cycle: '存续期', sourceOrigin: '质押…' },
  ],
  source: 'heuristic',
};

const sampleLongTerm: LongTermData = {
  industryPlan: '规划10个动力电池产业园，产能上限500GWh，技术路线向固态电池倾斜',
  macroOrientation: '长期扶持自主可控',
  source: 'heuristic',
};

function main() {
  const htmlDoc = renderToStaticMarkup(React.createElement(ParseResultView, { data: sampleDoc }));
  const htmlCmp = renderToStaticMarkup(React.createElement(ParseResultView, { data: sampleCompare }));
  const htmlCon = renderToStaticMarkup(React.createElement(ParseResultView, { data: sampleConstraint }));
  const htmlLt = renderToStaticMarkup(React.createElement(ParseResultView, { data: sampleLongTerm }));

  const checks: [string, boolean][] = [
    ['doc_id', htmlDoc.includes('abc123def456')],
    ['short_term', htmlDoc.includes('每辆1万元补贴')],
    ['long_term', htmlDoc.includes('500GWh')],
    ['constraint', htmlDoc.includes('本地配套率不低于40%')],
    ['risk_level', htmlDoc.includes('高') && htmlDoc.includes('中')],
    ['reliability', htmlDoc.includes('82%')],
    ['compare_consensus', htmlCmp.includes('新能源长期景气共识')],
    ['compare_conflict', htmlCmp.includes('短期补贴力度分歧')],
    ['constraint_block', htmlCon.includes('隐藏约束挖掘') && htmlCon.includes('对赌协议')],
    ['longterm_block', htmlLt.includes('长期规划提取') && htmlLt.includes('固态电池')],
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
    `DISPLAY_OK html_doc=${htmlDoc.length} html_cmp=${htmlCmp.length} html_con=${htmlCon.length} html_lt=${htmlLt.length} checks=${checks.length}`
  );
}

main();
