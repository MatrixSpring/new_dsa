import React, { useEffect, useState } from 'react';
import { forecastSnapshotApi } from '../api/forecastSnapshot';
import type {
  Cycle,
  CycleOverview,
  Direction,
  ForecastSnapshot,
  ForecastSnapshotResponse,
  ScopeType,
} from '../types/forecastSnapshot';
import {
  CYCLE_LABELS,
  DIRECTION_LABELS,
  SCOPE_LABELS,
} from '../types/forecastSnapshot';

const CYCLES: Cycle[] = ['1w', '2w', '1m', '6m'];

const card: React.CSSProperties = {
  background: '#111c33',
  border: '1px solid #1e293b',
  borderRadius: 10,
  padding: 16,
};
const muted = { color: '#64748b' } as React.CSSProperties;
const dirColor: Record<Direction, string> = {
  up: '#f87171',
  down: '#34d399',
  oscillation: '#fbbf24',
};

/** 前瞻预测中心（设计 §3.2 多周期 + 第二阶段「前瞻预测中心 UI 聚合页」基类）。 */
const ForecastCenterPage: React.FC<{ seedData?: ForecastSnapshotResponse }> = ({
  seedData,
}) => {
  const [items, setItems] = useState<ForecastSnapshot[]>(seedData?.items ?? []);
  const [byCycle, setByCycle] = useState<CycleOverview[]>(seedData?.byCycle ?? []);
  const [scopeType, setScopeType] = useState<ScopeType | ''>('');
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    const p = scopeType ? { scopeType } : {};
    forecastSnapshotApi
      .list(p)
      .then((r) => {
        setItems(r.items || []);
        setByCycle(r.byCycle || []);
      })
      .catch(() => setErr('前瞻预测快照加载失败'));
  };

  useEffect(() => {
    if (seedData) {
      setItems(seedData.items || []);
      setByCycle(seedData.byCycle || []);
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeType]);

  const handleSeed = () => {
    setErr(null);
    forecastSnapshotApi
      .seed()
      .then((r) => {
        setMsg(`已生成 ${r.data.created} 条占位快照`);
        load();
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'seed 失败'));
  };

  const scopes = Array.from(new Set(items.map((i) => i.scopeValue || i.scopeType)));

  return (
    <div style={{ padding: 24, color: '#e2e8f0' }} data-testid="forecast-center">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>前瞻预测中心</h2>
        <button
          style={{ background: '#165DFF', color: '#fff', border: 'none', borderRadius: 6, padding: '6px 14px', cursor: 'pointer' }}
          onClick={handleSeed}
          data-testid="fc-seed"
        >
          生成演示快照
        </button>
      </div>

      {/* 四周期概览 */}
      <div style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
        {CYCLES.map((c) => {
          const ov = byCycle.find((x) => x.cycle === c);
          return (
            <div key={c} style={{ ...card, flex: '1 1 180px' }} data-testid={`fc-cycle-${c}`}>
              <div style={{ fontWeight: 600 }}>{CYCLE_LABELS[c]}</div>
              <div style={muted}>样本 {ov ? ov.total : 0}</div>
              <div style={{ marginTop: 8 }}>
                看多 {ov ? ov.directionCounts.up : 0} / 看空 {ov ? ov.directionCounts.down : 0} / 震荡{' '}
                {ov ? ov.directionCounts.oscillation : 0}
              </div>
              <div style={{ marginTop: 4 }}>
                平均置信度 {(ov ? ov.avgConfidence : 0) * 100}%
              </div>
            </div>
          );
        })}
      </div>

      {/* 筛选 */}
      <div style={{ marginTop: 16 }}>
        <label style={muted}>范围类型：</label>
        <select
          value={scopeType}
          onChange={(e) => setScopeType(e.target.value as ScopeType | '')}
          data-testid="fc-scope-filter"
          style={{ background: '#0f172a', color: '#e2e8f0', border: '1px solid #1e293b', borderRadius: 6, padding: '4px 8px' }}
        >
          <option value="">全部</option>
          <option value="stock">个股</option>
          <option value="industry">产业链</option>
          <option value="event">事件</option>
          <option value="portfolio">组合</option>
        </select>
      </div>

      {/* 快照卡片 */}
      <div style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
        {scopes.map((sc) => {
          const rows = items.filter((i) => (i.scopeValue || i.scopeType) === sc);
          return (
            <div key={sc} style={{ ...card, flex: '1 1 260px' }} data-testid={`fc-scope-${sc}`}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>{sc}</div>
              {CYCLES.map((c) => {
                const it = rows.find((r) => r.cycle === c);
                if (!it) return null;
                const d = (it.direction || 'oscillation') as Direction;
                return (
                  <div key={c} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #1e293b' }}>
                    <span>{CYCLE_LABELS[c]}</span>
                    <span style={{ color: dirColor[d] }}>{DIRECTION_LABELS[d]}</span>
                    <span style={muted}>
                      {it.lowPct}% ~ {it.highPct}%
                    </span>
                    <span style={muted}>置信{(it.confidence || 0) * 100}%</span>
                  </div>
                );
              })}
            </div>
          );
        })}
        {scopes.length === 0 && (
          <div style={muted}>暂无快照，点击「生成演示快照」或等待每日批量推演落库。</div>
        )}
      </div>

      {msg && <div style={{ color: '#34d399', marginTop: 12 }}>{msg}</div>}
      {err && <div style={{ color: '#f87171', marginTop: 12 }}>{err}</div>}
    </div>
  );
};

export default ForecastCenterPage;
