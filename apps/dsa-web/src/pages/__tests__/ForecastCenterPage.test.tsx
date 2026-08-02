import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ForecastCenterPage from '../ForecastCenterPage';

// 避免 jsdom 下 canvas 报错：用空组件替换 echarts-for-react
vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

const mockGetMultiCycle = vi.fn();

vi.mock('../api/forecast', () => ({
  forecastApi: {
    getMultiCycleForecast: (...args: unknown[]) => mockGetMultiCycle(...args),
    runDsaPropagation: vi.fn(),
  },
}));

// 已为 camelCase（等同于客户端 toCamelCase 之后的结果）
const CAMEL_RESPONSE = {
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
            cycle: '1w', cycleDays: 5, designDays: 5, direction: 'up', directionLabel: '震荡偏强',
            consensusScore: 0.62, upProbability: 65, confidence: 0.72,
            priceRange: { low: 1680, high: 1750 }, volatilityRangePct: { low: 0.02, high: 0.04 },
            coreDrivers: ['地缘原油涨价'], mainRisks: ['美联储临时讲话'], subModelScores: { timing: 0.6, fund_flow: 0.7 },
          },
          '2w': {
            cycle: '2w', cycleDays: 10, designDays: 10, direction: 'up', directionLabel: '上行',
            consensusScore: 0.7, upProbability: 70, confidence: 0.75,
            priceRange: { low: 1670, high: 1780 }, volatilityRangePct: { low: 0.03, high: 0.07 },
            coreDrivers: ['行业涨价落地'], mainRisks: ['产能临时投放'], subModelScores: { timing: 0.65, fund_flow: 0.68 },
          },
          '1m': {
            cycle: '1m', cycleDays: 22, designDays: 22, direction: 'up', directionLabel: '稳步上行',
            consensusScore: 0.76, upProbability: 76, confidence: 0.78,
            priceRange: { low: 1650, high: 1820 }, volatilityRangePct: { low: 0.06, high: 0.12 },
            coreDrivers: ['财报高增'], mainRisks: ['需求不及预期'], subModelScores: { timing: 0.7, fund_flow: 0.66 },
          },
          '6m': {
            cycle: '6m', cycleDays: 120, designDays: 120, direction: 'up', directionLabel: '趋势上行',
            consensusScore: 0.81, upProbability: 81, confidence: 0.83,
            priceRange: { low: 1600, high: 1900 }, volatilityRangePct: { low: 0.15, high: 0.3 },
            coreDrivers: ['长期产业扶持'], mainRisks: ['全球经济衰退'], subModelScores: { timing: 0.8, fund_flow: 0.6 },
          },
        },
      },
    },
    cyclesRequested: ['1w', '2w', '1m', '6m'],
    mode: 'synthetic',
    generatedAt: '2026-08-01T23:00:00',
  },
};

describe('ForecastCenterPage 请求数据 → 显示', () => {
  beforeEach(() => {
    mockGetMultiCycle.mockReset();
    window.localStorage.clear();
  });

  it('点击批量预测后，将四周期标准化预测渲染进表格（数据→显示）', async () => {
    mockGetMultiCycle.mockResolvedValueOnce(CAMEL_RESPONSE);

    render(<ForecastCenterPage />);

    // 触发请求
    fireEvent.click(screen.getByText('批量预测'));

    // 表格行出现（请求返回并渲染）
    const row = await screen.findByTestId('row-600519');
    expect(row).toBeInTheDocument();

    // 四个周期表头
    expect(screen.getByText('1周')).toBeInTheDocument();
    expect(screen.getByText('半月')).toBeInTheDocument();
    expect(screen.getByText('1月')).toBeInTheDocument();
    expect(screen.getByText('半年')).toBeInTheDocument();

    // 单元格包含方向 / 涨概 / 置信
    const cell = screen.getByTestId('cell-600519-1w');
    expect(cell).toHaveTextContent('震荡偏强');
    expect(cell).toHaveTextContent('65%');
    expect(cell).toHaveTextContent('72%');

    // 右栏因子拆解
    expect(screen.getByText('地缘原油涨价')).toBeInTheDocument();
    expect(screen.getByText('美联储临时讲话')).toBeInTheDocument();

    // 历史存档写入
    await waitFor(() => {
      expect(window.localStorage.getItem('dsa_forecast_history')).not.toBeNull();
    });
  });

  it('请求失败时显示错误提示且不崩溃', async () => {
    mockGetMultiCycle.mockRejectedValueOnce(new Error('网络异常'));
    render(<ForecastCenterPage />);
    fireEvent.click(screen.getByText('批量预测'));
    expect(await screen.findByText(/网络异常/)).toBeInTheDocument();
  });

  it('切换至预测复盘页显示历史存档入口', async () => {
    mockGetMultiCycle.mockResolvedValueOnce(CAMEL_RESPONSE);
    render(<ForecastCenterPage />);
    fireEvent.click(screen.getByText('批量预测'));
    await screen.findByTestId('row-600519');
    fireEvent.click(screen.getByText('预测复盘'));
    expect(await screen.findByText(/历史预测存档/)).toBeInTheDocument();
  });
});
