// 定时任务可视化类型（对齐 src/services/job_registry.py，经 toCamelCase 映射）
export interface SchedulerTrigger {
  kind: string; // daily / weekly / interval
  time?: string;
  dow?: number;
  seconds?: number;
}

export interface SchedulerJob {
  id: string;
  name: string;
  group: string;
  description: string;
  trigger: SchedulerTrigger;
  triggerLabel: string;
  enabled: boolean;
  lastRunAt: string | null;
  lastStatus: string | null;
  nextRunAt: string | null;
  runCount: number;
}

export interface SchedulerRuntime {
  enabled?: boolean;
  running?: boolean;
  scheduleTimes?: string[];
  nextRunAt?: string | null;
  lastRunAt?: string | null;
  lastError?: string | null;
}

export interface SchedulerJobsResponse {
  code: number;
  msg: string;
  data: {
    jobs: SchedulerJob[];
    runtime: SchedulerRuntime | null;
  };
}

export interface SchedulerJobResponse {
  code: number;
  msg: string;
  data: SchedulerJob;
}

export interface SchedulerJobRun {
  id: number;
  jobKey: string;
  startedAt: string | null;
  finishedAt: string | null;
  status: string | null; // success / failed / running
  summary: string | null;
  error: string | null;
}

export interface SchedulerRunsResponse {
  code: number;
  total: number;
  items: SchedulerJobRun[];
}
