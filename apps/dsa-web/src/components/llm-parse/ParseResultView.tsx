import type { CSSProperties } from 'react';
import type {
  CompareData,
  ConstraintData,
  LongTermData,
  ParseDocumentData,
} from '../../types/llmParse';

const card: CSSProperties = {
  background: '#0e1626',
  border: '1px solid #1f2d44',
  borderRadius: 10,
  padding: 14,
  color: '#dbe4f3',
  fontSize: 13,
  lineHeight: 1.6,
};
const blockTitle: CSSProperties = {
  color: '#7dd3fc',
  fontWeight: 600,
  marginBottom: 6,
  fontSize: 13,
};
const riskColor: Record<string, string> = {
  高: '#f87171',
  中: '#fbbf24',
  低: '#34d399',
};

/** 纯展示组件：渲染解析结果（SSR 安全，无副作用/无 echarts/无 api 依赖）。 */
export default function ParseResultView({ data }: { data: ParseDocumentData | CompareData | ConstraintData | LongTermData }) {
  const isCompare = 'docTitles' in data;
  if (isCompare) {
    const c = data as CompareData;
    return (
      <div style={card} data-testid="parse-compare">
        <div style={blockTitle}>多文档交叉对比（{c.docCount} 份）</div>
        <div><b style={{ color: '#a5b4fc' }}>共识：</b>{c.consensus}</div>
        <div><b style={{ color: '#fbbf24' }}>分歧：</b>{c.conflict}</div>
        <div><b style={{ color: '#34d399' }}>乐观：</b>{c.optimisticView}</div>
        <div><b style={{ color: '#f87171' }}>悲观：</b>{c.pessimisticView}</div>
        <div style={{ marginTop: 6, color: '#64748b' }}>来源：{c.source}</div>
      </div>
    );
  }
  const isConstraint = 'hiddenConstraint' in data && !('docId' in data);
  if (isConstraint) {
    const c = data as ConstraintData;
    return (
      <div style={card} data-testid="parse-constraint">
        <div style={blockTitle}>隐藏约束挖掘（{c.hiddenConstraint.length}）</div>
        {c.hiddenConstraint.length === 0 && (
          <div style={{ color: '#94a3b8' }}>（未识别到明显隐藏约束）</div>
        )}
        {c.hiddenConstraint.map((h, i) => (
          <div key={i} style={{ marginBottom: 4 }}>
            <span style={{ color: riskColor[h.riskLevel] ?? '#fbbf24', fontWeight: 600 }}>[{h.riskLevel}]</span>{' '}
            {h.content}
          </div>
        ))}
        <div style={{ marginTop: 6, color: '#64748b' }}>来源：{c.source}</div>
      </div>
    );
  }
  const isLongTerm = 'industryPlan' in data;
  if (isLongTerm) {
    const l = data as LongTermData;
    return (
      <div style={card} data-testid="parse-long-term">
        <div style={blockTitle}>长期规划提取（半年+）</div>
        <div><b style={{ color: '#a5b4fc' }}>行业规划：</b>{l.industryPlan}</div>
        <div style={{ marginTop: 6, color: '#94a3b8' }}>宏观导向：{l.macroOrientation}</div>
        <div style={{ marginTop: 6, color: '#64748b' }}>来源：{l.source}</div>
      </div>
    );
  }
  const d = data as ParseDocumentData;
  return (
    <div style={card} data-testid="parse-result">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ color: '#94a3b8' }}>文档ID：{d.docId}</span>
        <span style={{ color: d.source === 'llm' ? '#34d399' : '#fbbf24' }}>
          {d.source === 'llm' ? 'LLM精读' : '启发式降级'} · 置信度 {(d.reliability * 100).toFixed(0)}%
        </span>
      </div>
      <div style={blockTitle}>短期（1周~半月）</div>
      <div>{d.shortTerm1w.effect}</div>
      <div style={{ color: '#94a3b8' }}>范围：{d.shortTerm1w.scope} · 生效：{d.shortTerm1w.triggerTime}</div>

      <div style={{ ...blockTitle, marginTop: 10 }}>中期（1个月）</div>
      <div>{d.midTerm1m.industryChange}</div>
      <div style={{ color: '#94a3b8' }}>利润影响：{d.midTerm1m.profitImpact}</div>

      <div style={{ ...blockTitle, marginTop: 10 }}>长期（半年）</div>
      <div>{d.longTermHalfyear.industryPlan}</div>
      <div style={{ color: '#94a3b8' }}>宏观导向：{d.longTermHalfyear.macroOrientation}</div>

      {d.hiddenConstraint.length > 0 && (
        <>
          <div style={{ ...blockTitle, marginTop: 10 }}>隐藏约束（{d.hiddenConstraint.length}）</div>
          {d.hiddenConstraint.map((c, i) => (
            <div key={i} style={{ marginBottom: 4 }}>
              <span style={{ color: riskColor[c.riskLevel] ?? '#fbbf24', fontWeight: 600 }}>
                [{c.riskLevel}]
              </span>{' '}
              {c.content}
            </div>
          ))}
        </>
      )}

      {d.potentialRisk.length > 0 && (
        <>
          <div style={{ ...blockTitle, marginTop: 10 }}>隐性风险（{d.potentialRisk.length}）</div>
          {d.potentialRisk.map((r, i) => (
            <div key={i}>• {r}</div>
          ))}
        </>
      )}
    </div>
  );
}
