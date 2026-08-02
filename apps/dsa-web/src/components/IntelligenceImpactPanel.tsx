import React, { useEffect, useState } from 'react';
import { intelligenceImpactApi } from '../api/intelligenceImpact';
import { dynamicsApi } from '../api/dynamics';
import { CYCLE_LABELS, DIRECTION_COLORS } from '../types/intelligenceImpact';
import type { IntelligenceImpact } from '../types/intelligenceImpact';

const card: React.CSSProperties = {
  background: '#111c33',
  border: '1px solid #1e293b',
  borderRadius: 10,
  padding: 12,
};
const muted = { color: '#64748b' } as React.CSSProperties;

/** 情报结构化 5 字段 + AI 分级面板（设计 §2.2 / §5.2）。 */
const IntelligenceImpactPanel: React.FC<{ seedData?: IntelligenceImpact[] }> = ({
  seedData,
}) => {
  const [rows, setRows] = useState<IntelligenceImpact[]>(seedData ?? []);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (seedData) return;
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setErr(null);
      try {
        // 取最近情报，调分级接口
        const list = await dynamicsApi.getIntelligenceItems({ days: 7 });
        const items = (list.items || []).slice(0, 8).map((it) => ({
          id: it.id,
          title: it.title,
          summary: it.summary,
          industry: it.industry,
        }));
        if (items.length > 0) {
          const graded = await intelligenceImpactApi.grade(items);
          if (!cancelled) setRows(graded.items || []);
        }
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : '分级失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="glass-card" style={{ padding: 16 }} data-testid="impact-panel">
      <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>
        情报结构化分级
      </h3>
      {loading && <div style={muted}>分级计算中…</div>}
      {err && <div style={{ color: '#f87171' }}>{err}</div>}
      {!loading && !err && rows.length === 0 && (
        <div style={muted}>暂无分级结果，拉取情报后将自动计算 5 字段。</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rows.map((r) => (
          <div key={r.itemId} style={card} data-testid={`impact-${r.itemId}`}>
            <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: 6 }}>
              {r.title ?? r.itemId}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 12 }}>
              <span style={{ color: r.impactDirection ? DIRECTION_COLORS[r.impactDirection] : '#94a3b8' }}>
                {r.impactDirection}
              </span>
              <span style={muted}>等级 {r.impactLevel}</span>
              <span style={muted}>周期 {r.impactCycle ? CYCLE_LABELS[r.impactCycle] : '-'}</span>
              <span style={muted}>传导 {(r.transmitWeight ?? 0) * 100}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default IntelligenceImpactPanel;
