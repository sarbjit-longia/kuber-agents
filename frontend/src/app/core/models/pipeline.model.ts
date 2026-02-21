/**
 * Pipeline Models
 * 
 * TypeScript models for pipelines, agents, and executions.
 */

export interface Agent {
  agent_type: string;
  name: string;
  description: string;
  category: string;
  version: string;
  icon?: string;
  pricing_rate: number;
  is_free: boolean;
  requires_timeframes: string[];
  requires_market_data: boolean;
  requires_position: boolean;
  config_schema: AgentConfigSchema;
}

export interface AgentConfigSchema {
  type: string;
  title: string;
  description?: string;
  properties: { [key: string]: any };
  required: string[];
}

export interface PipelineNode {
  id: string;
  agent_type: string;
  config: { [key: string]: any };
  position?: { x: number; y: number };
}

export interface PipelineEdge {
  from: string;
  to: string;
}

export interface PipelineConfig {
  symbol?: string;
  mode?: 'live' | 'paper' | 'simulation' | 'validation';
  /**
   * Optional pipeline-level broker tool configuration. Used by the guided builder
   * to enforce a single broker across Risk Manager + Trade Manager.
   */
  broker_tool?: any;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

export enum TriggerMode {
  SIGNAL = 'signal',
  PERIODIC = 'periodic'
}

export interface SignalSubscription {
  signal_type: string;
  timeframe?: string;
  min_confidence?: number;
}

export interface Pipeline {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  config: PipelineConfig;
  is_active: boolean;
  trigger_mode: TriggerMode;
  scanner_id?: string;
  signal_subscriptions?: SignalSubscription[];
  scanner_tickers?: string[]; // Deprecated - for backward compatibility
  notification_enabled: boolean;
  notification_events?: string[];
  require_approval: boolean;
  approval_modes?: string[];
  approval_timeout_minutes: number;
  approval_channels?: string[];
  approval_phone?: string;
  created_at: string;
  updated_at: string;
}

export interface PipelineCreate {
  name: string;
  description?: string;
  config: PipelineConfig;
  trigger_mode?: TriggerMode;
  scanner_id?: string;
  signal_subscriptions?: SignalSubscription[];
  notification_enabled?: boolean;
  notification_events?: string[];
  require_approval?: boolean;
  approval_modes?: string[];
  approval_timeout_minutes?: number;
  approval_channels?: string[];
  approval_phone?: string;
}

export interface PipelineUpdate {
  name?: string;
  description?: string;
  config?: PipelineConfig;
  is_active?: boolean;
  trigger_mode?: TriggerMode;
  scanner_id?: string;
  signal_subscriptions?: SignalSubscription[];
  scanner_tickers?: string[]; // Deprecated
  notification_enabled?: boolean;
  notification_events?: string[];
  require_approval?: boolean;
  approval_modes?: string[];
  approval_timeout_minutes?: number;
  approval_channels?: string[];
  approval_phone?: string;
}

export enum ExecutionStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
  SKIPPED = 'skipped'
}

export interface Execution {
  id: string;
  pipeline_id: string;
  user_id: string;
  status: ExecutionStatus;
  result?: any;
  error_message?: string;
  cost: number;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface ExecutionCreate {
  pipeline_id: string;
  mode?: 'live' | 'paper' | 'simulation' | 'validation';
}

export interface ExecutionLog {
  timestamp: string;
  agent_id: string;
  level: string;
  message: string;
}

export interface WebSocketMessage {
  type: 'connected' | 'execution_update' | 'execution_log' | 'execution_complete' | 'subscribed' | 'unsubscribed' | 'error' | 'pong';
  execution_id?: string;
  message?: string;
  data?: any;
  user_id?: string;
}

