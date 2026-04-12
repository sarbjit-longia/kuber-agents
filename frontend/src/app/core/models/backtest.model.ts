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
