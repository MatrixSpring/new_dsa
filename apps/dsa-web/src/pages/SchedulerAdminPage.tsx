/**
 * 运维后台：定时任务可视化（设计 §4.2 六段可视化之一）
 * 任务清单 + 启停 + 手动触发，数据来自 /api/v1/scheduler/jobs。
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, PlayCircle, Power } from 'lucide-react';
import { schedulerApi } from '../api/scheduler';
import JobBoard from '../components/scheduler/JobBoard';
import type { SchedulerJob, SchedulerJobRun, SchedulerRuntime } from '../types/scheduler';

export default function SchedulerAdminPage() {
  const [jobs, setJobs] = useState<SchedulerJob[]>([]);
  const [runtime, setRuntime] = useState<SchedulerRuntime | null>(null);
  const [runs, setRuns] = useState<SchedulerJobRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await schedulerApi.getJobs();
      if (resp.code === 0 && resp.data) {
        setJobs(resp.data.jobs);
        setRuntime(resp.data.runtime);
      } else {
        setError(resp.msg || '加载失败');
      }
      const r = await schedulerApi.getRuns();
      if (r.code === 0) setRuns(r.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求异常');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleToggle = async (job: SchedulerJob) => {
    setBusyId(job.id);
    try {
      const resp = await schedulerApi.toggleJob(job.id, !job.enabled);
      if (resp.code === 0 && resp.data) {
        setJobs((prev) => prev.map((j) => (j.id === job.id ? resp.data : j)));
      }
    } finally {
      setBusyId(null);
    }
  };

  const handleRun = async (job: SchedulerJob) => {
    setBusyId(job.id);
    try {
      const resp = await schedulerApi.runJob(job.id);
      if (resp.code === 0 && resp.data) {
        setJobs((prev) => prev.map((j) => (j.id === job.id ? resp.data : j)));
      }
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={{ padding: 20, maxWidth: 1320, margin: '0 auto' }}>
      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 20, marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 20, color: '#fff', marginBottom: 6 }}>定时任务可视化</h2>
          <p style={{ fontSize: 13, color: '#86909C' }}>
            爬虫 / 解析 / 主分析流水线的自动化调度总览
            {runtime ? ` · 引擎${runtime.enabled ? '已启用' : '未启用'}${runtime.running ? '（运行中）' : ''}` : ''}
          </p>
        </div>
        <button className="dsa-btn" onClick={() => void load()} disabled={loading}>
          {loading ? <span className="scan-line" style={{ display: 'inline-block', width: 90, height: 18 }} /> : <><RefreshCw size={14} style={{ marginRight: 6 }} />刷新</>}
        </button>
      </div>

      {error && (
        <div className="glass-card" style={{ padding: 16, borderColor: '#F53F3F', color: '#F53F3F', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {jobs.length === 0 && !loading ? (
        <div className="glass-card" style={{ padding: 24, color: '#86909C', textAlign: 'center' }}>暂无任务</div>
      ) : (
        <JobBoard jobs={jobs} runs={runs} />
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
        {jobs.map((j) => (
          <div key={j.id} className="glass-card" style={{ padding: '8px 12px', display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ color: '#dbe4f3', fontSize: 13 }}>{j.name}</span>
            <button className="dsa-btn dsa-btn-ghost" disabled={busyId === j.id} onClick={() => handleToggle(j)} style={{ padding: '4px 10px' }}>
              <Power size={13} style={{ marginRight: 4 }} />{j.enabled ? '停用' : '启用'}
            </button>
            <button className="dsa-btn dsa-btn-ghost" disabled={busyId === j.id} onClick={() => handleRun(j)} style={{ padding: '4px 10px' }}>
              <PlayCircle size={13} style={{ marginRight: 4 }} />触发
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
