import { useEffect, useState } from 'react';
import { companyApi } from '../api/company';
import type { CompanyDetail, RiskTag } from '../types/company';
import { colors } from '../theme/tokens';

const titleStyle: React.CSSProperties = { fontSize: 16, fontWeight: 700, color: colors.text, marginBottom: 12 };
const labelStyle: React.CSSProperties = { color: colors.textSecondary, fontSize: 12, marginBottom: 4, display: 'block' };
const inputStyle: React.CSSProperties = {
  background: '#0b1220', color: colors.text, border: `1px solid ${colors.border}`,
  borderRadius: 6, padding: '6px 8px', fontSize: 13, width: '100%',
};

type TabKey = 'basic' | 'finance' | 'holder' | 'risk';
const TABS: { key: TabKey; label: string }[] = [
  { key: 'basic', label: '基础信息' },
  { key: 'finance', label: '财务估值' },
  { key: 'holder', label: '关联产业链' },
  { key: 'risk', label: '风险标签' },
];

const fmt = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v));

/** 页面5 收尾：公司信息维护（Tab 化 + 风险高亮 + 自动识别）。 */
const CompanyMaintenancePage: React.FC<{ seed?: { detail?: CompanyDetail } }> = ({ seed }) => {
  const [q, setQ] = useState('');
  const [code, setCode] = useState(seed?.detail?.code ?? '');
  const [detail, setDetail] = useState<CompanyDetail | null>(seed?.detail ?? null);
  const [tab, setTab] = useState<TabKey>('risk');
  const [riskTags, setRiskTags] = useState<RiskTag[]>(seed?.detail?.riskTags ?? []);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // 自动装载首个公司（SSR/首次）
  useEffect(() => {
    if (seed?.detail) return;
    companyApi.list().then((r) => {
      if (r.items && r.items.length > 0) {
        setCode(r.items[0].code);
      }
    }).catch(() => setErr('公司列表加载失败'));
  }, []);

  useEffect(() => {
    if (!code || seed?.detail) return;
    setMsg(null);
    companyApi.get(code).then((d) => {
      setDetail(d);
      setRiskTags(d.riskTags || []);
    }).catch(() => setErr('公司详情加载失败'));
  }, [code]);

  const search = async () => {
    if (!q.trim()) return;
    const r = await companyApi.list(q.trim());
    if (r.items && r.items.length > 0) setCode(r.items[0].code);
    else setErr('未找到匹配公司');
  };

  const runRecognize = async () => {
    setErr(null);
    try {
      const r = await companyApi.computeRiskTags(code);
      setRiskTags(r.data.riskTags || []);
      setMsg(`已识别 ${r.data.total} 条风险标签`);
      // 刷新详情里的 riskTags
      const d = await companyApi.get(code);
      setDetail(d);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '识别失败');
    }
  };

  const goodCount = riskTags.filter((t) => t.level === '利好').length;
  const badCount = riskTags.filter((t) => t.level === '利空').length;

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }} data-testid="company-maintenance">
      <h2 style={titleStyle}>公司信息维护</h2>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input style={inputStyle} value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索代码/名称/拼音" data-testid="company-search" />
        <button style={{ background: '#2563eb', color: '#fff', border: 'none', borderRadius: 6, padding: '0 16px', cursor: 'pointer' }} onClick={search} data-testid="company-search-btn">搜索</button>
        {detail && (
          <span style={{ color: colors.textSecondary, fontSize: 13, alignSelf: 'center' }}>
            当前：{detail.name}（{detail.code}）
          </span>
        )}
      </div>

      {err && <div style={{ color: colors.danger, marginBottom: 12 }} data-testid="cm-error">{err}</div>}
      {msg && <div style={{ color: '#34d399', marginBottom: 12 }} data-testid="cm-msg">{msg}</div>}

      {/* Tab 头 */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            data-testid={`cm-tab-${t.key}`}
            style={{
              background: tab === t.key ? '#2563eb' : colors.card,
              color: tab === t.key ? '#fff' : colors.textSecondary,
              border: `1px solid ${colors.border}`,
              borderRadius: 8, padding: '6px 14px', cursor: 'pointer', fontSize: 13,
            }}
          >
            {t.label}
            {t.key === 'risk' && riskTags.length > 0 && (
              <span style={{ marginLeft: 6, color: tab === t.key ? '#fff' : '#fbbf24' }}>({riskTags.length})</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab 内容 */}
      <div style={{ background: colors.card, borderRadius: 8, padding: 18, border: `1px solid ${colors.border}` }} data-testid="cm-tab-content">
        {!detail && <div style={{ color: colors.textSecondary }}>加载中…</div>}

        {detail && tab === 'basic' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="名称" value={fmt(detail.name)} />
            <Field label="交易所" value={fmt(detail.exchange)} />
            <Field label="申万行业" value={fmt(detail.swIndustry)} />
            <Field label="主营" value={fmt(detail.mainBusiness)} />
            <Field label="ESG 评级" value={fmt(detail.esgRating)} />
            <Field label="关联产业链数" value={fmt(detail.linkedChainsCount)} />
          </div>
        )}

        {detail && tab === 'finance' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <Field label="PE" value={fmt(detail.pe)} />
            <Field label="PB" value={fmt(detail.pb)} />
            <Field label="PS" value={fmt(detail.ps)} />
            <Field label="现价" value={fmt(detail.price)} />
            <Field label="总市值" value={fmt(detail.totalMarketCap)} />
            <Field label="目标价" value={fmt(detail.consensusTargetPrice)} />
          </div>
        )}

        {detail && tab === 'holder' && (
          <div>
            <Field label="关联产业链" value={fmt(detail.linkedChainsCount)} />
            <div style={{ marginTop: 8, color: colors.textSecondary, fontSize: 13 }}>
              数据来源：{(detail.dataSources || []).join('、') || '—'}
            </div>
          </div>
        )}

        {detail && tab === 'risk' && (
          <div>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 12 }}>
              <span style={{ color: '#34d399' }}>利好 {goodCount}</span>
              <span style={{ color: colors.danger }}>利空 {badCount}</span>
              <button style={{ background: '#f59e0b', color: '#fff', border: 'none', borderRadius: 6, padding: '6px 14px', cursor: 'pointer' }} onClick={runRecognize} data-testid="cm-recognize">自动识别写库</button>
            </div>
            {riskTags.length === 0 && (
              <div style={{ color: colors.textSecondary, fontSize: 13 }}>暂无风险标签，点击「自动识别写库」生成。</div>
            )}
            {riskTags.map((t, i) => (
              <div key={i}
                style={{
                  padding: '8px 10px', marginBottom: 6, borderRadius: 6,
                  border: `1px solid ${t.level === '利好' ? '#34d399' : colors.danger}`,
                  background: t.level === '利好' ? 'rgba(52,211,153,0.08)' : 'rgba(248,113,113,0.08)',
                }}
                data-testid="cm-risk-tag"
              >
                <b style={{ color: t.level === '利好' ? '#34d399' : colors.danger }}>[{t.level}] {t.tag}</b>
                <span style={{ color: colors.textSecondary, fontSize: 12, marginLeft: 8 }}>{t.note}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const Field: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div>
    <div style={labelStyle}>{label}</div>
    <div style={{ color: colors.text, fontSize: 14 }}>{value}</div>
  </div>
);

export default CompanyMaintenancePage;
