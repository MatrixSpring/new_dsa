/**
 * 动态聚合页 纯展示组件（设计 §2.1/§2.2/§2.3）
 * 约束：无副作用、无 echarts、不引入 lucide 图标（保证 tsc 编译 + react-dom/server SSR 验证稳健）。
 * 所有内容用纯 HTML/CSS 表达，便于"请求数据 → 显示"全链路验证。
 */
import type {
  GameLongData,
  GameShortData,
  IntelligenceItem,
  IntelligenceItemList,
  MarketTrendData,
  PolicyTrackData,
  RiskOverviewData,
  StockRecentData,
} from '../../types/dynamics';

const UP_COLOR = '#F53F3F'; // 涨（红）
const DOWN_COLOR = '#00B42A'; // 跌（绿）
const NEUTRAL_COLOR = '#86909C';

function fmtNum(n: number | undefined | null, digits = 2): string {
  if (n == null || Number.isNaN(n)) return '-';
  return n.toFixed(digits);
}

function pctColor(n: number): string {
  if (n > 0) return UP_COLOR;
  if (n < 0) return DOWN_COLOR;
  return NEUTRAL_COLOR;
}

function marketLabel(market: string): string {
  const map: Record<string, string> = {
    cn: '中国', hk: '港股', us: '美股', jp: '日股', kr: '韩股', tw: '台股', global: '全球',
  };
  return map[market] ?? market;
}

