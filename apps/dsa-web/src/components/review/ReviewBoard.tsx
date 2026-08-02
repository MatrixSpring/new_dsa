import type { CSSProperties } from 'react';
import type {
  ReviewLayerKey,
  ReviewReportData,
  ReviewScoreData,
} from '../../types/review';

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
const LAYER_LABEL: Record<ReviewLayerKey, string> = {
  data_layer: '数据层',
  model_layer: '模型层',
  logic_layer: '逻辑层',
};
const LAYER_COLOR: Record<ReviewLayerKey, string> = {
  data_layer: '#60a5fa',
  model_layer: '#a78bfa',
  logic_layer: '#f472b6',
};

function LayerBar({ layer, value }: { layer: ReviewLayerKey; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>{LAYER_LABEL[layer]}</span>
        <span style={{ color: LAYER_COLOR[layer] }}>{pct}%</span>
      </div>
      <div style={{ background: '#162034', borderRadius: 6, height: 8, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: LAYER_COLOR[layer] }} />
      </div>
    </div>
  );
}

/** 纯展示：聚合复盘报告（SSR 安全，无副作用）。 */
export function ReviewReportView({ data }: { data: ReviewReportData }) {
  const layers = data.avgLayerHealth;
  return (
    <div style={card} data-testid="review-report">
      <div style={blockTitle}>复盘归因总览（样本 {data.total}）</div>
      <div style={{ fontSize: 22, color: '#34d399', fontWeight: 700 }}>
        综合准确率 {(Number(data.accuracyRate ?? 0) * 100).toFixed(1)}%
      </div>
      <div style={{ color: '#94a3b8', marginBottom: 8 }}>
        最弱层：{data.weakestLayer ? LAYER_LABEL[data.weakestLayer] : '—'}
      </div>
      <LayerBar layer="data_layer" value={layers.data_layer ?? 0} />
      <LayerBar layer="model_layer" value={layers.model_layer ?? 0} />
      <LayerBar layer="logic_layer" value={layers.logic_layer ?? 0} />
      {Object.keys(data.byCycle).length > 0 && (
        <>
          <div style={{ ...blockTitle, marginTop: 10 }}>分周期命中率</div>
          {Object.entries(data.byCycle).map(([cyc, s]) => (
            <div key={cyc} style={{ display: 'flex', gap: 12 }}>
              <span style={{ width: 36, color: '#fff' }}>{cyc}</span>
              <span>准确率 {(s.accuracyRate * 100).toFixed(0)}%</span>
              <span style={{ color: '#94a3b8' }}>
                方向 {(s.directionHitRate * 100).toFixed(0)}% / 区间 {(s.rangeHitRate * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

/** 纯展示：单条预测打分明细（SSR 安全，无副作用）。 */
export function ReviewScoreView({ data }: { data: ReviewScoreData }) {
  return (
    <div style={card} data-testid="review-score">
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ color: '#fff', fontWeight: 600 }}>{data.symbol} {data.name}</span>
        <span style={{ color: '#34d399' }}>准确率 {(data.accuracyRate * 100).toFixed(0)}%</span>
      </div>
      <div style={{ color: '#94a3b8', marginBottom: 8 }}>
        最弱层：{LAYER_LABEL[data.weakestLayer]}
      </div>
      {data.cycles.map((c) => (
        <div key={c.cycle} style={{ borderTop: '1px solid #162034', paddingTop: 6, marginTop: 6 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span style={{ width: 36, color: '#fff', fontWeight: 600 }}>{c.cycle}</span>
            <span style={{ color: c.directionHit ? '#34d399' : '#f87171' }}>
              {c.directionHit ? '方向✓' : '方向✗'}
            </span>
            <span style={{ color: c.rangeHit ? '#34d399' : '#f87171' }}>
              {c.rangeHit ? '区间✓' : '区间✗'}
            </span>
            <span style={{ color: '#94a3b8' }}>实际收益 {c.actualReturnPct}%</span>
          </div>
          <div style={{ fontSize: 12, color: '#64748b' }}>
            {LAYER_LABEL.data_layer}：{c.attribution.dataLayer.note}｜
            {LAYER_LABEL.model_layer}：{c.attribution.modelLayer.note}｜
            {LAYER_LABEL.logic_layer}：{c.attribution.logicLayer.note}
          </div>
        </div>
      ))}
    </div>
  );
}
