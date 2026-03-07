/**
 * Dashboard Component – v2
 *
 * Main dashboard view showing pipeline overview, P&L per account,
 * active positions, broker accounts, and recent activity.
 */
import { Component, OnInit, OnDestroy, HostListener } from '@angular/core';
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
import { FooterComponent } from '../../shared/components/footer/footer.component';
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
  EquityByBroker,
  EquityByPipeline,
  CalendarDayData,
  TradingScore,
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
    FooterComponent,
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

  // Analytics chart colors
  private chartColors = ['#10b981', '#06b6d4', '#8b5cf6', '#f59e0b', '#ef4444', '#ec4899'];

  // Calendar state
  calendarMonth = new Date().getMonth();
  calendarYear = new Date().getFullYear();
  selectedCalendarDay: CalendarDayData | null = null;
  calendarPopoverTop = 0;
  calendarPopoverLeft = 0;

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

  // ── Compare helpers ───────────────────────────────────────

  /** Returns 0–100 width% for a value relative to the max of two values. */
  compareBarPct(value: number, other: number): number {
    const max = Math.max(Math.abs(value), Math.abs(other), 0.01);
    return (Math.abs(value) / max) * 100;
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

  getPositionSideClass(pos: ActivePosition): string {
    const side = (pos.trade_info?.side || '').toUpperCase();
    if (side === 'BUY' || side === 'LONG') return 'position-side-buy';
    if (side === 'SELL' || side === 'SHORT') return 'position-side-sell';
    return '';
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

  // ── SVG Equity Chart helpers ───────────────────────────────

  // Shared SVG chart dimensions — full-bleed with small bottom padding for legend gap
  private svgW = 400;
  private svgH = 150;
  private svgPadLeft = 0;
  private svgPadTop = 0;
  private svgPadBot = 15;

  private buildSvgPolyline(
    data: { date: string; equity: number }[],
    allSeries: { date: string; equity: number }[][]
  ): string {
    if (!data.length) return '';
    const allVals = allSeries.flat().map(d => d.equity);
    const minY = Math.min(...allVals, 0);
    const maxY = Math.max(...allVals, 0);
    const range = maxY - minY || 1;
    const usableW = this.svgW - this.svgPadLeft;
    const usableH = this.svgH - this.svgPadTop - this.svgPadBot;

    return data
      .map((d, i) => {
        const x = this.svgPadLeft + (data.length > 1 ? (i / (data.length - 1)) * usableW : usableW / 2);
        const y = this.svgPadTop + usableH - ((d.equity - minY) / range) * usableH;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  }

  /** Builds SVG area paths split at zero baseline: greenPath (above zero) and redPath (below zero). */
  private buildSvgSplitAreaPaths(
    data: { date: string; equity: number }[],
    allSeries: { date: string; equity: number }[][]
  ): { greenPath: string; redPath: string } {
    if (data.length < 2) return { greenPath: '', redPath: '' };
    const allVals = allSeries.flat().map(d => d.equity);
    const minY = Math.min(...allVals, 0);
    const maxY = Math.max(...allVals, 0);
    const range = maxY - minY || 1;
    const usableW = this.svgW - this.svgPadLeft;
    const usableH = this.svgH - this.svgPadTop - this.svgPadBot;
    // Zero baseline in SVG coordinates
    const zeroY = this.svgPadTop + usableH - ((0 - minY) / range) * usableH;

    const points = data.map((d, i) => {
      const x = this.svgPadLeft + (data.length > 1 ? (i / (data.length - 1)) * usableW : usableW / 2);
      const y = this.svgPadTop + usableH - ((d.equity - minY) / range) * usableH;
      return { x, y };
    });

    // Green area: line clamped at zero baseline (above zero region)
    let greenPath = `M${points[0].x.toFixed(1)},${Math.min(points[0].y, zeroY).toFixed(1)}`;
    for (let i = 1; i < points.length; i++) {
      greenPath += ` L${points[i].x.toFixed(1)},${Math.min(points[i].y, zeroY).toFixed(1)}`;
    }
    greenPath += ` L${points[points.length - 1].x.toFixed(1)},${zeroY.toFixed(1)}`;
    greenPath += ` L${points[0].x.toFixed(1)},${zeroY.toFixed(1)} Z`;

    // Red area: line clamped at zero baseline (below zero region)
    let redPath = `M${points[0].x.toFixed(1)},${Math.max(points[0].y, zeroY).toFixed(1)}`;
    for (let i = 1; i < points.length; i++) {
      redPath += ` L${points[i].x.toFixed(1)},${Math.max(points[i].y, zeroY).toFixed(1)}`;
    }
    redPath += ` L${points[points.length - 1].x.toFixed(1)},${zeroY.toFixed(1)}`;
    redPath += ` L${points[0].x.toFixed(1)},${zeroY.toFixed(1)} Z`;

    return { greenPath, redPath };
  }

  private getEquityYAxisInfo(allSeries: { date: string; equity: number }[][]): { min: number; max: number; mid: number; minPct: number; maxPct: number; midPct: number } {
    const allVals = allSeries.flat().map(d => d.equity);
    const min = Math.min(...allVals, 0);
    const max = Math.max(...allVals, 0);
    const range = max - min || 1;
    const mid = (min + max) / 2;
    // Returns top% positions (0% = top, 100% = bottom)
    const valToPct = (v: number) => (1 - (v - min) / range) * 100;
    return { min, max, mid, minPct: valToPct(min), maxPct: valToPct(max), midPct: valToPct(mid) };
  }

  /** Trim leading zero-only days across all series so charts start from first activity. */
  private trimLeadingZeros(seriesArray: { date: string; equity: number }[][]): { date: string; equity: number }[][] {
    if (!seriesArray.length || !seriesArray[0].length) return seriesArray;
    const len = seriesArray[0].length;
    let firstActive = 0;
    for (let i = 0; i < len; i++) {
      if (seriesArray.some(s => s[i] && s[i].equity !== 0)) {
        firstActive = i;
        break;
      }
    }
    // Keep one zero point before first activity for context
    firstActive = Math.max(0, firstActive - 1);
    if (firstActive === 0) return seriesArray;
    return seriesArray.map(s => s.slice(firstActive));
  }

  getEquityBrokerSvgPaths(): { broker_name: string; points: string; greenPath: string; redPath: string; color: string; lastValue: number; gradientId: string }[] {
    if (!this.data?.equity_by_broker?.length) return [];
    const trimmed = this.trimLeadingZeros(this.data.equity_by_broker.map(b => b.data));
    return this.data.equity_by_broker.map((b, i) => {
      const { greenPath, redPath } = this.buildSvgSplitAreaPaths(trimmed[i], trimmed);
      return {
        broker_name: b.broker_name,
        points: this.buildSvgPolyline(trimmed[i], trimmed),
        greenPath,
        redPath,
        color: this.chartColors[i % this.chartColors.length],
        lastValue: b.data.length ? b.data[b.data.length - 1].equity : 0,
        gradientId: `broker-grad-${i}`,
      };
    });
  }

  getEquityBrokerYAxis(): { label: string; topPct: number }[] {
    if (!this.data?.equity_by_broker?.length) return [];
    const trimmed = this.trimLeadingZeros(this.data.equity_by_broker.map(b => b.data));
    const info = this.getEquityYAxisInfo(trimmed);
    const labels: { label: string; topPct: number }[] = [];
    labels.push({ label: this.formatCompactValue(info.max), topPct: info.maxPct });
    if (Math.abs(info.mid) > 0.01 && Math.abs(info.mid - info.max) > (info.max - info.min) * 0.15) {
      labels.push({ label: this.formatCompactValue(info.mid), topPct: info.midPct });
    }
    // Skip bottom label — X-axis dates occupy that space
    return labels;
  }

  getEquityBrokerGridLines(): { y: number }[] {
    if (!this.data?.equity_by_broker?.length) return [];
    const trimmed = this.trimLeadingZeros(this.data.equity_by_broker.map(b => b.data));
    const info = this.getEquityYAxisInfo(trimmed);
    // Convert pct back to SVG y coordinate for the grid lines
    const pctToY = (pct: number) => (pct / 100) * this.svgH;
    return [{ y: pctToY(info.maxPct) }, { y: pctToY(info.midPct) }, { y: pctToY(info.minPct) }];
  }

  getEquityPipelineSvgPaths(): { pipeline_name: string; points: string; greenPath: string; redPath: string; color: string; lastValue: number; gradientId: string }[] {
    if (!this.data?.equity_by_pipeline?.length) return [];
    const trimmed = this.trimLeadingZeros(this.data.equity_by_pipeline.map(p => p.data));
    return this.data.equity_by_pipeline.map((p, i) => {
      const { greenPath, redPath } = this.buildSvgSplitAreaPaths(trimmed[i], trimmed);
      return {
        pipeline_name: p.pipeline_name,
        points: this.buildSvgPolyline(trimmed[i], trimmed),
        greenPath,
        redPath,
        color: this.chartColors[i % this.chartColors.length],
        lastValue: p.data.length ? p.data[p.data.length - 1].equity : 0,
        gradientId: `pipeline-grad-${i}`,
      };
    });
  }

  getEquityPipelineYAxis(): { label: string; topPct: number }[] {
    if (!this.data?.equity_by_pipeline?.length) return [];
    const trimmed = this.trimLeadingZeros(this.data.equity_by_pipeline.map(p => p.data));
    const info = this.getEquityYAxisInfo(trimmed);
    const labels: { label: string; topPct: number }[] = [];
    labels.push({ label: this.formatCompactValue(info.max), topPct: info.maxPct });
    if (Math.abs(info.mid) > 0.01 && Math.abs(info.mid - info.max) > (info.max - info.min) * 0.15) {
      labels.push({ label: this.formatCompactValue(info.mid), topPct: info.midPct });
    }
    return labels;
  }

  getEquityPipelineGridLines(): { y: number }[] {
    if (!this.data?.equity_by_pipeline?.length) return [];
    const trimmed = this.trimLeadingZeros(this.data.equity_by_pipeline.map(p => p.data));
    const info = this.getEquityYAxisInfo(trimmed);
    const pctToY = (pct: number) => (pct / 100) * this.svgH;
    return [{ y: pctToY(info.maxPct) }, { y: pctToY(info.midPct) }, { y: pctToY(info.minPct) }];
  }

  private formatCompactValue(v: number): string {
    if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`;
    return `$${v.toFixed(0)}`;
  }

  // ── X-axis date labels (shared) ──────────────────────────

  /** Extract ~4 evenly-spaced date labels from a date array, returned as { label, leftPct }. */
  private getXAxisDates(dates: string[], count = 4): { label: string; leftPct: number }[] {
    if (!dates.length) return [];
    const len = dates.length;
    if (len <= count) {
      return dates.map((d, i) => ({
        label: this.formatChartDate(d),
        leftPct: len > 1 ? (i / (len - 1)) * 100 : 50,
      }));
    }
    const labels: { label: string; leftPct: number }[] = [];
    for (let i = 0; i < count; i++) {
      const idx = Math.round((i / (count - 1)) * (len - 1));
      labels.push({
        label: this.formatChartDate(dates[idx]),
        leftPct: (idx / (len - 1)) * 100,
      });
    }
    return labels;
  }

  formatChartDate(dateStr: string): string {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  getEquityBrokerXAxis(): { label: string; leftPct: number }[] {
    if (!this.data?.equity_by_broker?.length) return [];
    const trimmed = this.trimLeadingZeros(this.data.equity_by_broker.map(b => b.data));
    return this.getXAxisDates(trimmed[0].map(d => d.date));
  }

  getEquityPipelineXAxis(): { label: string; leftPct: number }[] {
    if (!this.data?.equity_by_pipeline?.length) return [];
    const trimmed = this.trimLeadingZeros(this.data.equity_by_pipeline.map(p => p.data));
    return this.getXAxisDates(trimmed[0].map(d => d.date));
  }

  getProfitXAxis(): { label: string; leftPct: number }[] {
    if (!this.data?.pnl_history?.length) return [];
    let firstActive = this.data.pnl_history.findIndex(e => e.pnl !== 0);
    if (firstActive < 0) return [];
    firstActive = Math.max(0, firstActive - 1);
    const trimmed = this.data.pnl_history.slice(firstActive);
    return this.getXAxisDates(trimmed.map(e => e.date));
  }

  // ── Profit area chart helpers ─────────────────────────────

  private getProfitCumulative(): number[] {
    if (!this.data?.pnl_history?.length) return [];
    // Find first day with non-zero pnl and keep one zero before it
    let firstActive = this.data.pnl_history.findIndex(e => e.pnl !== 0);
    if (firstActive < 0) return [];
    firstActive = Math.max(0, firstActive - 1);
    const trimmed = this.data.pnl_history.slice(firstActive);
    let cum = 0;
    return trimmed.map(e => { cum += e.pnl; return cum; });
  }

  getProfitAreaPoints(): { x: number; y: number }[] {
    const vals = this.getProfitCumulative();
    if (!vals.length) return [];
    const minV = Math.min(...vals, 0);
    const maxV = Math.max(...vals, 0);
    const range = maxV - minV || 1;
    const usableW = this.svgW - this.svgPadLeft;
    const usableH = this.svgH - this.svgPadTop - this.svgPadBot;
    return vals.map((v, i) => ({
      x: this.svgPadLeft + (vals.length > 1 ? (i / (vals.length - 1)) * usableW : usableW / 2),
      y: this.svgPadTop + usableH - ((v - minV) / range) * usableH,
    }));
  }

  getProfitLinePath(): string {
    const pts = this.getProfitAreaPoints();
    if (pts.length < 2) return '';
    return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  }

  getProfitBaselineY(): number {
    const vals = this.getProfitCumulative();
    if (!vals.length) return 100;
    const minV = Math.min(...vals, 0);
    const maxV = Math.max(...vals, 0);
    const range = maxV - minV || 1;
    const usableH = this.svgH - this.svgPadTop - this.svgPadBot;
    return this.svgPadTop + usableH - ((0 - minV) / range) * usableH;
  }

  getProfitGreenArea(): string {
    const pts = this.getProfitAreaPoints();
    if (pts.length < 2) return '';
    const baseY = this.getProfitBaselineY();
    let path = `M${pts[0].x.toFixed(1)},${baseY.toFixed(1)}`;
    for (const p of pts) {
      path += ` L${p.x.toFixed(1)},${Math.min(p.y, baseY).toFixed(1)}`;
    }
    path += ` L${pts[pts.length - 1].x.toFixed(1)},${baseY.toFixed(1)} Z`;
    return path;
  }

  getProfitRedArea(): string {
    const pts = this.getProfitAreaPoints();
    if (pts.length < 2) return '';
    const baseY = this.getProfitBaselineY();
    let path = `M${pts[0].x.toFixed(1)},${baseY.toFixed(1)}`;
    for (const p of pts) {
      path += ` L${p.x.toFixed(1)},${Math.max(p.y, baseY).toFixed(1)}`;
    }
    path += ` L${pts[pts.length - 1].x.toFixed(1)},${baseY.toFixed(1)} Z`;
    return path;
  }

  getProfitYAxis(): { label: string; topPct: number }[] {
    const vals = this.getProfitCumulative();
    if (!vals.length) return [];
    const minV = Math.min(...vals, 0);
    const maxV = Math.max(...vals, 0);
    const range = maxV - minV || 1;
    const valToPct = (v: number) => (1 - (v - minV) / range) * 100;
    const labels: { label: string; topPct: number }[] = [];
    labels.push({ label: this.formatCompactValue(maxV), topPct: valToPct(maxV) });
    labels.push({ label: '$0', topPct: valToPct(0) });
    // Skip bottom min label — X-axis dates occupy that space
    return labels;
  }

  getProfitGridLines(): { y: number }[] {
    return this.getProfitYAxis().map(l => ({ y: (l.topPct / 100) * this.svgH }));
  }

  getProfitCurrentValue(): number {
    const vals = this.getProfitCumulative();
    return vals.length ? vals[vals.length - 1] : 0;
  }

  /** Split profit area into green (above zero) and red (below zero) paths. */
  getProfitGreenAreaPath(): string {
    const pts = this.getProfitAreaPoints();
    if (pts.length < 2) return '';
    const baseY = this.getProfitBaselineY();
    let path = `M${pts[0].x.toFixed(1)},${Math.min(pts[0].y, baseY).toFixed(1)}`;
    for (const p of pts) {
      path += ` L${p.x.toFixed(1)},${Math.min(p.y, baseY).toFixed(1)}`;
    }
    path += ` L${pts[pts.length - 1].x.toFixed(1)},${baseY.toFixed(1)}`;
    path += ` L${pts[0].x.toFixed(1)},${baseY.toFixed(1)} Z`;
    return path;
  }

  getProfitRedAreaPath(): string {
    const pts = this.getProfitAreaPoints();
    if (pts.length < 2) return '';
    const baseY = this.getProfitBaselineY();
    let path = `M${pts[0].x.toFixed(1)},${Math.max(pts[0].y, baseY).toFixed(1)}`;
    for (const p of pts) {
      path += ` L${p.x.toFixed(1)},${Math.max(p.y, baseY).toFixed(1)}`;
    }
    path += ` L${pts[pts.length - 1].x.toFixed(1)},${baseY.toFixed(1)}`;
    path += ` L${pts[0].x.toFixed(1)},${baseY.toFixed(1)} Z`;
    return path;
  }

  // ── Radar chart helpers ───────────────────────────────────

  // Radar uses a 400x320 viewBox with center at 200,155
  radarCx = 200;
  radarCy = 155;
  private radarR = 85;
  private radarLabels = ['Win Rate', 'Profit Fa.', 'Win/Loss', 'Low DD', 'Consistency'];

  getRadarAxisPoint(axisIndex: number, radius: number): { x: number; y: number } {
    const angle = (Math.PI * 2 * axisIndex) / 5 - Math.PI / 2;
    return {
      x: this.radarCx + Math.cos(angle) * radius,
      y: this.radarCy + Math.sin(angle) * radius,
    };
  }

  getRadarGridPolygon(radius: number): string {
    return Array.from({ length: 5 }, (_, i) => {
      const p = this.getRadarAxisPoint(i, radius);
      return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    }).join(' ');
  }

  getRadarNormValues(): number[] {
    if (!this.data?.trading_score) return [0, 0, 0, 0, 0];
    const s = this.data.trading_score;
    return [
      Math.min(s.win_rate, 1.0),
      Math.min(s.profit_factor / 5, 1.0),
      Math.min(s.avg_win_loss_ratio / 5, 1.0),
      Math.max(1.0 - s.max_drawdown, 0),
      Math.min(s.consistency, 1.0),
    ];
  }

  getRadarPolygon(): string {
    const values = this.getRadarNormValues();
    return values
      .map((v, i) => {
        const p = this.getRadarAxisPoint(i, v * this.radarR);
        return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
      })
      .join(' ');
  }

  getRadarAxisLabel(index: number): string {
    return this.radarLabels[index] || '';
  }

  getRadarLabelPos(index: number): { x: number; y: number; anchor: string } {
    const p = this.getRadarAxisPoint(index, this.radarR + 28);
    let anchor = 'middle';
    if (p.x < this.radarCx - 20) anchor = 'end';
    else if (p.x > this.radarCx + 20) anchor = 'start';
    return { x: p.x, y: p.y, anchor };
  }

  getRadarValueLabel(index: number): string {
    if (!this.data?.trading_score) return '';
    const s = this.data.trading_score;
    const raw = [
      `${(s.win_rate * 100).toFixed(0)}%`,
      s.profit_factor.toFixed(1),
      s.avg_win_loss_ratio.toFixed(1),
      `${((1 - s.max_drawdown) * 100).toFixed(0)}%`,
      `${(s.consistency * 100).toFixed(0)}%`,
    ];
    return raw[index] || '';
  }

  getRadarValuePos(index: number): { x: number; y: number; anchor: string } {
    const p = this.getRadarAxisPoint(index, this.radarR + 28);
    let anchor = 'middle';
    if (p.x < this.radarCx - 20) anchor = 'end';
    else if (p.x > this.radarCx + 20) anchor = 'start';
    return { x: p.x, y: p.y + 16, anchor };
  }

  // ── Calendar helpers ──────────────────────────────────────

  get calendarMonthLabel(): string {
    const d = new Date(this.calendarYear, this.calendarMonth, 1);
    return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }

  prevMonth(): void {
    if (this.calendarMonth === 0) {
      this.calendarMonth = 11;
      this.calendarYear--;
    } else {
      this.calendarMonth--;
    }
    this.selectedCalendarDay = null;
  }

  nextMonth(): void {
    if (this.calendarMonth === 11) {
      this.calendarMonth = 0;
      this.calendarYear++;
    } else {
      this.calendarMonth++;
    }
    this.selectedCalendarDay = null;
  }

  getCalendarDays(): (CalendarDayData | null)[] {
    const firstDay = new Date(this.calendarYear, this.calendarMonth, 1);
    const lastDay = new Date(this.calendarYear, this.calendarMonth + 1, 0);
    // Monday = 0 start
    let startDow = firstDay.getDay() - 1;
    if (startDow < 0) startDow = 6;

    const calMap = new Map<string, CalendarDayData>();
    if (this.data?.calendar_data) {
      for (const d of this.data.calendar_data) {
        calMap.set(d.date, d);
      }
    }

    const cells: (CalendarDayData | null)[] = [];
    // Pad before
    for (let i = 0; i < startDow; i++) cells.push(null);
    // Days of month
    for (let day = 1; day <= lastDay.getDate(); day++) {
      const dateStr = `${this.calendarYear}-${String(this.calendarMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const entry = calMap.get(dateStr);
      cells.push(entry || { date: dateStr, pnl: 0, trades: 0, wins: 0, losses: 0, best_trade: 0, worst_trade: 0 });
    }
    // Pad after to fill 6 rows
    while (cells.length < 42) cells.push(null);
    return cells;
  }

  getCalendarDayClass(day: CalendarDayData | null): string {
    if (!day) return 'cal-empty';
    if (day.trades === 0) return 'cal-no-trades';
    return day.pnl >= 0 ? 'cal-profit' : 'cal-loss';
  }

  getCalendarDayNumber(day: CalendarDayData | null): string {
    if (!day) return '';
    return day.date.slice(-2).replace(/^0/, '');
  }

  selectCalendarDay(day: CalendarDayData | null): void {
    if (day && day.trades > 0) {
      this.selectedCalendarDay = day;
    }
  }

  onCalendarDayClick(event: MouseEvent, day: CalendarDayData | null): void {
    event.stopPropagation();
    if (!day || day.trades === 0) {
      this.selectedCalendarDay = null;
      return;
    }
    if (this.selectedCalendarDay?.date === day.date) {
      this.selectedCalendarDay = null;
      return;
    }
    // Position popover relative to the .pnl-calendar container
    const cell = event.currentTarget as HTMLElement;
    const container = cell.closest('.pnl-calendar') as HTMLElement;
    if (!container) return;
    const containerRect = container.getBoundingClientRect();
    const cellRect = cell.getBoundingClientRect();
    const popoverW = 220;
    let left = cellRect.left - containerRect.left + cellRect.width / 2 - popoverW / 2;
    // Clamp within container
    left = Math.max(0, Math.min(left, containerRect.width - popoverW));
    const top = cellRect.top - containerRect.top + cellRect.height + 6;
    this.calendarPopoverTop = top;
    this.calendarPopoverLeft = left;
    this.selectedCalendarDay = day;
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.selectedCalendarDay) return;
    const target = event.target as HTMLElement;
    if (!target.closest('.calendar-day') && !target.closest('.calendar-popover')) {
      this.selectedCalendarDay = null;
    }
  }
}