function shortTime(s?: string | null): string {
  if (!s) return '';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

/* ============ KPI 卡片 ============ */
export function KpiCard({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'neutral' | 'up' | 'down' | 'warn';
}) {
  const color =
    tone === 'up' ? UP_COLOR : tone === 'down' ? DOWN_COLOR : tone === 'warn' ? '#FF7D00' : '#C9CDD4';
  return (
    <div className="glass-card" style={{ padding: 14, minWidth: 140 }}>
      <div style={{ fontSize: 12, color: '#86909C', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, color, fontWeight: 600 }} data-testid={`kpi-${label}`}>{value}</div>
      {hint ? <div style={{ fontSize: 11, color: '#86909C', marginTop: 4 }}>{hint}</div> : null}
    </div>
  );
}

/* ============ 情报信息流 ============ */
export function IntelligenceFeed({
  data,
  loading,
  error,
  emptyText = '暂无情报',
}: {
  data: IntelligenceItemList;
  loading?: boolean;
  error?: string | null;
  emptyText?: string;
}) {
  if (error) {
    return (
      <div className="glass-card" style={{ padding: 16, borderColor: '#F53F3F', color: '#F53F3F' }} data-testid="feed-error">
        情报加载失败：{error}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="glass-card" style={{ padding: 24, color: '#86909C', textAlign: 'center' }} data-testid="feed-loading">
        正在拉取情报…
      </div>
    );
  }
  if (!data.items || data.items.length === 0) {
    return (
      <div className="glass-card" style={{ padding: 24, color: '#86909C', textAlign: 'center' }} data-testid="feed-empty">
        {emptyText}
      </div>
    );
  }
  return (
    <div className="glass-card" style={{ padding: 8 }}>
      <div style={{ fontSize: 13, color: '#86909C', padding: '6px 8px' }} data-testid="feed-count">
        共 {data.total} 条情报
      </div>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {data.items.map((it: IntelligenceItem) => (
          <li
            key={it.id}
            data-testid={`feed-item-${it.id}`}
            style={{ padding: '12px 8px', borderTop: '1px solid #22262F' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
              <span
                style={{
                  fontSize: 11,
                  color: '#C9CDD4',
                  border: '1px solid #313643',
                  borderRadius: 6,
                  padding: '1px 6px',
                }}
              >
                {marketLabel(it.market)}
              </span>
              <span style={{ fontSize: 11, color: '#86909C' }}>{it.source ?? it.sourceName ?? it.sourceType}</span>
              <span style={{ fontSize: 11, color: '#86909C', marginLeft: 'auto' }}>{shortTime(it.publishedAt)}</span>
            </div>
            <a href={it.url} target="_blank" rel="noreferrer" style={{ color: '#fff', fontSize: 14, textDecoration: 'none' }} data-testid={`feed-title-${it.id}`}>
              {it.title}
            </a>
            {it.summary ? (
              <p style={{ fontSize: 12, color: '#86909C', margin: '6px 0 0', lineHeight: 1.5 }}>{it.summary}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ============ 市场趋势 ============ */
export function MarketTrendPanel({ data }: { data: MarketTrendData }) {
  const trendTone: 'up' | 'down' | 'neutral' =
    data.trendScore >= 55 ? 'up' : data.trendScore <= 45 ? 'down' : 'neutral';
  return (
    <div className="glass-card" style={{ padding: 16 }}>
      <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>
        市场趋势
      </h3>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <KpiCard label="趋势评分" value={fmtNum(data.trendScore, 1)} tone={trendTone} hint={data.trendStatus} />
      </div>
      <table className="dsa-tech-table" style={{ width: '100%' }}>
        <thead>
          <tr><th>指数</th><th>代码</th><th>涨跌幅</th></tr>
        </thead>
        <tbody>
          {data.indexList.map((idx) => (
            <tr key={idx.code} data-testid={`index-${idx.code}`}>
              <td>{idx.name}</td>
              <td>{idx.code}</td>
              <td style={{ color: pctColor(idx.changePct) }}>{fmtNum(idx.changePct, 2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4 style={{ fontSize: 13, color: '#C9CDD4', margin: '14px 0 8px' }}>行业热度 TOP</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.industryHotList.map((ind) => (
          <div key={ind.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: '#C9CDD4', width: 70 }}>{ind.name}</span>
            <div style={{ flex: 1, height: 8, background: '#22262F', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${Math.min(100, ind.boomScore)}%`, height: '100%', background: '#165DFF' }} />
            </div>
            <span style={{ fontSize: 11, color: '#86909C', width: 40, textAlign: 'right' }}>{fmtNum(ind.boomScore, 1)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ============ 政策赛道 ============ */
export function PolicyTrackPanel({ data }: { data: PolicyTrackData }) {
  return (
    <div className="glass-card" style={{ padding: 16 }}>
      <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>
        国家政策赛道
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {data.tracks.map((t) => (
          <div key={t.trackName} data-testid={`policy-${t.trackName}`} style={{ borderBottom: '1px solid #22262F', paddingBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 14, color: '#fff' }}>{t.trackName}</span>
              <span style={{ fontSize: 12, color: t.policyLevel.includes('强力') ? '#F53F3F' : '#FF7D00' }}>{t.policyLevel}</span>
            </div>
            <div style={{ fontSize: 12, color: '#86909C', margin: '4px 0' }}>{t.policyDesc}</div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: '#86909C' }}>景气</span>
              <div style={{ flex: 1, height: 6, background: '#22262F', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${Math.min(100, t.boomScore)}%`, height: '100%', background: '#36C9A8' }} />
              </div>
              <span style={{ fontSize: 11, color: '#C9CDD4' }}>{fmtNum(t.boomScore, 1)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ============ 个股速览 ============ */
export function StockRecentPanel({ data }: { data: StockRecentData }) {
  return (
    <div className="glass-card" style={{ padding: 16 }}>
      <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>
        个股速览
      </h3>
      <table className="dsa-tech-table" style={{ width: '100%' }}>
        <thead>
          <tr><th>代码</th><th>现价</th><th>量比</th><th>RSI</th><th>综合分</th><th>风险</th></tr>
        </thead>
        <tbody>
          {data.stocks.map((s) => (
            <tr key={s.stockCode} data-testid={`stock-${s.stockCode}`}>
              <td>{s.stockCode}</td>
              <td>{fmtNum(s.price, 2)}</td>
              <td>{fmtNum(s.volumeRatio, 2)}</td>
              <td>{fmtNum(s.rsi, 1)}</td>
              <td>{fmtNum(s.totalScore, 1)}</td>
              <td style={{ color: s.riskLevel === '高' ? '#F53F3F' : '#86909C' }}>{s.riskLevel}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ============ 短线资金博弈 ============ */
export function GameShortPanel({ data }: { data: GameShortData }) {
  return (
    <div className="glass-card" style={{ padding: 16 }}>
      <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>
        短线资金博弈
      </h3>
      <KpiCard label="博弈评分" value={fmtNum(data.gameScore, 1)} tone={data.gameScore >= 55 ? 'up' : 'down'} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
        <div>
          <h4 style={{ fontSize: 13, color: '#C9CDD4', marginBottom: 6 }}>主力净流入 TOP</h4>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, fontSize: 12, color: '#C9CDD4' }}>
            {data.mainFundList.map((m) => (
              <li key={m.code} data-testid={`main-${m.code}`} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}>
                <span>{m.code}</span>
                <span style={{ color: pctColor(m.mainNetIn) }}>{fmtNum(m.mainNetIn / 1e8, 2)}亿</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 style={{ fontSize: 13, color: '#C9CDD4', marginBottom: 6 }}>北向净流入 TOP</h4>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, fontSize: 12, color: '#C9CDD4' }}>
            {data.northFundList.map((n) => (
              <li key={n.code} data-testid={`north-${n.code}`} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}>
                <span>{n.code}</span>
                <span style={{ color: pctColor(n.northNetIn) }}>{fmtNum(n.northNetIn / 1e8, 2)}亿</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

/* ============ 长线赛道博弈 ============ */
export function GameLongPanel({ data }: { data: GameLongData }) {
  return (
    <div className="glass-card" style={{ padding: 16 }}>
      <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>
        长线赛道轮动
      </h3>
      <KpiCard label="基础博弈分" value={fmtNum(data.baseGameScore, 1)} tone={data.baseGameScore >= 55 ? 'up' : 'down'} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
        {data.industryRotateList.map((g) => (
          <div key={g.name} data-testid={`rotate-${g.name}`} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: '#C9CDD4', width: 70 }}>{g.name}</span>
            <div style={{ flex: 1, height: 8, background: '#22262F', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${Math.min(100, g.boomScore)}%`, height: '100%', background: '#165DFF' }} />
            </div>
            <span style={{ fontSize: 11, color: '#86909C', width: 40, textAlign: 'right' }}>{fmtNum(g.boomScore, 1)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ============ 风控概览 ============ */
export function RiskOverviewPanel({ data }: { data: RiskOverviewData }) {
  const statEntries = Object.entries(data.riskStat ?? {});
  return (
    <div className="glass-card" style={{ padding: 16 }}>
      <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>
        风控概览
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
        <KpiCard label="接口失败率" value={fmtNum(data.systemRisk.interfaceFailRate, 2) + '%'} tone={data.systemRisk.interfaceFailRate > 3 ? 'warn' : 'neutral'} />
        <KpiCard label="缓存命中率" value={fmtNum(data.systemRisk.cacheHitRate, 2) + '%'} tone="neutral" />
      </div>
      <h4 style={{ fontSize: 13, color: '#C9CDD4', marginBottom: 6 }}>风险分布</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#C9CDD4' }}>
        {statEntries.map(([k, v]) => (
          <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{k}</span>
            <span>{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
