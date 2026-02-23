/**
 * Monitoring Component
 * 
 * Main monitoring dashboard showing list of executions
 */

import { Component, OnInit, OnDestroy, AfterViewInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatPaginator, MatPaginatorModule } from '@angular/material/paginator';
import { MatTableDataSource } from '@angular/material/table';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';

import { MonitoringService, ExecutionListResponse } from '../../core/services/monitoring.service';
import { ExecutionSummary, ExecutionStats } from '../../core/models/execution.model';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../shared/components/footer/footer.component';
import { ExecutionReportModalComponent } from './execution-report-modal/execution-report-modal.component';
import { ReconciliationDialogComponent } from './reconciliation-dialog/reconciliation-dialog.component';

@Component({
  selector: 'app-monitoring',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatSnackBarModule,
    MatDialogModule,
    MatPaginatorModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatDatepickerModule,
    MatNativeDateModule,
    NavbarComponent,
    FooterComponent
  ],
  templateUrl: './monitoring.component.html',
  styleUrls: ['./monitoring.component.scss']
})
export class MonitoringComponent implements OnInit, OnDestroy, AfterViewInit {
  // Split executions into active monitoring and historical
  activeExecutions: ExecutionSummary[] = [];
  historicalDataSource = new MatTableDataSource<ExecutionSummary>([]);
  
  // All executions (unfiltered)
  allExecutions: ExecutionSummary[] = [];
  
  // Execution bar visualization data (music bar / equalizer style)
  executionBars: Array<{
    execution: ExecutionSummary;
    colorClass: string;
    height: number;
    tooltip: string;
    category: string;
  }> = [];

  // Timeline filter toggles — which categories are visible
  timelineFilters: Record<string, boolean> = {
    profit: true,
    loss: true,
    hold: true,
    'no-trade': true,
    cancelled: true,
    pending: true,
    rejected: true,
    failed: true,
  };

  // Timeline legend items (interactive) — count is computed after buildExecutionBars
  timelineLegend: Array<{ key: string; label: string; colorClass: string; count: number }> = [
    { key: 'profit', label: 'Profit', colorClass: 'bar-profit', count: 0 },
    { key: 'loss', label: 'Loss', colorClass: 'bar-loss', count: 0 },
    { key: 'hold', label: 'Hold', colorClass: 'bar-hold', count: 0 },
    { key: 'no-trade', label: 'No Trade', colorClass: 'bar-no-trade', count: 0 },
    { key: 'cancelled', label: 'Cancelled', colorClass: 'bar-cancelled', count: 0 },
    { key: 'pending', label: 'Limit Pending', colorClass: 'bar-pending', count: 0 },
    { key: 'rejected', label: 'Rejected', colorClass: 'bar-rejected', count: 0 },
    { key: 'failed', label: 'Failed', colorClass: 'bar-failed', count: 0 },
  ];
  
  stats: ExecutionStats | null = null;
  loading = true;

  // Client-side pagination — fetch a large batch, filter + paginate locally
  private fetchSize = 500;
  totalServerCount = 0;
  hasMore = false;
  loadingMore = false;

  // Filter values
  filters = {
    status: 'all',
    mode: 'all',
    tradeOutcome: 'all',
    symbol: '',
    pipeline: '',
    startDate: null as Date | null,
    endDate: null as Date | null
  };
  
  // Filter options
  statusOptions = [
    { value: 'all', label: 'All Statuses' },
    { value: 'RUNNING', label: 'Running' },
    { value: 'MONITORING', label: 'Monitoring' },
    { value: 'AWAITING_APPROVAL', label: 'Awaiting Approval' },
    { value: 'COMPLETED', label: 'Completed' },
    { value: 'FAILED', label: 'Failed' },
    { value: 'PENDING', label: 'Pending' },
    { value: 'COMMUNICATION_ERROR', label: 'Comm. Error' },
    { value: 'NEEDS_RECONCILIATION', label: 'Needs Reconciliation' }
  ];
  
  modeOptions = [
    { value: 'all', label: 'All Modes' },
    { value: 'paper', label: 'Paper' },
    { value: 'live', label: 'Live' },
    { value: 'simulation', label: 'Simulation' }
  ];
  
