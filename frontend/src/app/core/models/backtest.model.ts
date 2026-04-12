export type BacktestRunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface BacktestCreateRequest {
  pipeline_id: string;
  symbols: string[];
  start_date: string;
  end_date: string;
  timeframe: string;
  initial_capital: number;
  slippage_model: string;
  slippage_value: number;
  commission_model: string;
  commission_value: number;
  max_cost_usd?: number | null;
}

export interface BacktestStartResponse {
  run_id: string;
  status: BacktestRunStatus;
}

export interface BacktestRunSummary {
  id: string;
  pipeline_id?: string | null;
  pipeline_name?: string | null;
  status: BacktestRunStatus;
  config: Record<string, any>;
  progress: Record<string, any>;
  metrics?: Record<string, any> | null;
  trades_count: number;
  estimated_cost?: number | null;
  actual_cost: number;
  failure_reason?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface BacktestRunResult extends BacktestRunSummary {
  equity_curve: number[];
  trades: Record<string, any>[];
}

export interface BacktestRunListResponse {
  backtests: BacktestRunSummary[];
  total: number;
}

export interface BacktestExecutionSummary {
  id: string;
  pipeline_id: string;
  status: string;
  mode: string;
  symbol?: string | null;
  cost: number;
  error_message?: string | null;
  execution_phase?: string | null;
  result: Record<string, any>;
  logs: Record<string, any>[];
  agent_states: Record<string, any>[];
  reports: Record<string, any>;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface BacktestExecutionListResponse {
  executions: BacktestExecutionSummary[];
  total: number;
}

export interface BacktestTimelineEvent {
  id: string;
  ts: string;
  level: string;
  type: string;
  title: string;
  message: string;
  symbol?: string | null;
  execution_id?: string | null;
  data: Record<string, any>;
}

export interface BacktestTimelineResponse {
  events: BacktestTimelineEvent[];
}

export interface BacktestReportResponse {
  generated_at: string;
  summary: Record<string, any>;
  sections: Array<{ title: string; items: string[] }>;
  llm_analysis?: {
    executive_summary?: string;
    strengths?: string[];
    weaknesses?: string[];
    recommendations?: string[];
  } | null;
}
