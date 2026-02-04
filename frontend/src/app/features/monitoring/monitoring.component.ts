/**
 * Monitoring Component
 * 
 * Main monitoring dashboard showing list of executions
 */

import { Component, OnInit, OnDestroy, AfterViewInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
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

import { MonitoringService } from '../../core/services/monitoring.service';
import { ExecutionSummary, ExecutionStats } from '../../core/models/execution.model';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { ExecutionReportModalComponent } from './execution-report-modal/execution-report-modal.component';

@Component({
  selector: 'app-monitoring',
  standalone: true,
  imports: [
    CommonModule,
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
    NavbarComponent
  ],
  templateUrl: './monitoring.component.html',
  styleUrls: ['./monitoring.component.scss']
})
export class MonitoringComponent implements OnInit, OnDestroy, AfterViewInit {
  // Split executions into active monitoring and historical
  activeExecutions: ExecutionSummary[] = [];
  historicalDataSource = new MatTableDataSource<ExecutionSummary>([]);
  
  stats: ExecutionStats | null = null;
  loading = true;
  
  // Separate columns for active monitoring (more compact)
  activeColumns: string[] = ['symbol', 'pipeline', 'mode', 'started', 'result', 'pnl', 'actions'];
  // Full columns for historical executions
  displayedColumns: string[] = ['symbol', 'pipeline', 'mode', 'source', 'started', 'duration', 'cost', 'result', 'outcome', 'pnl', 'status', 'actions'];
  
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
    this.monitoringService.loadExecutions().subscribe({
      next: (executions) => {
        // Split executions: MONITORING/RUNNING vs others (status comes as uppercase from backend)
        this.activeExecutions = executions.filter(
          e => e.status.toUpperCase() === 'MONITORING' || e.status.toUpperCase() === 'RUNNING'
        );
        
        const historical = executions.filter(
          e => e.status.toUpperCase() !== 'MONITORING' && e.status.toUpperCase() !== 'RUNNING'
        );
        
        this.historicalDataSource.data = historical;
        
        // Ensure paginator is connected after data update
        if (this.paginator) {
          this.historicalDataSource.paginator = this.paginator;
        }
        
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

  getStatusColor(status: string): string {
    const colors: any = {
      'pending': 'default',
      'running': 'primary',
      'monitoring': 'accent',
      'completed': 'accent',
      'failed': 'warn',
      'cancelled': 'default',
      'paused': 'default',
      'communication_error': 'warn'
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
      'communication_error': 'wifi_off'
    };
    return icons[status] || 'help';
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
      'skipped': 'Skipped',
      'rejected': 'Rejected',
      'pending': 'Pending',
      'no_trade': 'No Trade',
      'unknown': 'Unknown'
    };
    return labels[outcome] || outcome;
  }

  getOutcomeClass(execution: any): string {
    const outcome = execution.trade_outcome;
    if (!outcome) return '';
    return `outcome-${outcome.toLowerCase().replace('_', '-')}`;
  }

  getOutcomeIcon(execution: any): string {
    const outcome = execution.trade_outcome;
    const icons: any = {
      'executed': 'check_circle',
      'skipped': 'block',
      'rejected': 'cancel',
      'pending': 'schedule',
      'no_trade': 'remove_circle_outline',
      'unknown': 'help_outline'
    };
    return icons[outcome] || 'help_outline';
  }

  getPnL(execution: any): { value: number | null, percent: number | null } {
    // Check if we have final P&L (completed trades)
    if (execution.result?.final_pnl !== null && execution.result?.final_pnl !== undefined) {
      return {
        value: execution.result.final_pnl,
        percent: execution.result.final_pnl_percent
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
}