  tradeOutcomeOptions = [
    { value: 'all', label: 'All Outcomes' },
    { value: 'executed', label: 'Executed (P&L)' },
    { value: 'pending', label: 'Pending (Limit Order)' },
    { value: 'cancelled', label: 'Cancelled' },
    { value: 'failed', label: 'Failed' },
    { value: 'rejected', label: 'Rejected' },
    { value: 'no_action', label: 'Hold / No Action' },
    { value: 'no_trade', label: 'No Trade' }
  ];
  
  // Separate columns for active monitoring (more compact)
  activeColumns: string[] = ['symbol', 'pipeline', 'mode', 'started', 'result', 'pnl', 'actions'];
  // Full columns for historical executions
  displayedColumns: string[] = ['execution_id', 'symbol', 'pipeline', 'mode', 'source', 'started', 'duration', 'cost', 'result', 'outcome', 'pnl', 'status', 'actions'];
  
  @ViewChild(MatPaginator) paginator!: MatPaginator;

  private refreshInterval: any;

  constructor(
    private monitoringService: MonitoringService,
    private router: Router,
    private snackBar: MatSnackBar,
    private dialog: MatDialog
  ) {}

  ngOnInit(): void {
    this.loadData();
    // Refresh every 5 seconds
    this.refreshInterval = setInterval(() => this.loadData(), 5000);
  }

  ngOnDestroy(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }

  ngAfterViewInit(): void {
    this.historicalDataSource.paginator = this.paginator;
  }

  loadData(): void {
    this.monitoringService.loadExecutions(this.fetchSize, 0).subscribe({
      next: (resp: ExecutionListResponse) => {
        this.allExecutions = resp.executions;
        this.totalServerCount = resp.historical_total + resp.active_count;
        this.hasMore = resp.executions.length < this.totalServerCount;

        this.buildExecutionBars();
        this.applyFilters();

        this.loading = false;
      },
      error: (error) => {
        console.error('Failed to load executions:', error);
        this.loading = false;
        this.showNotification('Failed to load executions', 'error');
      }
    });

    this.monitoringService.getExecutionStats().subscribe({
      next: (stats) => {
        this.stats = stats;
      },
      error: (error) => {
        console.error('Failed to load stats:', error);
      }
    });
  }

  loadMore(): void {
    this.loadingMore = true;
    const offset = this.allExecutions.length;

    this.monitoringService.loadExecutions(this.fetchSize, offset).subscribe({
      next: (resp: ExecutionListResponse) => {
        // Append new executions (skip duplicates by id)
        const existingIds = new Set(this.allExecutions.map(e => e.id));
        const newExecs = resp.executions.filter(e => !existingIds.has(e.id));
        this.allExecutions = [...this.allExecutions, ...newExecs];
        this.totalServerCount = resp.historical_total + resp.active_count;
        this.hasMore = this.allExecutions.length < this.totalServerCount;

        this.buildExecutionBars();
        this.applyFilters();
        this.loadingMore = false;
      },
      error: (error) => {
        console.error('Failed to load more executions:', error);
        this.loadingMore = false;
        this.showNotification('Failed to load more executions', 'error');
      }
    });
  }

  applyFilters(): void {
    let filtered = [...this.allExecutions];

    // Apply client-side filters (symbol search, mode, etc.)
    if (this.filters.status !== 'all') {
      filtered = filtered.filter(e => e.status.toUpperCase() === this.filters.status);
    }
    if (this.filters.mode !== 'all') {
      filtered = filtered.filter(e => e.mode.toLowerCase() === this.filters.mode);
    }
    if (this.filters.symbol) {
      const symbolLower = this.filters.symbol.toLowerCase();
      filtered = filtered.filter(e => e.symbol?.toLowerCase().includes(symbolLower) ?? false);
    }
    if (this.filters.pipeline) {
      const pipelineLower = this.filters.pipeline.toLowerCase();
      filtered = filtered.filter(e => e.pipeline_name?.toLowerCase().includes(pipelineLower) ?? false);
    }
    if (this.filters.startDate) {
      filtered = filtered.filter(e => new Date(e.started_at) >= this.filters.startDate!);
    }
    if (this.filters.endDate) {
      const endOfDay = new Date(this.filters.endDate);
      endOfDay.setHours(23, 59, 59, 999);
      filtered = filtered.filter(e => new Date(e.started_at) <= endOfDay);
    }

    // Split into active and historical
    const activeStatuses = new Set(['MONITORING', 'RUNNING', 'PENDING', 'COMMUNICATION_ERROR', 'NEEDS_RECONCILIATION', 'AWAITING_APPROVAL']);
    this.activeExecutions = filtered.filter(
      e => activeStatuses.has(e.status.toUpperCase())
    );

    let historical = filtered.filter(
      e => !activeStatuses.has(e.status.toUpperCase())
    );

    // Apply trade outcome filter to historical table only
    if (this.filters.tradeOutcome !== 'all') {
      historical = historical.filter(e => e.trade_outcome === this.filters.tradeOutcome);
      if (this.filters.tradeOutcome === 'executed') {
        historical = historical.filter(e => {
          const pnl = this.getPnL(e);
          return pnl.value !== null && pnl.value !== undefined && pnl.value !== 0;
        });
      }
    }

    this.historicalDataSource.data = historical;

    // Reset paginator to first page on filter change
    if (this.paginator) {
      this.paginator.firstPage();
    }
  }

