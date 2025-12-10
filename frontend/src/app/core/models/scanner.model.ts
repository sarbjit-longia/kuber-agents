/**
 * Scanner models for managing ticker lists
 */

export enum ScannerType {
  MANUAL = 'manual',
  FILTER = 'filter',
  API = 'api'
}

export interface SignalSubscription {
  signal_type: string;
  min_confidence?: number;
}

export interface Scanner {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  scanner_type: ScannerType;
  config: {
    tickers?: string[];
    [key: string]: any;
  };
  is_active: boolean;
  refresh_interval?: number;
  last_refreshed_at?: string;
  created_at: string;
  updated_at: string;
  ticker_count?: number;
  pipeline_count?: number;
}

export interface ScannerCreate {
  name: string;
  description?: string;
  scanner_type: ScannerType;
  config: {
    tickers?: string[];
    [key: string]: any;
  };
  is_active?: boolean;
  refresh_interval?: number;
}

export interface ScannerUpdate {
  name?: string;
  description?: string;
  config?: {
    tickers?: string[];
    [key: string]: any;
  };
  is_active?: boolean;
  refresh_interval?: number;
}

export interface ScannerTickers {
  scanner_id: string;
  scanner_name: string;
  tickers: string[];
  ticker_count: number;
  last_refreshed_at?: string;
}

export interface ScannerUsage {
  scanner_id: string;
  scanner_name: string;
  pipeline_count: number;
  pipelines: Array<{
    id: string;
    name: string;
    is_active: boolean;
    trigger_mode: string;
  }>;
}

export interface SignalType {
  signal_type: string;
  name: string;
  description: string;
  generator: string;
  is_free: boolean;
  typical_frequency: string;
  requires_confidence_filter: boolean;
  default_confidence?: number;
  icon: string;
  category: string;
}

