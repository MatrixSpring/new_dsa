/**
 * 动态聚合页（设计 §2.1/§2.2/§2.3：全球动态 / 国内动态 / 单日动态）
 * 复用现有 dashboard + intelligence 接口。按 variant 配置渲染：
 *  - 左：情报筛选（天数 / 关键词）+ 刷新
 *  - 中：情报信息流 + 各仪表盘面板（市场趋势 / 政策赛道 / 个股速览 / 资金博弈 / 风控）
 *  - 右：关联入口（前瞻预测中心 / AI 建议）+ 概览 KPI
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Globe, Landmark, CalendarClock, RefreshCw, AlertTriangle, ArrowRight, Sparkles } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { dynamicsApi } from '../api/dynamics';
import {
  IntelligenceFeed,
  KpiCard,
  MarketTrendPanel,
  PolicyTrackPanel,
  StockRecentPanel,
  GameShortPanel,
  GameLongPanel,
  RiskOverviewPanel,
} from '../components/dynamics/DynamicsViews';
import LlmParseModal from '../components/llm-parse/LlmParseModal';
import IntelligenceImpactPanel from '../components/IntelligenceImpactPanel';
import type {
  DynamicsPanelKey,
  DynamicsVariant,
  DynamicsVariantConfig,
  GameLongData,
  GameShortData,
  IntelligenceItemList,
  MarketTrendData,
  PolicyTrackData,
  RiskOverviewData,
  StockRecentData,
} from '../types/dynamics';

const VARIANT_CONFIG: Record<DynamicsVariant, DynamicsVariantConfig & { subtitle: string; icon: 'global' | 'domestic' | 'daily' }> = {
  global: {
    title: '全球动态',
    subtitle: '全球股指、地缘政策与跨市场资金联动，把握外围对 A 股的传导',
    intelligenceMarket: 'global',
    panels: ['marketTrend', 'riskOverview', 'gameLong'],
    icon: 'global',
  },
  domestic: {
    title: '国内动态',
    subtitle: '国内政策赛道、个股异动与短线资金博弈，聚焦本土景气变化',
    intelligenceMarket: 'cn',
    panels: ['policyTrack', 'stockRecent', 'gameShort', 'riskOverview'],
    icon: 'domestic',
  },
  daily: {
    title: '单日动态',
    subtitle: '当日市场趋势、个股速览与长短线资金博弈，复盘盘中结构',
    panels: ['marketTrend', 'stockRecent', 'gameShort', 'gameLong'],
    icon: 'daily',
  },
};

const PANEL_TITLE: Record<DynamicsPanelKey, string> = {
  marketTrend: '市场趋势',
  policyTrack: '国家政策赛道',
  stockRecent: '个股速览',
  gameShort: '短线资金博弈',
  gameLong: '长线赛道轮动',
  riskOverview: '风控概览',
};

const EMPTY_INTEL: IntelligenceItemList = { items: [], total: 0, page: 1, pageSize: 50 };
const DAY_OPTIONS = [1, 3, 7, 14, 30];

type PanelBucket = { data: unknown; error: string | null };

export default function DynamicsCenterPage({ variant }: { variant: DynamicsVariant }) {
  const cfg = VARIANT_CONFIG[variant];
  const [days, setDays] = useState<number>(7);
  const [query, setQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [intel, setIntel] = useState<IntelligenceItemList>(EMPTY_INTEL);
  const [intelError, setIntelError] = useState<string | null>(null);
  const [parseOpen, setParseOpen] = useState<boolean>(false);
  const [panelData, setPanelData] = useState<Record<DynamicsPanelKey, PanelBucket>>(() => {
    const init = {} as Record<DynamicsPanelKey, PanelBucket>;
    (Object.keys(PANEL_TITLE) as DynamicsPanelKey[]).forEach((k) => {
      init[k] = { data: null, error: null };
    });
    return init;
  });

  const timeRange = days <= 1 ? '1d' : days <= 3 ? '3d' : days <= 7 ? '7d' : days <= 14 ? '14d' : '30d';

  const fetchIntelligence = useCallback(async () => {
    if (!cfg.intelligenceMarket) return;
    setIntelError(null);
    try {
      const list = await dynamicsApi.getIntelligenceItems({
        market: cfg.intelligenceMarket,
        days,
        query: query.trim() || undefined,
      });
      setIntel(list);
    } catch (e) {
      setIntelError(e instanceof Error ? e.message : '情报加载失败');
    }
  }, [cfg.intelligenceMarket, days, query]);

  const fetchPanel = useCallback(
    async (panel: DynamicsPanelKey) => {
      try {
        let data: unknown;
        switch (panel) {
          case 'marketTrend':
            data = await dynamicsApi.getMarketTrend(timeRange);
            break;
          case 'policyTrack':
            data = await dynamicsApi.getPolicyTrack();
            break;
          case 'stockRecent':
            data = await dynamicsApi.getStockRecent();
            break;
          case 'gameShort':
            data = await dynamicsApi.getGameShort(timeRange);
            break;
          case 'gameLong':
            data = await dynamicsApi.getGameLong(timeRange);
            break;
          case 'riskOverview':
            data = await dynamicsApi.getRiskOverview();
            break;
        }
        setPanelData((prev) => ({ ...prev, [panel]: { data, error: null } }));
      } catch (e) {
        setPanelData((prev) => ({
          ...prev,
          [panel]: { data: null, error: e instanceof Error ? e.message : '加载失败' },
        }));
      }
    },
    [timeRange]
  );

  const loadAll = useCallback(async () => {
    setLoading(true);
    // 情报与面板并行拉取，各面板独立容错
    const tasks: Promise<void>[] = [];
    if (cfg.intelligenceMarket) tasks.push(fetchIntelligence());
    cfg.panels.forEach((p) => tasks.push(fetchPanel(p)));
    await Promise.all(tasks);
    setLoading(false);
  }, [cfg, fetchIntelligence, fetchPanel]);

  useEffect(() => {
    void loadAll();
    // 切换 variant 时重置情报
    setIntel(EMPTY_INTEL);
    setIntelError(null);
  }, [loadAll]);

  const iconEl = cfg.icon === 'global' ? <Globe size={20} color="#165DFF" /> : cfg.icon === 'domestic' ? <Landmark size={20} color="#165DFF" /> : <CalendarClock size={20} color="#165DFF" />;

  // 右栏概览 KPI（从已加载面板抽取）
  const overviewKpis = useMemo(() => {
    const kpis: { label: string; value: string; tone: 'up' | 'down' | 'neutral' | 'warn' }[] = [];
    const trend = panelData.marketTrend?.data as MarketTrendData | undefined;
    if (trend) {
      kpis.push({
        label: '趋势评分',
        value: trend.trendScore.toFixed(1),
        tone: trend.trendScore >= 55 ? 'up' : trend.trendScore <= 45 ? 'down' : 'neutral',
      });
    }
    const gs = panelData.gameShort?.data as GameShortData | undefined;
    if (gs) {
      kpis.push({
        label: '短线博弈',
        value: gs.gameScore.toFixed(1),
        tone: gs.gameScore >= 55 ? 'up' : 'down',
      });
    }
    const gl = panelData.gameLong?.data as GameLongData | undefined;
    if (gl) {
      kpis.push({
        label: '长线博弈',
        value: gl.baseGameScore.toFixed(1),
        tone: gl.baseGameScore >= 55 ? 'up' : 'down',
      });
    }
    const ro = panelData.riskOverview?.data as RiskOverviewData | undefined;
    if (ro) {
      kpis.push({
        label: '接口失败率',
        value: `${ro.systemRisk.interfaceFailRate.toFixed(2)}%`,
        tone: ro.systemRisk.interfaceFailRate > 3 ? 'warn' : 'neutral',
      });
    }
    return kpis;
  }, [panelData]);

  return (
    <div style={{ padding: 20, maxWidth: 1680, margin: '0 auto' }}>
      {/* Header */}
      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 20, marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 20, color: '#fff', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
            {iconEl} {cfg.title}
          </h2>
          <p style={{ fontSize: 13, color: '#86909C' }}>{cfg.subtitle}</p>
        </div>
        <button className="dsa-btn" onClick={() => void loadAll()} disabled={loading}>
          {loading ? <span className="scan-line" style={{ display: 'inline-block', width: 90, height: 18 }} /> : <><RefreshCw size={14} style={{ marginRight: 6 }} />刷新</>}
        </button>
        <button className="dsa-btn dsa-btn-ghost" onClick={() => setParseOpen(true)} style={{ marginLeft: 8 }}>
          <Sparkles size={14} style={{ marginRight: 6 }} />LLM 深度解读
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr 300px', gap: 16, alignItems: 'start' }}>
        {/* 左：筛选 */}
        <div className="glass-card" style={{ padding: 16 }}>
          <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>筛选条件</h3>
          {cfg.intelligenceMarket ? (
            <>
              <label style={{ fontSize: 12, color: '#86909C', display: 'block', marginBottom: 6 }}>情报时间范围（天）</label>
              <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="dsa-input" style={{ width: '100%', marginBottom: 12 }} aria-label="情报天数">
                {DAY_OPTIONS.map((d) => (
                  <option key={d} value={d}>{d} 天</option>
                ))}
              </select>
              <label style={{ fontSize: 12, color: '#86909C', display: 'block', marginBottom: 6 }}>关键词（可选）</label>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="dsa-input"
                style={{ width: '100%', marginBottom: 12 }}
                placeholder="如：半导体 / 美联储"
                aria-label="关键词"
              />
            </>
          ) : (
            <p style={{ fontSize: 12, color: '#86909C', lineHeight: 1.6 }}>单日动态汇聚全市场当日信息流，无需按地区筛选。</p>
          )}
          <div style={{ fontSize: 11, color: '#86909C', borderTop: '1px solid #22262F', paddingTop: 10 }}>
            当前展示面板：{cfg.panels.map((p) => PANEL_TITLE[p]).join(' · ')}
          </div>
        </div>

        {/* 中：情报 + 面板 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {cfg.intelligenceMarket ? (
            <IntelligenceFeed data={intel} loading={loading && intel.items.length === 0} error={intelError} emptyText="该范围内暂无情报" />
          ) : null}

          {cfg.panels.map((panel) => {
            const bucket = panelData[panel];
            if (bucket.error) {
              return (
                <div key={panel} className="glass-card" style={{ padding: 16, borderColor: '#F53F3F', color: '#F53F3F' }}>
                  <AlertTriangle size={14} style={{ marginRight: 6 }} />{PANEL_TITLE[panel]}：{bucket.error}
                </div>
              );
            }
            if (!bucket.data) {
              return (
                <div key={panel} className="glass-card" style={{ padding: 24, color: '#86909C', textAlign: 'center' }}>
                  {PANEL_TITLE[panel]} 加载中…
                </div>
              );
            }
            return <PanelRenderer key={panel} panel={panel} data={bucket.data} />;
          })}
        </div>

        {/* 右：关联入口 + 概览 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="glass-card" style={{ padding: 16 }}>
            <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>概览</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
              {overviewKpis.length === 0 ? (
                <span style={{ fontSize: 12, color: '#86909C' }}>面板加载后展示关键评分</span>
              ) : (
                overviewKpis.map((k) => <KpiCard key={k.label} label={k.label} value={k.value} tone={k.tone} />)
              )}
            </div>
          </div>

          <div className="glass-card" style={{ padding: 16 }}>
            <h3 style={{ fontSize: 15, color: '#fff', marginBottom: 12, borderLeft: '3px solid #165DFF', paddingLeft: 8 }}>关联分析</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <NavLink to="/forecast-center" className="dsa-btn dsa-btn-ghost" style={{ justifyContent: 'space-between' }}>
                前瞻预测中心 <ArrowRight size={14} />
              </NavLink>
              <NavLink to="/decision-signals" className="dsa-btn dsa-btn-ghost" style={{ justifyContent: 'space-between' }}>
                AI 建议 <ArrowRight size={14} />
              </NavLink>
            </div>
          </div>

          <IntelligenceImpactPanel />
        </div>
      </div>
      {parseOpen && <LlmParseModal onClose={() => setParseOpen(false)} />}
    </div>
  );
}

/** 按面板 key 渲染对应纯展示组件（类型在此处收窄） */
function PanelRenderer({ panel, data }: { panel: DynamicsPanelKey; data: unknown }) {
  switch (panel) {
    case 'marketTrend':
      return <MarketTrendPanel data={data as MarketTrendData} />;
    case 'policyTrack':
      return <PolicyTrackPanel data={data as PolicyTrackData} />;
    case 'stockRecent':
      return <StockRecentPanel data={data as StockRecentData} />;
    case 'gameShort':
      return <GameShortPanel data={data as GameShortData} />;
    case 'gameLong':
      return <GameLongPanel data={data as GameLongData} />;
    case 'riskOverview':
      return <RiskOverviewPanel data={data as RiskOverviewData} />;
    default:
      return null;
  }
}
