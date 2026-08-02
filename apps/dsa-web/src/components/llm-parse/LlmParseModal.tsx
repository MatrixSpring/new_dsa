import { useState } from 'react';
import type { CSSProperties } from 'react';
import { llmParseApi } from '../../api/llmParse';
import ParseResultView from './ParseResultView';
import type {
  CompareData,
  ConstraintData,
  LlmParseDocType,
  LongTermData,
  ParseDocumentData,
} from '../../types/llmParse';

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
const inputStyle: CSSProperties = {
  background: '#0b1220',
  color: '#dbe4f3',
  border: '1px solid #1f2d44',
  borderRadius: 8,
  padding: 10,
  fontSize: 13,
};

const DOC_TYPES: LlmParseDocType[] = [
  'policy',
  'broker_report',
  'prospectus',
  'meeting_minutes',
  'industry_white_paper',
  'other',
];
const DOC_LABELS: Record<LlmParseDocType, string> = {
  policy: '政策',
  broker_report: '券商研报',
  prospectus: '招股书',
  meeting_minutes: '会议纪要',
  industry_white_paper: '行业白皮书',
  other: '其他',
};

type TabKey = 'document' | 'compare' | 'constraints' | 'long-term';
const TABS: { key: TabKey; label: string }[] = [
  { key: 'document', label: '分层拆解' },
  { key: 'compare', label: '多文档对比' },
  { key: 'constraints', label: '隐藏约束' },
  { key: 'long-term', label: '长期规划' },
];

/** 交互弹窗：四模式解析（DSA-OPT-LLM-001 Phase 2 全能力）。 */
export default function LlmParseModal({ onClose }: { onClose?: () => void }) {
  const [tab, setTab] = useState<TabKey>('document');
  const [text, setText] = useState('');
  const [textB, setTextB] = useState('');
  const [titleB, setTitleB] = useState('文档B');
  const [docType, setDocType] = useState<LlmParseDocType>('policy');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<
    ParseDocumentData | CompareData | ConstraintData | LongTermData | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  const handleParse = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      let resp;
      if (tab === 'compare') {
        if (!text.trim() || !textB.trim()) {
          setError('请粘贴文档A与文档B文本');
          setLoading(false);
          return;
        }
        resp = await llmParseApi.compareDocuments({
          documents: [
            { title: '文档A', text },
            { title: titleB || '文档B', text: textB },
          ],
        });
      } else if (tab === 'constraints') {
        if (!text.trim()) { setError('请粘贴待解析文本'); setLoading(false); return; }
        resp = await llmParseApi.mineConstraints(text);
      } else if (tab === 'long-term') {
        if (!text.trim()) { setError('请粘贴待解析文本'); setLoading(false); return; }
        resp = await llmParseApi.extractLongTerm(text);
      } else {
        if (!text.trim()) { setError('请粘贴待解析文本'); setLoading(false); return; }
        resp = await llmParseApi.parseDocument({ text, docType, mode: 'deep' });
      }
      if (resp.code === 0 && resp.data) {
        setResult(resp.data);
      } else {
        setError(resp.msg || '解析失败');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求异常');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(2,6,23,0.7)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        style={{ ...card, width: 680, maxHeight: '88vh', overflow: 'auto' }}
        onClick={(e) => e.stopPropagation()}
        data-testid="llm-parse-modal"
      >
        <div style={{ ...blockTitle, fontSize: 15 }}>长文本深度解析（DSA-OPT-LLM-001）</div>

        {/* 模式 Tab */}
        <div style={{ display: 'flex', gap: 6, margin: '10px 0' }}>
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => { setTab(t.key); setResult(null); setError(null); }}
              data-testid={`tab-${t.key}`}
              style={{
                background: tab === t.key ? '#2563eb' : '#0b1220',
                color: tab === t.key ? '#fff' : '#94a3b8',
                border: '1px solid #1f2d44',
                borderRadius: 8,
                padding: '6px 12px',
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* 文档类型（仅分层拆解模式需要） */}
        {tab === 'document' && (
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value as LlmParseDocType)}
            style={{ ...inputStyle, width: '100%', marginBottom: 10 }}
          >
            {DOC_TYPES.map((t) => (
              <option key={t} value={t}>{DOC_LABELS[t]}</option>
            ))}
          </select>
        )}

        {/* 文本输入 */}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={tab === 'compare' ? '粘贴文档A 原文…' : '粘贴政策原文 / 券商研报 / 招股书 / 会议纪要…'}
          style={{ ...inputStyle, width: '100%', minHeight: tab === 'compare' ? 90 : 120 }}
        />
        {tab === 'compare' && (
          <>
            <input
              value={titleB}
              onChange={(e) => setTitleB(e.target.value)}
              placeholder="文档B 标题"
              style={{ ...inputStyle, width: '100%', marginTop: 10 }}
            />
            <textarea
              value={textB}
              onChange={(e) => setTextB(e.target.value)}
              placeholder="粘贴文档B 原文…"
              style={{ ...inputStyle, width: '100%', minHeight: 90, marginTop: 10 }}
            />
          </>
        )}

        <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
          <button
            onClick={handleParse}
            disabled={loading}
            data-testid="parse-btn"
            style={{
              background: loading ? '#334155' : '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              padding: '6px 16px',
              cursor: 'pointer',
            }}
          >
            {loading ? '解析中…' : '开始解析'}
          </button>
          {onClose && (
            <button
              onClick={onClose}
              style={{ background: '#1f2d44', color: '#dbe4f3', border: 'none', borderRadius: 8, padding: '6px 12px', cursor: 'pointer' }}
            >
              关闭
            </button>
          )}
        </div>

        {error && <div style={{ color: '#f87171', marginTop: 10 }} data-testid="parse-error">{error}</div>}
        {result && (
          <div style={{ marginTop: 12 }}>
            <ParseResultView data={result} />
          </div>
        )}
      </div>
    </div>
  );
}
