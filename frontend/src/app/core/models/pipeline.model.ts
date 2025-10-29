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
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

export interface Pipeline {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  config: PipelineConfig;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PipelineCreate {
  name: string;
  description?: string;
  config: PipelineConfig;
}

export interface PipelineUpdate {
  name?: string;
  description?: string;
  config?: PipelineConfig;
  is_active?: boolean;
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

