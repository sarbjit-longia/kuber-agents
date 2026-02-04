/**
 * Execution Models
 * 
 * TypeScript models for pipeline execution and monitoring
 */

export interface Execution {
  id: string;
  pipeline_id: string;
  pipeline_name?: string;
  user_id: string;
  status: ExecutionStatus;
  mode: ExecutionMode;
  symbol?: string;
  trigger_mode?: 'signal' | 'periodic';
  scanner_name?: string;
  started_at: string;
  completed_at?: string;
  error_message?: string;
  result?: any;
  cost_breakdown?: CostBreakdown;
  agent_states?: AgentState[];
  logs?: ExecutionLog[];
  reports?: { [agentId: string]: AgentReport };
  execution_artifacts?: any; // Chart data and other execution outputs
  created_at: string;
  updated_at: string;
}

export type ExecutionStatus = 
  | 'pending'
  | 'running'
  | 'monitoring'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'paused'
  | 'communication_error'; // API failure during monitoring

export type ExecutionMode = 
  | 'live'
  | 'paper'
  | 'simulation'
  | 'validation';

export interface AgentState {
  agent_id: string;
  agent_type: string;
  agent_name?: string;
  status: AgentStatus;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  output?: any;
  cost?: number;
}

export interface AgentReportMetric {
  name: string;
  value: any;
  unit?: string;
  description?: string;
}

export interface AgentReport {
  agent_id: string;
  agent_type: string;
  title: string;
  summary: string;
  status: string;
  details?: string;
  metrics?: AgentReportMetric[];
  data?: any;
  created_at: string;
}

export type AgentStatus = 
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped';

export interface CostBreakdown {
  total_cost: number;
  llm_cost: number;
  agent_rental_cost: number;
  api_call_cost: number;
  by_agent: {
    [agent_type: string]: number;
  };
}

export interface ExecutionLog {
  id: string;
  execution_id: string;
  timestamp: string;
  level: LogLevel;
  agent_type?: string;
  message: string;
  details?: any;
}

export type LogLevel = 
  | 'debug'
  | 'info'
  | 'warning'
  | 'error'
  | 'critical';

export interface ExecutionSummary {
  id: string;
  pipeline_id: string;
  pipeline_name: string;
  status: ExecutionStatus;
  mode: ExecutionMode;
  symbol?: string;
  trigger_mode?: 'signal' | 'periodic';
  scanner_name?: string;
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  total_cost: number;
  agent_count: number;
  agents_completed: number;
  error_message?: string;
}

export interface ExecutionStats {
  total_executions: number;
  running_executions: number;
  completed_executions: number;
  failed_executions: number;
  total_cost: number;
  avg_duration_seconds: number;
  success_rate: number;
}

