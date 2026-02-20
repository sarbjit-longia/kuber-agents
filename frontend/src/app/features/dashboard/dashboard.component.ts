/**
 * Dashboard Component
 *
 * Main dashboard view showing pipeline overview, P&L per account,
 * active positions, broker accounts, and recent activity.
 */
import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatTableModule } from '@angular/material/table';
import { MatDividerModule } from '@angular/material/divider';
import { MatBadgeModule } from '@angular/material/badge';
import { Subject, interval, takeUntil, switchMap } from 'rxjs';

import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { ApiService } from '../../core/services/api.service';
import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';
import {
  DashboardService,
  DashboardData,
  BrokerAccount,
  ActivePosition,
  RecentExecution,
  DashboardPipeline,
  CostHistoryEntry,
  PnLHistoryEntry,
  TradeStats,
} from '../../core/services/dashboard.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatTableModule,
    MatDividerModule,
    MatBadgeModule,
    NavbarComponent,
    LocalDatePipe,
  ],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();

  data: DashboardData | null = null;
  healthStatus: any = null;
  loading = true;
  error: string | null = null;
  lastUpdated: Date | null = null;

  recentColumns = ['symbol', 'pipeline', 'action', 'pnl', 'cost', 'time'];
  pipelineColumns = ['name', 'status', 'broker', 'executions', 'completed', 'failed', 'pnl'];

  // Chart display settings
  costChartDays = 14;
  pnlChartDays = 14;

  constructor(
    private dashboardService: DashboardService,
    private apiService: ApiService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.loadAll();

    // Auto-refresh every 30 seconds
    interval(30000)
      .pipe(
        takeUntil(this.destroy$),
        switchMap(() => this.dashboardService.loadDashboard())
      )
      .subscribe({
        next: (data) => {
          this.data = data;
          this.lastUpdated = new Date();
        },
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadAll(): void {
    this.loading = true;
    this.error = null;

    // Load health + dashboard in parallel
    this.apiService.healthCheck().subscribe({
      next: (res) => (this.healthStatus = res),
      error: () => (this.healthStatus = null),
    });

    this.dashboardService.loadDashboard().subscribe({
      next: (data) => {
        this.data = data;
        this.loading = false;
        this.lastUpdated = new Date();
      },
      error: (err) => {
        console.error('Dashboard load failed:', err);
        this.error = 'Failed to load dashboard data. Please try again.';
        this.loading = false;
      },
    });
  }

  refresh(): void {
    this.loadAll();
  }

  // ── Navigation ─────────────────────────────────────────────

  goToMonitoring(): void {
    this.router.navigate(['/monitoring']);
  }

  goToPipelines(): void {
    this.router.navigate(['/pipelines']);
  }

  goToPipelineBuilder(): void {
    this.router.navigate(['/guided-builder']);
  }

  viewPosition(pos: ActivePosition): void {
    this.router.navigate(['/monitoring', pos.execution_id]);
  }

  viewPipeline(pipeline: DashboardPipeline): void {
    this.router.navigate(['/guided-builder', pipeline.id]);
  }

  // ── Formatting ─────────────────────────────────────────────

  formatPnL(value: number | null | undefined): string {
    if (value === null || value === undefined) return '-';
    const sign = value >= 0 ? '+' : '';
    return `${sign}$${value.toFixed(2)}`;
  }

  formatPercent(value: number | null | undefined): string {
    if (value === null || value === undefined) return '';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  }

  formatCost(cost: number): string {
    if (!cost) return '$0.00';
    return `$${cost.toFixed(4)}`;
  }

  formatDate(dateStr: string | null): string {
    if (!dateStr) return '-';
    // Ensure UTC dates from backend are treated as UTC before converting to local
    let isoString = dateStr;
    if (!dateStr.endsWith('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
      isoString = dateStr + 'Z';
    }
    const d = new Date(isoString);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  formatDuration(seconds: number | null): string {
    if (!seconds) return '-';
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  }

  formatSuccessRate(rate: number): string {
    return `${(rate * 100).toFixed(1)}%`;
  }

  // ── Chart helpers ─────────────────────────────────────────

  getCostChartData(): CostHistoryEntry[] {
    if (!this.data?.cost_history) return [];
    return this.data.cost_history.slice(-this.costChartDays);
  }

  getPnLChartData(): PnLHistoryEntry[] {
    if (!this.data?.pnl_history) return [];
    return this.data.pnl_history.slice(-this.pnlChartDays);
  }

  getBarHeight(value: number, entries: { cost?: number; pnl?: number }[], key: 'cost' | 'pnl'): number {
    const values = entries.map(e => Math.abs((e as any)[key] || 0));
    const maxVal = Math.max(...values, 0.001);
    return Math.max((Math.abs(value) / maxVal) * 100, 2);
  }

  getCostChartMax(): number {
    const data = this.getCostChartData();
    if (!data.length) return 0;
    return Math.max(...data.map(d => d.cost));
  }

  getPnLChartMax(): number {
    const data = this.getPnLChartData();
    if (!data.length) return 0;
    return Math.max(...data.map(d => Math.abs(d.pnl)), 0.01);
  }

  formatChartDate(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  formatShortDate(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { day: 'numeric' });
  }

  getTotalCostForPeriod(): number {
    return this.getCostChartData().reduce((sum, d) => sum + d.cost, 0);
  }

  getTotalPnLForPeriod(): number {
    return this.getPnLChartData().reduce((sum, d) => sum + d.pnl, 0);
  }

  /** Returns 0–100 representing how tall the bar should be within its half */
  getPnLBarPercent(pnl: number): number {
    const maxAbs = this.getPnLChartMax();
    if (maxAbs === 0) return 0;
    return Math.max((Math.abs(pnl) / maxAbs) * 100, 4);
  }

  getFilteredRecentExecutions(): RecentExecution[] {
    if (!this.data?.recent_executions) return [];
    return this.data.recent_executions.filter(e => {
      if (!e.pnl) return false;
      return e.pnl.value !== null && e.pnl.value !== undefined && e.pnl.value !== 0;
    });
  }

  // ── Pipeline P&L chart helpers ────────────────────────────

  getPipelinePnLData(): DashboardPipeline[] {
    if (!this.data?.pipeline_list) return [];
    return this.data.pipeline_list.filter(p => p.total_pnl !== 0);
  }

  getPipelinePnLMax(): number {
    const data = this.getPipelinePnLData();
    if (!data.length) return 1;
    return Math.max(...data.map(p => Math.abs(p.total_pnl)), 0.01);
  }

  getPipelineBarHeight(pnl: number): number {
    const maxVal = this.getPipelinePnLMax();
    // Returns 0-50 (half the chart height since baseline is at 50%)
    return Math.max((Math.abs(pnl) / maxVal) * 50, 3);
  }

  getPipelineBarLabel(name: string): string {
    if (!name) return '';
    return name.length > 12 ? name.substring(0, 10) + '…' : name;
  }

  // ── Style helpers ──────────────────────────────────────────

  getPnLClass(value: number | null | undefined): string {
    if (value === null || value === undefined) return '';
    return value >= 0 ? 'pnl-positive' : 'pnl-negative';
  }

  getStatusClass(status: string): string {
    const s = (status || '').toLowerCase();
    if (s === 'monitoring' || s === 'running') return 'status-active';
    if (s === 'completed') return 'status-completed';
    if (s === 'failed') return 'status-failed';
    return '';
  }

  getStatusIcon(status: string): string {
    const s = (status || '').toLowerCase();
    if (s === 'monitoring') return 'visibility';
    if (s === 'running') return 'play_circle';
    if (s === 'completed') return 'check_circle';
    if (s === 'failed') return 'error';
    return 'help';
  }

  getActionIcon(action: string | null): string {
    if (!action) return 'remove';
    const a = action.toUpperCase();
    if (a === 'BUY') return 'trending_up';
    if (a === 'SELL') return 'trending_down';
    return 'remove';
  }

  getActionClass(action: string | null | undefined): string {
    if (!action) return '';
    const a = action.toUpperCase();
    if (a === 'BUY') return 'action-buy';
    if (a === 'SELL') return 'action-sell';
    return '';
  }

  getBrokerIcon(brokerName: string): string {
    const name = (brokerName || '').toLowerCase();
    if (name.includes('oanda')) return 'currency_exchange';
    if (name.includes('alpaca')) return 'pets';
    if (name.includes('tradier')) return 'account_balance';
    return 'business';
  }

  getAccountTypeClass(accountType: string): string {
    const t = (accountType || '').toLowerCase();
    if (t === 'paper' || t === 'practice' || t === 'demo') return 'account-paper';
    return 'account-live';
  }

  getMaskedAccountId(accountId: string): string {
    if (!accountId || accountId.length <= 6) return accountId || '-';
    return '•••' + accountId.slice(-4);
  }
}
