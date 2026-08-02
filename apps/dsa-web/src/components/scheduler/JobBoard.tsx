import type { CSSProperties } from 'react';
import type { SchedulerJob, SchedulerJobRun } from '../../types/scheduler';

const wrap: CSSProperties = {
  background: '#0e1626',
  border: '1px solid #1f2d44',
  borderRadius: 10,
  padding: 14,
  color: '#dbe4f3',
  fontSize: 13,
};
const table: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 13,
};
const th: CSSProperties = {
  textAlign: 'left',
  color: '#7dd3fc',
  fontWeight: 600,
  padding: '8px 10px',
  borderBottom: '1px solid #1f2d44',
};
const td: CSSProperties = {
  padding: '8px 10px',
  borderBottom: '1px solid #162034',
  verticalAlign: 'top',
};
const GROUP_LABEL: Record<string, string> = {
  core: '核心',
  crawl: '爬虫',
  monitor: '监控',
};

/** 纯展示组件：定时任务表格 + 最近运行日志（SSR 安全，无副作用/无 echarts）。 */
export default function JobBoard({
  jobs,
  runs,
}: {
  jobs: SchedulerJob[];
  runs?: SchedulerJobRun[];
}) {
  return (
    <div style={wrap} data-testid="job-board">
      <table style={table}>
        <thead>
          <tr>
            <th style={th}>任务</th>
            <th style={th}>分组</th>
            <th style={th}>触发</th>
            <th style={th}>状态</th>
            <th style={th}>下次运行</th>
            <th style={th}>上次运行</th>
            <th style={th}>累计</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} data-testid={`job-${j.id}`}>
              <td style={td}>
                <div style={{ fontWeight: 600, color: '#fff' }}>{j.name}</div>
                <div style={{ color: '#86909C', fontSize: 12 }}>{j.description}</div>
              </td>
              <td style={td}>{GROUP_LABEL[j.group] ?? j.group}</td>
              <td style={td}>{j.triggerLabel}</td>
              <td style={td}>
                <span
                  style={{
                    color: j.enabled ? '#34d399' : '#f87171',
                    fontWeight: 600,
                  }}
                >
                  {j.enabled ? '启用' : '停用'}
                </span>
                {j.lastStatus ? (
                  <span style={{ color: '#64748b', marginLeft: 6 }}>
                    ({j.lastStatus})
                  </span>
                ) : null}
              </td>
              <td style={{ ...td, color: j.nextRunAt ? '#dbe4f3' : '#64748b' }}>
                {j.nextRunAt ? j.nextRunAt.replace('T', ' ') : '—'}
              </td>
              <td style={{ ...td, color: '#94a3b8' }}>
                {j.lastRunAt ? j.lastRunAt.replace('T', ' ') : '—'}
              </td>
              <td style={td}>{j.runCount}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 最近运行日志（设计 §5.3 表4） */}
      <div style={{ marginTop: 16, fontWeight: 600, color: '#7dd3fc' }} data-testid="runs-title">
        最近运行日志
      </div>
      {runs && runs.length > 0 ? (
        <table style={{ ...table, marginTop: 8 }} data-testid="runs-table">
          <thead>
            <tr>
              <th style={th}>任务</th>
              <th style={th}>状态</th>
              <th style={th}>开始</th>
              <th style={th}>摘要</th>
            </tr>
          </thead>
          <tbody>
            {runs.slice(0, 10).map((r) => (
              <tr key={r.id} data-testid={`run-${r.id}`}>
                <td style={td}>{r.jobKey}</td>
                <td style={td}>
                  <span
                    style={{
                      color:
                        r.status === 'success'
                          ? '#34d399'
                          : r.status === 'failed'
                          ? '#f87171'
                          : '#fbbf24',
                      fontWeight: 600,
                    }}
                  >
                    {r.status}
                  </span>
                </td>
                <td style={{ ...td, color: '#94a3b8' }}>
                  {r.startedAt ? r.startedAt.replace('T', ' ') : '—'}
                </td>
                <td style={{ ...td, color: '#86909C' }}>{r.summary ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ marginTop: 8, color: '#64748b' }} data-testid="runs-empty">
          暂无运行记录，触发任务后将在此显示。
        </div>
      )}
    </div>
  );
}
