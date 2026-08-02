/**
 * 预测复盘归因中心（设计：预测复盘归因自动打分）
 * 左：聚合报告（准确率 / 三层健康度 / 分周期命中率）
 * 右：单条预测打分（输入预测 + 实际观测 → 三层归因）
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { reviewApi } from '../api/review';
import { ReviewReportView, ReviewScoreView } from '../components/review/ReviewBoard';
import type {
  ReviewCycleInput,
  ReviewReportData,
  ReviewScoreData,
} from '../types/review';

export default function ReviewCenterPage() {
  const [report, setReport] = useState<ReviewReportData | null>(null);
  const [score, setScore] = useState<ReviewScoreData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 表单状态
  const [symbol, setSymbol] = useState('600519');
  const [name, setName] = useState('贵州茅台');
  const [cycles, setCycles] = useState<ReviewCycleInput[]>([
    { cycle: '1w', direction: 'up', consensus_score: 0.7, up_probability: 65, confidence: 0.8, volatility_range_pct: { low: -3, high: 5 }, actual_direction: 'up', actual_return_pct: 4.2 },
    { cycle: '1m', direction: 'up', consensus_score: 0.6, up_probability: 58, confidence: 0.7, volatility_range_pct: { low: -5, high: 8 }, actual_direction: 'oscillation', actual_return_pct: 1.1 },
    { cycle: '6m', direction: 'up', consensus_score: 0.55, up_probability: 55, confidence: 0.65, volatility_range_pct: { low: -10, high: 20 }, actual_direction: 'up', actual_return_pct: 12 },
  ]);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await reviewApi.report();
      if (resp.code === 0 && resp.data && 'byCycle' in resp.data) {
        setReport(resp.data as ReviewReportData);
      } else if (resp.code === 0 && resp.data) {
        setReport(resp.data as unknown as ReviewReportData);
      } else {
        setError(resp.msg || '加载失败');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求异常');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadReport();
  }, [loadReport]);

  const setCycleField = (idx: number, patch: Partial<ReviewCycleInput>) => {
    setCycles((prev) => prev.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
  };

  const handleScore = async () => {
    setError(null);
    try {
      const resp = await reviewApi.score({ symbol, name, cycles });
      if (resp.code === 0 && resp.data && 'cycles' in resp.data) {
        setScore(resp.data as ReviewScoreData);
        void loadReport();
      } else if (resp.code === 0 && resp.data) {
        setScore(resp.data as unknown as ReviewScoreData);
      } else {
        setError(resp.msg || '打分失败');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求异常');
    }
  };

  return (
    <div style={{ padding: 20, maxWidth: 1280, margin: '0 auto' }}>
      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 20, marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: 20, color: '#fff', marginBottom: 6 }}>预测复盘归因中心</h2>
          <p style={{ fontSize: 13, color: '#86909C' }}>三层复盘：数据层 / 模型层 / 逻辑层 自动归因打分</p>
        </div>
        <button className="dsa-btn" onClick={() => void loadReport()} disabled={loading}>
          {loading ? <span className="scan-line" style={{ display: 'inline-block', width: 90, height: 18 }} /> : <><RefreshCw size={14} style={{ marginRight: 6 }} />刷新</>}
        </button>
      </div>

      {error && (
        <div className="glass-card" style={{ padding: 16, borderColor: '#F53F3F', color: '#F53F3F', marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 420px', gap: 16, alignItems: 'start' }}>
        {/* 左：聚合报告 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {report ? <ReviewReportView data={report} /> : <div className="glass-card" style={{ padding: 24, color: '#86909C', textAlign: 'center' }}>报告加载中…</div>}
          {score ? <ReviewScoreView data={score} /> : null}
        </div>

        {/* 右：打分表单 */}
        <div className="glass-card" style={{ padding: 16 }}>
          <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>单条预测打分</h3>
          <label style={{ fontSize: 12, color: '#86909C', display: 'block', marginBottom: 4 }}>标的代码</label>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} className="dsa-input" style={{ width: '100%', marginBottom: 10 }} />
          <label style={{ fontSize: 12, color: '#86909C', display: 'block', marginBottom: 4 }}>标的名称</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="dsa-input" style={{ width: '100%', marginBottom: 10 }} />

          {cycles.map((c, i) => (
            <div key={c.cycle} style={{ borderTop: '1px solid #22262F', paddingTop: 8, marginTop: 8 }}>
              <div style={{ color: '#7dd3fc', fontSize: 12, marginBottom: 6 }}>周期 {c.cycle}</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <select value={c.direction} onChange={(e) => setCycleField(i, { direction: e.target.value })} className="dsa-input" style={{ flex: 1, minWidth: 90 }}>
                  {['up', 'down', 'oscillation'].map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
                <select value={c.actual_direction} onChange={(e) => setCycleField(i, { actual_direction: e.target.value })} className="dsa-input" style={{ flex: 1, minWidth: 90 }}>
                  {['up', 'down', 'oscillation'].map((d) => <option key={d} value={d}>实际{d}</option>)}
                </select>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <input type="number" step="0.1" value={c.actual_return_pct} onChange={(e) => setCycleField(i, { actual_return_pct: Number(e.target.value) })} className="dsa-input" style={{ flex: 1, minWidth: 90 }} placeholder="实际收益%" aria-label={`${c.cycle} 实际收益`} />
                <input type="number" step="0.01" value={c.confidence} onChange={(e) => setCycleField(i, { confidence: Number(e.target.value) })} className="dsa-input" style={{ flex: 1, minWidth: 90 }} placeholder="置信度" aria-label={`${c.cycle} 置信度`} />
              </div>
            </div>
          ))}

          <button className="dsa-btn" style={{ marginTop: 12, width: '100%', justifyContent: 'center' }} onClick={() => void handleScore()}>
            提交复盘打分
          </button>
        </div>
      </div>
    </div>
  );
}
