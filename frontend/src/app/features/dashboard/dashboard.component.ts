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

  recentColumns = ['symbol', 'pipeline', 'action', 'status', 'pnl', 'cost', 'time'];
  pipelineColumns = ['name', 'status', 'broker', 'executions', 'pnl'];

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

  getActionClass(action: string | null): string {
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
