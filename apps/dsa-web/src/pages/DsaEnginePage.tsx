import { useEffect, useState } from 'react';
import { industryChainApi } from '../api/industryChain';
import type {
  DsaEngineSeed,
  IndustryChainListItem,
  PropagateResult,
  ScenarioResult,
} from '../types/industryChain';
import { colors } from '../theme/tokens';

const titleStyle: React.CSSProperties = { fontSize: 16, fontWeight: 700, color: colors.text, marginBottom: 6 };
const subStyle: React.CSSProperties = { color: colors.textSecondary, fontSize: 12, marginBottom: 14 };
const labelStyle: React.CSSProperties = { color: colors.textSecondary, fontSize: 12, marginBottom: 4, display: 'block' };
const inputStyle: React.CSSProperties = {
  background: '#0b1220', color: colors.text, border: `1px solid ${colors.border}`,
  borderRadius: 6, padding: '6px 8px', fontSize: 13, width: '100%',
};
const cardStyle: React.CSSProperties = {
  background: '#0f172a', border: `1px solid ${colors.border}`, borderRadius: 8, padding: 14, marginBottom: 12,
};
const btnStyle: React.CSSProperties = {
  background: colors.primary, color: '#fff', border: 'none', borderRadius: 6,
  padding: '8px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer', marginRight: 8,
};
const btnGhost: React.CSSProperties = {
  background: 'transparent', color: colors.text, border: `1px solid ${colors.border}`,
  borderRadius: 6, padding: '8px 14px', fontSize: 13, cursor: 'pointer', marginRight: 8,
};

const SHOCK_KINDS = ['cost', 'demand', 'supply', 'substitute', 'negative'];

function ParamRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '3px 0' }}>
      <span style={{ color: colors.textSecondary }}>{label}</span>
      <span style={{ color: colors.text, fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function ImpactBlock({ title, res }: { title: string; res: PropagateResult }) {
  const topNodes = (res.nodeImpacts || []).slice(0, 5);
  const topCompanies = (res.companyImpacts || []).slice(0, 5);
  return (
    <div style={cardStyle}>
      <div style={{ fontWeight: 700, color: colors.text, marginBottom: 8 }}>{title}</div>
      <ParamRow label="冲击环节" value={res.shockLabel || res.shockNode} />
      <ParamRow label="冲击幅度" value={`${(res.magnitudePct ?? 0).toFixed(1)}%`} />
      <ParamRow label="受影响环节" value={res.summary.impactedNodes} />
      <ParamRow label="最大冲击" value={`${(res.summary.maxImpactPct ?? 0).toFixed(2)}%`} />
      <ParamRow label="受影响公司" value={res.summary.affectedCompanies} />
      <ParamRow label="双向衰减" value={res.params.bidirectionalDecay} />
      <ParamRow label="利空衰减" value={res.params.bearishDecay} />
      {res.params.usedOverrides && <ParamRow label="覆盖系数" value="已启用" />}

      <div style={{ fontSize: 12, color: colors.textSecondary, margin: '10px 0 4px' }}>Top 环节冲击</div>
      {topNodes.map((n) => (
        <div key={n.nodeId} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '2px 0' }}>
          <span style={{ color: colors.text }}>{n.label}</span>
          <span style={{ color: n.direction === 'positive' ? '#ef4444' : '#22c55e', fontWeight: 600 }}>
            {n.direction === 'positive' ? '+' : ''}{(n.impactPct ?? 0).toFixed(2)}%
          </span>
        </div>
      ))}

      <div style={{ fontSize: 12, color: colors.textSecondary, margin: '10px 0 4px' }}>Top 公司冲击</div>
      {topCompanies.map((c) => (
        <div key={c.code} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '2px 0' }}>
          <span style={{ color: colors.text }}>{c.name}（{c.code}）</span>
          <span style={{ color: c.direction === 'positive' ? '#ef4444' : '#22c55e', fontWeight: 600 }}>
            {c.direction === 'positive' ? '+' : ''}{(c.impactPct ?? 0).toFixed(2)}%
          </span>
        </div>
      ))}
    </div>
  );
}

