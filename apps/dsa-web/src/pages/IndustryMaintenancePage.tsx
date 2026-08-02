import { useEffect, useState } from 'react';
import { industryChainApi } from '../api/industryChain';
import type {
  ChainEdgeOverride,
  ChainRiskFlag,
  IndustryChainListItem,
} from '../types/industryChain';
import { colors } from '../theme/tokens';

const sectionStyle: React.CSSProperties = {
  background: colors.card,
  borderRadius: 8,
  padding: 18,
  border: `1px solid ${colors.border}`,
  marginBottom: 16,
};
const titleStyle: React.CSSProperties = {
  fontSize: 16, fontWeight: 700, color: colors.text, marginBottom: 12,
};
const labelStyle: React.CSSProperties = { color: colors.textSecondary, fontSize: 12, marginBottom: 4, display: 'block' };
const inputStyle: React.CSSProperties = {
  background: '#0b1220', color: colors.text, border: `1px solid ${colors.border}`,
  borderRadius: 6, padding: '6px 8px', fontSize: 13, width: '100%',
};
const btn = (accent: string): React.CSSProperties => ({
  background: accent, color: '#fff', border: 'none', borderRadius: 6,
  padding: '6px 14px', cursor: 'pointer', fontSize: 13,
});

/** 页面4 收尾：产业链维护（自定义传导系数 / 风险标记 / 模板导出）。 */
const IndustryMaintenancePage: React.FC<{
  seed?: { chains?: IndustryChainListItem[]; overrides?: ChainEdgeOverride[]; flags?: ChainRiskFlag[] };
}> = ({ seed }) => {
  const [chains, setChains] = useState<IndustryChainListItem[]>(seed?.chains ?? []);
  const [chainId, setChainId] = useState<string>(seed?.chains?.[0]?.id ?? '');

  const [edge, setEdge] = useState<ChainEdgeOverride | null>(null);
  const [sourceNode, setSourceNode] = useState('');
  const [targetNode, setTargetNode] = useState('');
  const [coeff, setCoeff] = useState(0.6);
  const [lag, setLag] = useState(5);

  const [riskNode, setRiskNode] = useState('');
  const [riskType, setRiskType] = useState('price_up');
  const [severity, setSeverity] = useState('中');
  const [note, setNote] = useState('');

  const [overrides, setOverrides] = useState<ChainEdgeOverride[]>(seed?.overrides ?? []);
  const [flags, setFlags] = useState<ChainRiskFlag[]>(seed?.flags ?? []);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    industryChainApi.list().then((r) => {
      setChains(r.items || []);
      if (r.items && r.items.length > 0) setChainId(r.items[0].id);
    }).catch(() => setErr('产业链目录加载失败'));
  }, []);

  useEffect(() => {
    if (!chainId) return;
    setMsg(null);
    Promise.all([
      industryChainApi.listEdgeOverrides(chainId),
      industryChainApi.listRiskFlags(chainId),
    ]).then(([o, f]) => {
      setOverrides(o.items || []);
      setFlags(f.items || []);
    }).catch(() => setErr('加载系数/风险失败'));
  }, [chainId]);

  const saveOverride = async () => {
    setErr(null);
    try {
      const r = await industryChainApi.upsertEdgeOverride(chainId, {
        sourceNode, targetNode, coeff, lag,
      });
      setEdge(r.data);
      setMsg('传导系数已保存');
      const o = await industryChainApi.listEdgeOverrides(chainId);
      setOverrides(o.items || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '保存失败');
    }
  };

  const addFlag = async () => {
    setErr(null);
    try {
      await industryChainApi.addRiskFlag(chainId, { node: riskNode, riskType, severity, note });
      setMsg('风险标记已添加');
      const f = await industryChainApi.listRiskFlags(chainId);
      setFlags(f.items || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '添加失败');
    }
  };

  const doExport = async () => {
    setErr(null);
    try {
      const r = await industryChainApi.exportTemplate(chainId);
      const t = r.data;
      setMsg(`模板已导出：${t.nodes.length} 节点 / ${t.edges.length} 边`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '导出失败');
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }} data-testid="industry-maintenance">
      <h2 style={titleStyle}>产业链信息维护</h2>

      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>选择产业链</label>
        <select value={chainId} onChange={(e) => setChainId(e.target.value)} style={inputStyle} data-testid="chain-select">
          {chains.map((c) => (
            <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
          ))}
        </select>
      </div>

      {err && <div style={{ color: colors.danger, marginBottom: 12 }} data-testid="im-error">{err}</div>}
      {msg && <div style={{ color: '#34d399', marginBottom: 12 }} data-testid="im-msg">{msg}</div>}

      {/* 自定义传导系数 */}
      <div style={sectionStyle} data-testid="edge-panel">
        <div style={titleStyle}>自定义传导系数（覆盖默认 0.6 / lag 5）</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={labelStyle}>源环节</label>
            <input style={inputStyle} value={sourceNode} onChange={(e) => setSourceNode(e.target.value)} placeholder="如 锂矿" />
          </div>
          <div>
            <label style={labelStyle}>目标环节</label>
            <input style={inputStyle} value={targetNode} onChange={(e) => setTargetNode(e.target.value)} placeholder="如 正极材料" />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 16, marginTop: 12, alignItems: 'center' }}>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>传导系数 coeff：{coeff.toFixed(2)}</label>
            <input type="range" min={0} max={1} step={0.05} value={coeff}
              onChange={(e) => setCoeff(parseFloat(e.target.value))} style={{ width: '100%' }} />
          </div>
          <div style={{ width: 120 }}>
            <label style={labelStyle}>lag（天）</label>
            <input type="number" style={inputStyle} value={lag} onChange={(e) => setLag(parseInt(e.target.value, 10) || 0)} />
          </div>
          <button style={{ ...btn('#2563eb'), marginTop: 14 }} onClick={saveOverride} data-testid="save-edge">保存系数</button>
        </div>
        {overrides.length > 0 && (
          <div style={{ marginTop: 12 }}>
            {overrides.map((o) => (
              <div key={o.id} style={{ fontSize: 12, color: colors.textSecondary, padding: '4px 0', borderBottom: `1px solid ${colors.border}` }}>
                {o.sourceNode} → {o.targetNode}：coeff={o.coeff.toFixed(2)} / lag={o.lag}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 风险标记 */}
      <div style={sectionStyle} data-testid="risk-panel">
        <div style={titleStyle}>产业链环节风险标记</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <div>
            <label style={labelStyle}>环节</label>
            <input style={inputStyle} value={riskNode} onChange={(e) => setRiskNode(e.target.value)} placeholder="如 碳酸锂" />
          </div>
          <div>
            <label style={labelStyle}>风险类型</label>
            <select style={inputStyle} value={riskType} onChange={(e) => setRiskType(e.target.value)}>
              <option value="price_up">涨价</option>
              <option value="output_cut">减产</option>
              <option value="oversupply">过剩</option>
              <option value="other">其他</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>严重度</label>
            <select style={inputStyle} value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="高">高</option>
              <option value="中">中</option>
              <option value="低">低</option>
            </select>
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          <label style={labelStyle}>备注</label>
          <input style={inputStyle} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <button style={{ ...btn('#f59e0b'), marginTop: 12 }} onClick={addFlag} data-testid="add-flag">添加风险标记</button>
        {flags.length > 0 && (
          <div style={{ marginTop: 12 }}>
            {flags.map((f) => (
              <div key={f.id} style={{ fontSize: 12, color: colors.textSecondary, padding: '4px 0', borderBottom: `1px solid ${colors.border}` }}>
                [{f.severity}] {f.node}（{f.riskType}）{f.note ? `：${f.note}` : ''}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 模板导出 */}
      <div style={sectionStyle} data-testid="export-panel">
        <div style={titleStyle}>一键导出画布模板</div>
        <p style={{ color: colors.textSecondary, fontSize: 13, marginBottom: 12 }}>
          导出当前产业链的 nodes / edges / companies 结构化画布模板，可直接导入画布编辑器。
        </p>
        <button style={{ ...btn('#00B42A') }} onClick={doExport} data-testid="export-btn">导出模板</button>
      </div>
    </div>
  );
};

export default IndustryMaintenancePage;
