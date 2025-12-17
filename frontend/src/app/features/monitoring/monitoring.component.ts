/**
 * Monitoring Component
 * 
 * Main monitoring dashboard showing list of executions
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
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
    NavbarComponent
  ],
  templateUrl: './monitoring.component.html',
  styleUrls: ['./monitoring.component.scss']
})
export class MonitoringComponent implements OnInit, OnDestroy {
  executions: ExecutionSummary[] = [];
  stats: ExecutionStats | null = null;
  loading = true;
  displayedColumns: string[] = ['pipeline', 'mode', 'source', 'started', 'duration', 'cost', 'result', 'outcome', 'status', 'actions'];

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

  loadData(): void {
    this.monitoringService.loadExecutions().subscribe({
      next: (executions) => {
        this.executions = executions;
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
      'completed': 'accent',
      'failed': 'warn',
      'cancelled': 'default',
      'paused': 'default'
    };
    return colors[status] || 'default';
  }

  getStatusIcon(status: string): string {
    const icons: any = {
      'pending': 'schedule',
      'running': 'play_circle',
      'completed': 'check_circle',
      'failed': 'error',
      'cancelled': 'cancel',
      'paused': 'pause_circle'
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
}

