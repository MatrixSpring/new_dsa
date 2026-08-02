import { useEffect, useState } from 'react';
import { crawlApi } from '../api/crawl';
import type {
  CrawlDocument,
  CrawlSource,
} from '../types/crawl';

const STATUS_COLOR: Record<string, string> = {
  pending: '#fbbf24',
  fetched: '#38bdf8',
  parsed: '#34d399',
  failed: '#f87171',
};

const DOC_TYPE_LABEL: Record<string, string> = {
  policy: '政策',
  report: '研报',
  prospectus: '招股书',
  minutes: '纪要',
};

/** 自动爬虫 + 长文本解析流水线中心（P0）：抓取源 → 一键抓取解析 → 结果列表。 */
const CrawlCenterPage: React.FC<{ seed?: { sources: CrawlSource[]; documents: CrawlDocument[] } }> = ({
  seed,
}) => {
  const [sources, setSources] = useState<CrawlSource[]>(seed?.sources ?? []);
  const [documents, setDocuments] = useState<CrawlDocument[]>(seed?.documents ?? []);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    crawlApi.listSources().then((r) => setSources(r.data ?? [])).catch(() => setErr('抓取源加载失败'));
    crawlApi.listDocuments(50).then((r) => setDocuments(r.items ?? [])).catch(() => setErr('文档加载失败'));
  };

  useEffect(() => {
    if (seed) return;
    load();
  }, [seed]);

  const runSource = (key: string) => {
    setBusyKey(key);
    setErr(null);
    setMsg(null);
    crawlApi
      .run(key)
      .then((r) => {
        if (r.code === 0 && r.data) {
          setMsg(`「${r.data.title}」抓取并解析完成`);
          setDocuments((prev) => [r.data as CrawlDocument, ...prev.filter((d) => d.id !== r.data!.id)]);
        } else {
          setErr(r.msg || '抓取失败');
        }
      })
      .catch((e) => setErr(e instanceof Error ? e.message : '请求异常'))
      .finally(() => setBusyKey(null));
  };

  return (
    <div style={{ padding: 24, color: '#e6edf3', maxWidth: 1080, margin: '0 auto' }} data-testid="crawl-center">
      <h2 style={{ margin: '0 0 4px', color: '#fff' }}>自动爬虫 · 长文本解析中心</h2>
      <div style={{ color: '#86909C', marginBottom: 16, fontSize: 13 }}>
        抓取源 → LLM 结构化解析 → 落地库（P0 流水线，外挂不改 DSA 内核）
      </div>

      {msg ? <div style={{ color: '#34d399', marginBottom: 12 }}>{msg}</div> : null}
      {err ? <div style={{ color: '#f87171', marginBottom: 12 }}>{err}</div> : null}

      <div style={{ marginBottom: 24 }}>
        <div style={{ fontWeight: 600, marginBottom: 8, color: '#c9d1d9' }}>抓取源</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
          {sources.map((s) => (
            <div
              key={s.key}
              data-testid={`source-${s.key}`}
              style={{
                background: '#161b22',
                border: '1px solid #30363d',
                borderRadius: 10,
                padding: 14,
              }}
            >
              <div style={{ fontWeight: 600, color: '#fff', marginBottom: 4 }}>{s.name}</div>
              <div style={{ color: '#86909C', fontSize: 12, marginBottom: 6 }}>
                {DOC_TYPE_LABEL[s.docType] ?? s.docType} · 适配器 {s.adapter}
              </div>
              <div style={{ color: '#8b949e', fontSize: 12, marginBottom: 10, minHeight: 32 }}>{s.description}</div>
              <button
                data-testid={`run-${s.key}`}
                disabled={busyKey === s.key}
                onClick={() => runSource(s.key)}
                style={{
                  background: busyKey === s.key ? '#374151' : '#2563eb',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 6,
                  padding: '6px 14px',
                  cursor: busyKey === s.key ? 'default' : 'pointer',
                }}
              >
                {busyKey === s.key ? '抓取中…' : '抓取并解析'}
              </button>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div style={{ fontWeight: 600, marginBottom: 8, color: '#c9d1d9' }}>
          已解析文档（{documents.length}）
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {documents.map((d) => (
            <div
              key={d.id}
              data-testid={`doc-${d.id}`}
              style={{ background: '#0d1117', border: '1px solid #30363d', borderRadius: 10, padding: 14 }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontWeight: 600, color: '#fff' }}>{d.title}</div>
                <span style={{ color: STATUS_COLOR[d.status] ?? '#94a3b8', fontWeight: 600 }}>
                  {d.status}
                </span>
              </div>
              <div style={{ color: '#86909C', fontSize: 12, margin: '4px 0 8px' }}>
                来源 {d.sourceKey} · 原始 {d.rawLength} 字
                {d.parsedAt ? ` · 解析于 ${d.parsedAt.replace('T', ' ')}` : ''}
              </div>
              {d.parsed ? (
                <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                  <div><b style={{ color: '#a5b4fc' }}>短期(1w)：</b>{d.parsed.shortTerm1w}</div>
                  <div><b style={{ color: '#a5b4fc' }}>中期(1m)：</b>{d.parsed.midTerm1m}</div>
                  <div><b style={{ color: '#a5b4fc' }}>长期(半年)：</b>{d.parsed.longTermHalfyear}</div>
                  <div><b style={{ color: '#fbbf24' }}>隐藏约束：</b>{d.parsed.hiddenConstraint}</div>
                  <div><b style={{ color: '#f87171' }}>潜在风险：</b>{d.parsed.potentialRisk}</div>
                  <div><b style={{ color: '#34d399' }}>可靠性：</b>{d.parsed.reliability}</div>
                </div>
              ) : (
                <div style={{ color: '#64748b', fontSize: 12 }}>暂无结构化解析结果</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default CrawlCenterPage;
