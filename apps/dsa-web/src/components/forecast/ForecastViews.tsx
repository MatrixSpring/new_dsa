/**
 * 前瞻预测中心 — 纯展示组件（无副作用、无 echarts，便于 SSR/单测验证“数据显示”）
 * 设计 §3.5 标准化多周期结论表：方向 / 波动区间 / 上涨概率 / 置信度
 */
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type {
  ForecastCycleKey,
  ForecastDirection,
  SymbolForecast,
} from '../../types/forecast';

const CYCLE_META: { key: ForecastCycleKey; label: string; days: number }[] = [
  { key: '1w', label: '1周', days: 5 },
  { key: '2w', label: '半月', days: 10 },
  { key: '1m', label: '1月', days: 22 },
  { key: '6m', label: '半年', days: 120 },
];

const DIRECTION_COLOR: Record<ForecastDirection, string> = {
  up: '#F53F3F',
  down: '#00B42A',
  oscillation: '#FF7D00',
};
const DIRECTION_ICON: Record<ForecastDirection, typeof TrendingUp> = {
  up: TrendingUp,
  down: TrendingDown,
  oscillation: Minus,
};

export function directionColor(direction: ForecastDirection): string {
  return DIRECTION_COLOR[direction] ?? '#86909C';
}

function formatPct(v: number): string {
  const sign = v > 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(1)}%`;
}

export interface ForecastTableProps {
  symbolsData: Record<string, SymbolForecast>;
  selectedCycle: ForecastCycleKey;
  onSelectCycle: (cycle: ForecastCycleKey) => void;
}

export function ForecastTable({
  symbolsData,
  selectedCycle,
  onSelectCycle,
}: ForecastTableProps) {
  const orderedSymbols = Object.keys(symbolsData);

  return (
    <div>
      <table className="dsa-tech-table" style={{ width: '100%' }}>
        <thead>
          <tr>
            <th>标的</th>
            {CYCLE_META.map((m) => (
              <th key={m.key}>
                {m.label}
                <div style={{ fontSize: 11, color: '#86909C', fontWeight: 400 }}>{m.days}交易日</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {orderedSymbols.map((sym) => {
            const fc = symbolsData[sym];
            return (
              <tr key={sym} data-testid={`row-${sym}`}>
                <td style={{ fontWeight: 600, color: '#E5E6EB' }}>{sym}</td>
                {CYCLE_META.map((m) => {
                  const c = fc.cycles[m.key];
                  if (!c) return <td key={m.key}>-</td>;
                  const Icon = DIRECTION_ICON[c.direction as ForecastDirection] ?? Minus;
                  return (
                    <td key={m.key} data-testid={`cell-${sym}-${m.key}`}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                          color: directionColor(c.direction as ForecastDirection),
                          fontWeight: 600,
                        }}
                      >
                        <Icon size={13} /> {c.directionLabel}
                      </div>
                      <div style={{ fontSize: 11, color: '#C9CDD4', marginTop: 2 }}>
                        区间 {formatPct(c.volatilityRangePct.low)}~{formatPct(c.volatilityRangePct.high)}
                      </div>
                      <div style={{ fontSize: 11, color: '#86909C' }}>
                        涨概 {c.upProbability}% · 置信 {(c.confidence * 100).toFixed(0)}%
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      <h4 style={{ fontSize: 13, color: '#C9CDD4', margin: '16px 0 8px' }}>周期切换</h4>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {CYCLE_META.map((m) => (
          <button
            key={m.key}
            onClick={() => onSelectCycle(m.key)}
            className={`dsa-btn ${selectedCycle === m.key ? 'dsa-btn-active' : 'dsa-btn-ghost'}`}
          >
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
}