  clearFilters(): void {
    this.filters = {
      status: 'all',
      mode: 'all',
      tradeOutcome: 'all',
      symbol: '',
      pipeline: '',
      startDate: null,
      endDate: null
    };
    this.applyFilters();
  }

  onFilterChange(): void {
    this.applyFilters();
  }

  viewExecution(execution: ExecutionSummary): void {
    this.router.navigate(['/monitoring', execution.id]);
  }

  viewReport(execution: ExecutionSummary, event: Event): void {
    event.stopPropagation(); // Prevent row click
    
    // Fetch full execution data and open modal
    this.monitoringService.getExecutionDetail(execution.id).subscribe({
      next: (fullExecution) => {
        this.dialog.open(ExecutionReportModalComponent, {
          width: '800px',
          maxHeight: '90vh',
          data: { execution: fullExecution }
        });
      },
      error: (error) => {
        console.error('Failed to load execution details:', error);
        this.showNotification('Failed to load report', 'error');
      }
    });
  }

  stopExecution(execution: ExecutionSummary, event: Event): void {
    event.stopPropagation();
    
    if (confirm(`Stop execution for ${execution.pipeline_name}?`)) {
      this.monitoringService.stopExecution(execution.id).subscribe({
        next: () => {
          this.showNotification('Execution stopped', 'success');
          this.loadData();
        },
        error: (error) => {
          console.error('Failed to stop execution:', error);
          this.showNotification('Failed to stop execution', 'error');
        }
      });
    }
  }

