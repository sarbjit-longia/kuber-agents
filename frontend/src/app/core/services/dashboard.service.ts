/**
 * Dashboard Service
 *
 * Fetches aggregated dashboard data from the backend including
 * pipeline overview, execution stats, broker P&L, and active positions.
 */
import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, interval, switchMap, tap, catchError, of } from 'rxjs';
import { ApiService } from './api.service';

// ── Interfaces ────────────────────────────────────────────────

export interface DashboardPipelineStats {
  total: number;
  active: number;
  inactive: number;
  signal_based: number;
  periodic: number;
}

export interface DashboardExecutionStats {
  total: number;
  running: number;
  monitoring: number;
  completed: number;
  failed: number;
  total_cost: number;
  success_rate: number;
}

export interface DashboardPnL {
  total_realized: number;
  total_unrealized: number;
  total: number;
}

export interface DashboardToday {
  executions: number;
  cost: number;
  pnl: number;
}

export interface BrokerAccount {
  broker_name: string;
  account_id: string;
  account_type: string;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  total_trades: number;
  active_positions: number;
  pipeline_count: number;
}

export interface TradeInfo {
  order_status: string;
  order_type: string;
  side: string;
  entry_price: number;
  current_price: number;
  quantity: number;
  unrealized_pl: number;
  pnl_percent: number;
  take_profit: number;
  stop_loss: number;
}

export interface PnLInfo {
  value: number;
  percent: number | null;
  type: 'realized' | 'unrealized';
}

export interface BrokerInfo {
  tool_type: string;
  broker_name: string;
  account_id: string;
  account_type: string;
}

export interface ActivePosition {
  execution_id: string;
  pipeline_id: string;
  pipeline_name: string;
  symbol: string;
  mode: string;
  status: string;
  started_at: string;
  trade_info: TradeInfo | null;
  pnl: PnLInfo | null;
  broker: BrokerInfo | null;
}

export interface RecentExecution {
  execution_id: string;
  pipeline_name: string;
  symbol: string;
  mode: string;
  status: string;
  strategy_action: string | null;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  cost: number;
  pnl: PnLInfo | null;
}

export interface DashboardPipeline {
  id: string;
  name: string;
  is_active: boolean;
  trigger_mode: string;
  broker: BrokerInfo | null;
  total_executions: number;
  active_executions: number;
  completed_executions: number;
  failed_executions: number;
  total_pnl: number;
  created_at: string;
}

export interface CostHistoryEntry {
  date: string;
  cost: number;
}

export interface PnLHistoryEntry {
  date: string;
  pnl: number;
}

export interface TradeStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  best_trade: number;
  worst_trade: number;
  profit_factor: number;
}

export interface DashboardData {
  pipelines: DashboardPipelineStats;
  executions: DashboardExecutionStats;
  pnl: DashboardPnL;
  today: DashboardToday;
  broker_accounts: BrokerAccount[];
  active_positions: ActivePosition[];
  recent_executions: RecentExecution[];
  pipeline_list: DashboardPipeline[];
  cost_history: CostHistoryEntry[];
  pnl_history: PnLHistoryEntry[];
  trade_stats: TradeStats;
}

@Injectable({
  providedIn: 'root'
})
export class DashboardService {
  private dashboardSubject = new BehaviorSubject<DashboardData | null>(null);
  private loadingSubject = new BehaviorSubject<boolean>(false);

  dashboard$ = this.dashboardSubject.asObservable();
  loading$ = this.loadingSubject.asObservable();

  constructor(private apiService: ApiService) {}

  /**
   * Load dashboard data from backend.
   */
  loadDashboard(): Observable<DashboardData> {
    this.loadingSubject.next(true);
    return this.apiService.get<DashboardData>('/api/v1/dashboard/').pipe(
      tap(data => {
        this.dashboardSubject.next(data);
        this.loadingSubject.next(false);
      }),
      catchError(error => {
        console.error('Failed to load dashboard:', error);
        this.loadingSubject.next(false);
        throw error;
      })
    );
  }

  /**
   * Get current cached dashboard data.
   */
  getCurrentData(): DashboardData | null {
    return this.dashboardSubject.getValue();
  }
}