/** DSA 传导引擎控制台（设计 §3.1 引擎规则 + 三情景并行传导）。 */
const DsaEnginePage: React.FC<{ seed?: DsaEngineSeed }> = ({ seed }) => {
  const chains: IndustryChainListItem[] = seed?.chains ?? [];
  const gParams = seed?.params ?? [];

  const [chainId, setChainId] = useState<string>(chains[0]?.id ?? 'lithium');
  const [shockNode, setShockNode] = useState<string>('');
  const [magnitude, setMagnitude] = useState<number>(0.2);
  const [kind, setKind] = useState<string>('cost');

  // 引擎参数默认值来自 dsa_global_params（设计 §3.1）
  const gp = (k: string, d: number) => {
    const p = gParams.find((x) => x.paramKey === k);
    return p ? p.paramValue : d;
  };
  const [maxDepth, setMaxDepth] = useState<number>(gp('recursion_depth', 20));
  const [bd, setBd] = useState<number>(gp('coeff_threshold', 0.85));
  const [bearish, setBearish] = useState<number>(gp('bearish_weight', 0.7));
  const [useOverrides, setUseOverrides] = useState<boolean>(true);

  const [single, setSingle] = useState<PropagateResult | null>(seed?.propagate ?? null);
  const [scenarios, setScenarios] = useState<ScenarioResult | null>(seed?.scenarios ?? null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (seed?.propagate || seed?.scenarios) return;
    industryChainApi.list().then((r) => {
      const items = r.items || [];
      if (items.length && !chainId) setChainId(items[0].id);
    }).catch(() => setErr('产业链目录加载失败'));
    industryChainApi.listEdgeOverrides(chainId).catch(() => undefined);
  }, []);

  const runPropagate = async () => {
    setErr(null); setMsg(null);
    try {
      const res = await industryChainApi.propagate(chainId, {
        node: shockNode, magnitude, kind, maxDepth, bidirectionalDecay: bd, bearishDecay: bearish, useOverrides,
      });
      setSingle(res);
      setMsg('传导推演完成');
    } catch (e) {
      setErr(e instanceof Error ? e.message : '传导失败');
    }
  };

  const runScenarios = async () => {
    setErr(null); setMsg(null);
    try {
      const res = await industryChainApi.propagateScenarios(chainId, {
        node: shockNode, magnitude, kind, maxDepth, bidirectionalDecay: bd, bearishDecay: bearish, useOverrides,
      });
      setScenarios(res.data);
      setMsg('三情景并行传导完成');
    } catch (e) {
      setErr(e instanceof Error ? e.message : '情景推演失败');
    }
  };

  return (
    <div style={{ padding: 16, color: colors.text }}>
      <div style={titleStyle}>DSA 传导引擎</div>
      <div style={subStyle}>
        设计 §3.1 引擎规则：递归深度≤{maxDepth} · 双向衰减{bd} · 利空衰减{bearish} · 系数区间[0,1] · 覆盖系数接入 chain_edge_override
      </div>

      <div style={{ ...cardStyle, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
        <div>
          <label style={labelStyle}>产业链</label>
          <select style={inputStyle} value={chainId} onChange={(e) => setChainId(e.target.value)}>
            {chains.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
            {chains.length === 0 && <option value="lithium">锂电池产业链</option>}
          </select>
        </div>
        <div>
          <label style={labelStyle}>冲击环节（名称/ID）</label>
          <input style={inputStyle} value={shockNode} placeholder="如：锂矿开采" onChange={(e) => setShockNode(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>冲击幅度 magnitude（{(magnitude * 100).toFixed(0)}%）</label>
          <input style={inputStyle} type="number" step={0.05} value={magnitude}
                 onChange={(e) => setMagnitude(Number(e.target.value))} />
        </div>
        <div>
          <label style={labelStyle}>冲击类型 kind</label>
          <select style={inputStyle} value={kind} onChange={(e) => setKind(e.target.value)}>
            {SHOCK_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>最大深度 maxDepth</label>
          <input style={inputStyle} type="number" value={maxDepth} onChange={(e) => setMaxDepth(Number(e.target.value))} />
        </div>
        <div>
          <label style={labelStyle}>双向衰减 bidirectionalDecay</label>
          <input style={inputStyle} type="number" step={0.05} value={bd} onChange={(e) => setBd(Number(e.target.value))} />
        </div>
        <div>
          <label style={labelStyle}>利空衰减 bearishDecay</label>
          <input style={inputStyle} type="number" step={0.05} value={bearish} onChange={(e) => setBearish(Number(e.target.value))} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <input type="checkbox" checked={useOverrides} onChange={(e) => setUseOverrides(e.target.checked)} />
          <span style={{ fontSize: 12, color: colors.textSecondary, marginLeft: 6 }}>启用自定义覆盖系数</span>
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <button style={btnStyle} onClick={runPropagate}>传导推演</button>
        <button style={btnGhost} onClick={runScenarios}>三情景并行传导</button>
        {msg && <span style={{ color: '#22c55e', fontSize: 12, marginLeft: 10 }}>{msg}</span>}
        {err && <span style={{ color: '#ef4444', fontSize: 12, marginLeft: 10 }}>{err}</span>}
      </div>

      {single && <ImpactBlock title="单冲击传导结果" res={single} />}

      {scenarios && (
        <div>
          <div style={{ fontWeight: 700, color: colors.text, margin: '6px 0 8px' }}>三情景并行传导</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            <ImpactBlock title="基准 Base" res={scenarios.base} />
            <ImpactBlock title="乐观 Optimistic" res={scenarios.optimistic} />
            <ImpactBlock title="悲观 Pessimistic" res={scenarios.pessimistic} />
          </div>
        </div>
      )}
    </div>
  );
};

export default DsaEnginePage;
