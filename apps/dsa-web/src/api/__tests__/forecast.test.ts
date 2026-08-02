import { beforeEach, describe, expect, it, vi } from 'vitest';
import { forecastApi } from '../forecast';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('../index', () => ({
  default: { post },
}));

// 后端真实返回（snake_case），验证前端 toCamelCase 映射链路
const SNAKE_BODY = {
  code: 200,
  msg: 'ok',
  data: {
    symbols: {
      '600519': {
        symbol: '600519',
        name: '600519',
        market: 'A',
        cycles: {
          '1w': {
            cycle: '1w',
            cycle_days: 5,
            design_days: 5,
            direction: 'up',
            direction_label: '震荡偏强',
            consensus_score: 0.62,
            up_probability: 65,
            confidence: 0.72,
            price_range: { low: 1680, high: 1750 },
            volatility_range_pct: { low: 0.02, high: 0.04 },
            core_drivers: ['地缘原油涨价'],
            main_risks: ['美联储临时讲话'],
            sub_model_scores: { timing: 0.6, fund_flow: 0.7 },
          },
          '2w': {
            cycle: '2w',
            cycle_days: 10,
            design_days: 10,
            direction: 'up',
            direction_label: '上行',
            consensus_score: 0.7,
            up_probability: 70,
            confidence: 0.75,
            price_range: { low: 1670, high: 1780 },
            volatility_range_pct: { low: 0.03, high: 0.07 },
            core_drivers: ['行业涨价落地'],
            main_risks: ['产能临时投放'],
            sub_model_scores: { timing: 0.65, fund_flow: 0.68 },
          },
          '1m': {
            cycle: '1m',
            cycle_days: 22,
            design_days: 22,
            direction: 'up',
            direction_label: '稳步上行',
            consensus_score: 0.76,
            up_probability: 76,
            confidence: 0.78,
            price_range: { low: 1650, high: 1820 },
            volatility_range_pct: { low: 0.06, high: 0.12 },
            core_drivers: ['财报高增'],
            main_risks: ['需求不及预期'],
            sub_model_scores: { timing: 0.7, fund_flow: 0.66 },
          },
          '6m': {
            cycle: '6m',
            cycle_days: 120,
            design_days: 120,
            direction: 'up',
            direction_label: '趋势上行',
            consensus_score: 0.81,
            up_probability: 81,
            confidence: 0.83,
            price_range: { low: 1600, high: 1900 },
            volatility_range_pct: { low: 0.15, high: 0.3 },
            core_drivers: ['长期产业扶持'],
            main_risks: ['全球经济衰退'],
            sub_model_scores: { timing: 0.8, fund_flow: 0.6 },
          },
        },
      },
    },
    cycles_requested: ['1w', '2w', '1m', '6m'],
    mode: 'synthetic',
    generated_at: '2026-08-01T23:00:00',
  },
};

describe('forecastApi.getMultiCycleForecast', () => {
  beforeEach(() => post.mockReset());

  it('发送正确路径与请求体，并将 snake_case 响应映射为 camelCase', async () => {
    post.mockResolvedValueOnce({ data: SNAKE_BODY });

    const result = await forecastApi.getMultiCycleForecast({
      symbols: ['600519'],
      market: 'A',
      mode: 'synthetic',
      seed: 42,
    });

    // 请求路径与字段正确
    expect(post).toHaveBeenCalledTimes(1);
    const [url, body] = post.mock.calls[0];
    expect(url).toBe('/api/v1/predict/multi-cycle');
    expect(body).toMatchObject({
      symbols: ['600519'],
      market: 'A',
      mode: 'synthetic',
      seed: 42,
    });

    // 响应结构 + 字段映射
    expect(result.code).toBe(200);
    expect(result.data.mode).toBe('synthetic');
    expect(result.data.cyclesRequested).toEqual(['1w', '2w', '1m', '6m']);
    const c1w = result.data.symbols['600519'].cycles['1w'];
    expect(c1w.directionLabel).toBe('震荡偏强');
    expect(c1w.volatilityRangePct).toEqual({ low: 0.02, high: 0.04 });
    expect(c1w.priceRange).toEqual({ low: 1680, high: 1750 });
    expect(c1w.coreDrivers).toEqual(['地缘原油涨价']);
    expect(c1w.subModelScores).toEqual({ timing: 0.6, fund_flow: 0.7 });
    expect(Object.keys(result.data.symbols['600519'].cycles)).toEqual(['1w', '2w', '1m', '6m']);
  });

  it('省略可选 cycles / seed 时不影响请求', async () => {
    post.mockResolvedValueOnce({ data: SNAKE_BODY });
    await forecastApi.getMultiCycleForecast({ symbols: ['600519'] });
    const [, body] = post.mock.calls[0];
    expect(body.cycles).toBeUndefined();
    expect(body.seed).toBeUndefined();
  });
});

describe('forecastApi.runDsaPropagation', () => {
  beforeEach(() => post.mockReset());

  it('发送 graph/shock 并返回 camelCase 传导结果', async () => {
    post.mockResolvedValueOnce({
      data: {
        code: 200,
        msg: 'ok',
        data: {
          node_impacts: [{ node: 'n1', depth: 0, impact: 0.5, kind: 'cost' }],
          company_impacts: [{ symbol: '600519', total_impact: 0.2, upstream_impact: 0.1, downstream_impact: 0.1 }],
          summary: { max_abs_impact: 0.5, affected_nodes: 1, affected_companies: 1 },
        },
      },
    });

    const result = await forecastApi.runDsaPropagation({
      graph: { nodes: [], edges: [] },
      shock: { node: 'n1', magnitude: 0.5, kind: 'cost' },
    });

    const [url, body] = post.mock.calls[0];
    expect(url).toBe('/api/v1/predict/dsa-propagation');
    expect(body).toMatchObject({ graph: { nodes: [] }, shock: { node: 'n1' } });
    expect(result.data.nodeImpacts[0].nodeName).toBeUndefined();
    expect(result.data.companyImpacts[0].totalImpact).toBe(0.2);
    expect(result.data.summary.maxAbsImpact).toBe(0.5);
  });
});
