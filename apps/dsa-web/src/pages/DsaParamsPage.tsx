import { useEffect, useState } from 'react';
import { dsaParamsApi } from '../api/dsaParams';
import type { DsaParam } from '../types/dsaParams';
import { colors } from '../theme/tokens';

const titleStyle: React.CSSProperties = { fontSize: 16, fontWeight: 700, color: colors.text, marginBottom: 12 };
const labelStyle: React.CSSProperties = { color: colors.textSecondary, fontSize: 12, marginBottom: 4, display: 'block' };
const inputStyle: React.CSSProperties = {
  background: '#0b1220', color: colors.text, border: `1px solid ${colors.border}`,
  borderRadius: 6, padding: '6px 8px', fontSize: 13, width: '100%',
};

/** DSA 全局模型参数管控（设计 §5.3）：递归深度 / 系数阈值 / 风险衰减等。 */
const DsaParamsPage: React.FC<{ seed?: { params?: DsaParam[] } }> = ({ seed }) => {
  const [params, setParams] = useState<DsaParam[]>(seed?.params ?? []);
  const [drafts, setDrafts] = useState<Record<string, number>>(
    Object.fromEntries((seed?.params ?? []).map((p) => [p.paramKey, p.paramValue]))
  );
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (seed?.params) return;
    dsaParamsApi.list().then((r) => {
      setParams(r.items || []);
      setDrafts(Object.fromEntries((r.items || []).map((p) => [p.paramKey, p.paramValue])));
    }).catch(() => setErr('参数加载失败'));
  }, []);

  const save = async (p: DsaParam) => {
    setErr(null);
    try {
      await dsaParamsApi.set(p.paramKey, drafts[p.paramKey]);
      setMsg(`已保存 ${p.paramKey}`);
      const r = await dsaParamsApi.list();
      setParams(r.items || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '保存失败');
    }
  };

  const runSeed = async () => {
    setErr(null);
    try {
      await dsaParamsApi.seed();
      setMsg('已写入默认种子参数');
      const r = await dsaParamsApi.list();
      setParams(r.items || []);
      setDrafts(Object.fromEntries((r.items || []).map((p) => [p.paramKey, p.paramValue])));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'seed 失败');
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: '0 auto' }} data-testid="dsa-params">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2 style={titleStyle}>DSA 全局模型参数</h2>
        <button style={{ background: '#475569', color: '#fff', border: 'none', borderRadius: 6, padding: '6px 14px', cursor: 'pointer' }} onClick={() => runSeed()} data-testid="dsa-seed">写入种子参数</button>
      </div>

      {err && <div style={{ color: colors.danger, marginBottom: 12 }} data-testid="dp-error">{err}</div>}
      {msg && <div style={{ color: '#34d399', marginBottom: 12 }} data-testid="dp-msg">{msg}</div>}

      {params.length === 0 && (
        <div style={{ color: colors.textSecondary, fontSize: 13 }}>暂无参数，点击「写入种子参数」初始化。</div>
      )}

      {params.map((p) => (
        <div key={p.id} style={{ background: colors.card, borderRadius: 8, padding: 16, border: `1px solid ${colors.border}`, marginBottom: 12 }} data-testid="dp-row">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <b style={{ color: colors.text }}>{p.paramKey}</b>
            <span style={{ color: colors.textSecondary, fontSize: 12 }}>{p.paramDesc || ''}</span>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 10 }}>
            <input
              type="number" step={0.05} style={inputStyle}
              value={drafts[p.paramKey] ?? p.paramValue}
              onChange={(e) => setDrafts({ ...drafts, [p.paramKey]: parseFloat(e.target.value) || 0 })}
              data-testid={`dp-input-${p.paramKey}`}
            />
            <button style={{ background: '#2563eb', color: '#fff', border: 'none', borderRadius: 6, padding: '6px 14px', cursor: 'pointer' }} onClick={() => save(p)} data-testid={`dp-save-${p.paramKey}`}>保存</button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default DsaParamsPage;