  /**
   * Build execution bar visualization data from all executions.
   * Each bar represents one execution, color-coded by outcome,
   * with height proportional to P&L magnitude for executed trades.
   */
  buildExecutionBars(): void {
    const sorted = [...this.allExecutions].sort(
      (a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
    );

    // Find max absolute P&L for height scaling
    let maxPnL = 0;
    sorted.forEach(ex => {
      const pnl = this.getPnL(ex);
      if (pnl.value !== null && pnl.value !== undefined) {
        maxPnL = Math.max(maxPnL, Math.abs(pnl.value));
      }
    });
    if (maxPnL === 0) maxPnL = 1;

    const MIN_H = 12;
    const MAX_H = 72;

    this.executionBars = sorted.map(ex => {
      const pnl = this.getPnL(ex);
      const outcome = ex.trade_outcome;
      const action = ex.strategy_action;
      let colorClass = 'bar-no-action';
      let height = MIN_H;
      let category = 'hold'; // default category

      if (outcome === 'executed' && pnl.value !== null && pnl.value !== undefined && pnl.value !== 0) {
        colorClass = pnl.value >= 0 ? 'bar-profit' : 'bar-loss';
        height = MIN_H + (Math.abs(pnl.value) / maxPnL) * (MAX_H - MIN_H);
        category = pnl.value >= 0 ? 'profit' : 'loss';
      } else if (outcome === 'pending') {
        colorClass = 'bar-pending';
        height = MIN_H + 18;
        category = 'pending';
      } else if (outcome === 'cancelled') {
        colorClass = 'bar-cancelled';
        height = MIN_H + 8;
        category = 'cancelled';
      } else if (outcome === 'rejected') {
        colorClass = 'bar-rejected';
        height = MIN_H + 8;
        category = 'rejected';
      } else if (outcome === 'failed') {
        colorClass = 'bar-failed';
        height = MIN_H + 8;
        category = 'failed';
      } else if (outcome === 'no_action' || action === 'HOLD') {
        colorClass = 'bar-hold';
        height = MIN_H + 8;
        category = 'hold';
      } else if (outcome === 'no_trade') {
        colorClass = 'bar-no-trade';
        height = MIN_H + 6;
        category = 'no-trade';
      } else {
        colorClass = 'bar-no-action';
        height = MIN_H + 4;
        category = 'hold';
      }

      const symbol = ex.symbol || 'N/A';
      const outcomeLabel = this.getTradeOutcome(ex);
      const pnlStr = (pnl.value !== null && pnl.value !== undefined && pnl.value !== 0)
        ? ` · P&L: ${pnl.value >= 0 ? '+' : ''}$${pnl.value.toFixed(2)}`
        : '';
      const actionStr = action ? ` · ${action}` : '';
      const tooltip = `${symbol}${actionStr} · ${outcomeLabel}${pnlStr}`;

      return { execution: ex, colorClass, height, tooltip, category };
    });

    // Update legend counts
    const counts: Record<string, number> = {};
    this.executionBars.forEach(bar => {
      counts[bar.category] = (counts[bar.category] || 0) + 1;
    });
    this.timelineLegend.forEach(item => {
      item.count = counts[item.key] || 0;
    });
  }

  /** Get only the bars that pass the current timeline filters */
  get filteredBars() {
    return this.executionBars.filter(bar => this.timelineFilters[bar.category]);
  }

  /** Toggle a timeline category on/off */
  toggleTimelineFilter(key: string): void {
    this.timelineFilters[key] = !this.timelineFilters[key];
  }

  /** Quick preset: show only real trades (profit + loss + pending) */
  showOnlyTrades(): void {
    Object.keys(this.timelineFilters).forEach(k => {
      this.timelineFilters[k] = ['profit', 'loss', 'pending'].includes(k);
    });
  }

  /** Quick preset: show all categories */
  showAllCategories(): void {
    Object.keys(this.timelineFilters).forEach(k => {
      this.timelineFilters[k] = true;
    });
  }

  /** Check if we're currently showing all categories */
  get allCategoriesVisible(): boolean {
    return Object.values(this.timelineFilters).every(v => v);
  }

  onBarClick(execution: ExecutionSummary): void {
    this.viewExecution(execution);
  }

  getStatusColor(status: string): string {
    const colors: any = {
      'pending': 'default',
      'running': 'primary',
      'monitoring': 'accent',
      'completed': 'accent',
      'failed': 'warn',
      'cancelled': 'default',
      'paused': 'default',
      'communication_error': 'warn',
      'needs_reconciliation': 'warn',
      'awaiting_approval': 'accent'
    };
    return colors[status] || 'default';
  }

  getStatusIcon(status: string): string {
    const icons: any = {
      'pending': 'schedule',
      'running': 'play_circle',
      'monitoring': 'visibility',
      'completed': 'check_circle',
      'failed': 'error',
      'cancelled': 'cancel',
      'paused': 'pause_circle',
      'communication_error': 'wifi_off',
      'needs_reconciliation': 'warning',
      'awaiting_approval': 'verified_user'
    };
    return icons[status?.toLowerCase()] || 'help';
  }

  getModeColor(mode: string): string {
    const colors: any = {
      'live': 'warn',
      'paper': 'primary',
      'simulation': 'accent',
      'validation': 'default'
    };
    return colors[mode] || 'default';
  }

  formatDuration(seconds: number | undefined): string {
    if (!seconds) return '-';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  }

  formatCost(cost: number): string {
    return `$${cost.toFixed(4)}`;
  }

  formatDate(dateString: string): string {
    if (!dateString) return '-';
    
    // Ensure the date is treated as UTC if no timezone info is present
    let isoString = dateString;
    if (!dateString.endsWith('Z') && !dateString.match(/[+-]\d{2}:\d{2}$/)) {
      // If no timezone info, append 'Z' to treat as UTC
      isoString = dateString + 'Z';
    }
    
    // Convert to local timezone
    return new Date(isoString).toLocaleString();
  }

  getSource(execution: ExecutionSummary): string {
    if (execution.trigger_mode === 'signal' && execution.scanner_name) {
      return execution.scanner_name;
    } else if (execution.trigger_mode === 'periodic') {
      return 'Periodic';
    }
    return '—';
  }

  showNotification(message: string, type: 'success' | 'error' | 'info'): void {
    this.snackBar.open(message, 'Close', {
      duration: 3000,
      horizontalPosition: 'right',
      verticalPosition: 'top',
      panelClass: [`snackbar-${type}`]
    });
  }

  refresh(): void {
    this.loading = true;
    this.loadData();
  }

  getStrategyResult(execution: any): string {
    // Use the summary fields from the API
    if (execution.strategy_action) {
      const action = execution.strategy_action;
      const confidence = execution.strategy_confidence 
        ? `(${(execution.strategy_confidence * 100).toFixed(0)}%)` 
        : '';
      return `${action} ${confidence}`.trim();
    }
    
    // Fallback to result object (for detail view)
    if (execution.result && execution.result.strategy) {
      const strategy = execution.result.strategy;
      const action = strategy.action || 'HOLD';
      const confidence = strategy.confidence ? `(${(strategy.confidence * 100).toFixed(0)}%)` : '';
      return `${action} ${confidence}`.trim();
    }
    
    return '-';
  }

  getResultClass(execution: any): string {
    // Check summary field first
    const action = execution.strategy_action || execution.result?.strategy?.action;
    if (!action) {
      return '';
    }
    return `result-${action.toLowerCase()}`;
  }

  getResultIcon(execution: any): string {
    // Check summary field first
    const action = execution.strategy_action || execution.result?.strategy?.action;
    if (!action) {
      return 'remove';
    }
    const icons: any = {
      'BUY': 'trending_up',
      'SELL': 'trending_down',
      'HOLD': 'remove'
    };
    return icons[action] || 'remove';
  }

  getTradeOutcome(execution: any): string {
    const outcome = execution.trade_outcome;
    if (!outcome) return '-';
    
    const labels: any = {
      'executed': 'Executed',
      'pending': 'Pending',
      'cancelled': 'Cancelled',
      'failed': 'Failed',
      'rejected': 'Rejected',
      'no_action': 'Hold',
      'no_trade': 'No Trade',
      'unknown': 'Unknown'
    };
    return labels[outcome] || outcome;
  }

  getOutcomeClass(execution: any): string {
    const outcome = execution.trade_outcome;
    if (!outcome) return '';
    return `outcome-${outcome.toLowerCase().replace(/_/g, '-')}`;
  }

  getOutcomeIcon(execution: any): string {
    const outcome = execution.trade_outcome;
    const icons: any = {
      'executed': 'check_circle',
      'pending': 'hourglass_empty',
      'cancelled': 'cancel',
      'failed': 'error',
      'rejected': 'block',
      'no_action': 'pause_circle',
      'no_trade': 'remove_circle_outline',
      'unknown': 'help_outline'
    };
    return icons[outcome] || 'help_outline';
  }

  getPnL(execution: any): { value: number | null, percent: number | null } {
    // Check if we have final P&L (completed trades) - NEW FORMAT
    if (execution.result?.final_pnl !== null && execution.result?.final_pnl !== undefined) {
      return {
        value: execution.result.final_pnl,
        percent: execution.result.final_pnl_percent
      };
    }
    
    // Check if we have P&L in trade_outcome (OLD FORMAT - fallback)
    if (execution.result?.trade_outcome?.pnl !== null && execution.result?.trade_outcome?.pnl !== undefined) {
      return {
        value: execution.result.trade_outcome.pnl,
        percent: execution.result.trade_outcome.pnl_percent
      };
    }

    // Check if we have monitoring data (live trades)
    if (execution.reports) {
      // Find trade manager report
      for (const agentId in execution.reports) {
        const report = execution.reports[agentId];
        if (report.agent_type === 'trade_manager_agent' && report.data) {
          if (report.data.unrealized_pl !== null && report.data.unrealized_pl !== undefined) {
            return {
              value: report.data.unrealized_pl,
              percent: report.data.pnl_percent
            };
          }
        }
      }
    }

    return { value: null, percent: null };
  }

  formatPnL(execution: any): string {
    // Check if it's a pending limit order
    const orderStatus = this.getOrderStatus(execution);
    if (orderStatus) {
      return orderStatus;
    }

    const pnl = this.getPnL(execution);
    
    if (pnl.value === null || pnl.value === undefined) {
      return '-';
    }

    const sign = pnl.value >= 0 ? '+' : '';
    const valueStr = `${sign}$${pnl.value.toFixed(2)}`;
    const percentStr = pnl.percent !== null && pnl.percent !== undefined 
      ? ` (${sign}${pnl.percent.toFixed(2)}%)` 
      : '';

    return `${valueStr}${percentStr}`;
  }

  getPnLClass(execution: any): string {
    // Check if it's a pending limit order
    const orderStatus = this.getOrderStatus(execution);
    if (orderStatus) {
      return 'order-pending';
    }

    const pnl = this.getPnL(execution);
    if (pnl.value === null || pnl.value === undefined) {
      return '';
    }
    return pnl.value >= 0 ? 'pnl-positive' : 'pnl-negative';
  }

  getOrderStatus(execution: any): string | null {
    // Check if we have a trade manager report with order status
    if (execution.reports) {
      for (const agentId in execution.reports) {
        const report = execution.reports[agentId];
        if (report.agent_type === 'trade_manager_agent' && report.data) {
          // Check if order_status is "pending" and order_type is "limit"
          if (report.data.order_status === 'pending' && report.data.order_type === 'limit') {
            const entryPrice = report.data.entry_price;
            return entryPrice ? `Limit @ $${entryPrice.toFixed(5)}` : 'Limit Order Pending';
          }
        }
      }
    }
    return null;
  }

  openReconciliationDialog(execution: ExecutionSummary, event?: Event): void {
    if (event) {
      event.stopPropagation();
    }
    
    const dialogRef = this.dialog.open(ReconciliationDialogComponent, {
      width: '640px',
      maxWidth: '95vw',
      panelClass: 'reconciliation-dialog-panel',
      data: { execution }
    });
    
    dialogRef.afterClosed().subscribe(result => {
      if (result && result.success) {
        this.showNotification(
          result.action === 'close' 
            ? 'Trade reconciled successfully' 
            : 'Monitoring resumed successfully',
          'success'
        );
        this.loadData();
      }
    });
  }

  isNeedsReconciliation(execution: ExecutionSummary): boolean {
    return execution.status.toUpperCase() === 'NEEDS_RECONCILIATION';
  }

  isAwaitingApproval(execution: ExecutionSummary): boolean {
    return execution.status.toUpperCase() === 'AWAITING_APPROVAL';
  }

  approveExecution(execution: ExecutionSummary, event?: Event): void {
    if (event) event.stopPropagation();
    if (confirm(`Approve trade for ${execution.symbol || execution.pipeline_name}?`)) {
      this.monitoringService.approveExecution(execution.id).subscribe({
        next: () => {
          this.showNotification('Trade approved — executing now', 'success');
          this.loadData();
        },
        error: (error) => {
          console.error('Failed to approve execution:', error);
          this.showNotification(error.error?.detail || 'Failed to approve trade', 'error');
        }
      });
    }
  }

  rejectExecution(execution: ExecutionSummary, event?: Event): void {
    if (event) event.stopPropagation();
    if (confirm(`Reject trade for ${execution.symbol || execution.pipeline_name}?`)) {
      this.monitoringService.rejectExecution(execution.id).subscribe({
        next: () => {
          this.showNotification('Trade rejected', 'info');
          this.loadData();
        },
        error: (error) => {
          console.error('Failed to reject execution:', error);
          this.showNotification(error.error?.detail || 'Failed to reject trade', 'error');
        }
      });
    }
  }

  getApprovalTimeRemaining(execution: any): string {
    const expiresAt = execution.approval_expires_at || execution.result?.approval_expires_at;
    if (!expiresAt) return '';
    let isoString = expiresAt;
    if (!expiresAt.endsWith('Z') && !expiresAt.match(/[+-]\d{2}:\d{2}$/)) {
      isoString = expiresAt + 'Z';
    }
    const diff = new Date(isoString).getTime() - Date.now();
    if (diff <= 0) return 'Expired';
    const minutes = Math.floor(diff / 60000);
    const seconds = Math.floor((diff % 60000) / 1000);
    return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
  }
}

