/**
 * Execution Detail Component
 * 
 * Displays detailed information about a pipeline execution including agent reports and charts
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTabsModule } from '@angular/material/tabs';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { interval, Subscription, switchMap } from 'rxjs';

import { MonitoringService } from '../../../core/services/monitoring.service';
import { NavbarComponent } from '../../../core/components/navbar/navbar.component';
import { TradingChartComponent } from '../../../shared/components/trading-chart/trading-chart.component';
import { ExecutionReportModalComponent } from '../execution-report-modal/execution-report-modal.component';
import { MarkdownToHtmlPipe } from '../../../shared/pipes/markdown-to-html.pipe';
import { ConfirmDialogComponent } from '../../../shared/confirm-dialog/confirm-dialog.component';

@Component({
  selector: 'app-execution-detail',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatTabsModule,
    MatExpansionModule,
    MatDialogModule,
    MatTooltipModule,
    MatSnackBarModule,
    NavbarComponent,
    TradingChartComponent,
    MarkdownToHtmlPipe,
  ],
  templateUrl: './execution-detail.component.html',
  styleUrls: ['./execution-detail.component.scss']
})
export class ExecutionDetailComponent implements OnInit, OnDestroy {
  execution: any = null;
  loading = true;
  error: string | null = null;
  private refreshInterval: any;
  private countdownInterval: any;
  timeUntilNextCheck: string = '-';

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private monitoringService: MonitoringService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.loadExecution(id);
      
      // Auto-refresh every 10 seconds if monitoring
      this.refreshInterval = setInterval(() => {
        if (this.isMonitoring()) {
          this.loadExecution(id);
        } else {
          // Stop auto-refresh if no longer monitoring
          this.stopAutoRefresh();
        }
      }, 10000); // 10 seconds
      
      // Update countdown every second
      this.countdownInterval = setInterval(() => {
        if (this.isMonitoring()) {
          this.updateCountdown();
        }
      }, 1000); // 1 second
    } else {
      this.error = 'No execution ID provided';
      this.loading = false;
    }
  }

  ngOnDestroy(): void {
    this.stopAutoRefresh();
    this.stopCountdown();
  }

  private stopAutoRefresh(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }

  private stopCountdown(): void {
    if (this.countdownInterval) {
      clearInterval(this.countdownInterval);
      this.countdownInterval = null;
    }
  }

  private updateCountdown(): void {
    this.timeUntilNextCheck = this.getTimeUntilNextCheck();
  }

  loadExecution(id: string): void {
    this.monitoringService.getExecutionDetail(id).subscribe({
      next: (data) => {
        this.execution = data;
        this.loading = false;
        
        // Initialize countdown immediately after loading
        if (this.isMonitoring()) {
          this.updateCountdown();
        }
      },
      error: (error) => {
        console.error('Failed to load execution:', error);
        this.error = 'Failed to load execution details';
        this.loading = false;
      }
    });
  }

  goBack(): void {
    this.router.navigate(['/monitoring']);
  }

  openFinalReport(): void {
    this.dialog.open(ExecutionReportModalComponent, {
      width: '800px',
      maxHeight: '90vh',
      data: { execution: this.execution }
    });
  }

  getStatusColor(status: string): string {
    const colors: any = {
      'COMPLETED': 'success',
      'FAILED': 'error',
      'RUNNING': 'primary',
      'PENDING': 'warning'
    };
    return colors[status] || 'default';
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

  getAgentIcon(agentType: string): string {
    const icons: any = {
      'bias_agent': 'analytics',
      'strategy_agent': 'psychology',
      'risk_manager_agent': 'security',
      'trade_manager_agent': 'swap_horiz',
    };
    return icons[agentType] || 'smart_toy';
  }

  getAgentStateColor(status: string): string {
    const colors: any = {
      'completed': '#4caf50',
      'failed': '#f44336',
      'running': '#2196f3',
      'pending': '#ff9800',
    };
    return colors[status] || '#9e9e9e';
  }

  hasChart(agent: any): boolean {
    return agent.agent_type === 'strategy_agent' && 
           this.execution?.result?.execution_artifacts?.strategy_chart;
  }

  getChartData(): any {
    return this.execution?.result?.execution_artifacts?.strategy_chart;
  }

  isArray(value: any): boolean {
    return Array.isArray(value);
  }

  isObject(value: any): boolean {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  isNumber(value: any): boolean {
    return typeof value === 'number';
  }

  isString(value: any): boolean {
    return typeof value === 'string';
  }

  // Monitoring-specific methods
  isMonitoring(): boolean {
    return this.execution?.status === 'MONITORING';
  }

  isCompleted(): boolean {
    return this.execution?.status === 'COMPLETED';
  }

  hasFinalPnL(): boolean {
    return this.isCompleted() && (
      this.execution?.result?.final_pnl !== null && 
      this.execution?.result?.final_pnl !== undefined
    );
  }

  getFinalPnL(): any {
    if (!this.hasFinalPnL()) return null;
    
    const finalPnl = this.execution.result.final_pnl;
    const finalPnlPercent = this.execution.result.final_pnl_percent;
    const strategy = this.execution?.result?.strategy;
    const tradeExecution = this.execution?.result?.trade_execution;
    
    return {
      symbol: this.execution.symbol,
      action: strategy?.action,
      qty: tradeExecution?.filled_quantity,
      entryPrice: strategy?.entry_price,
      stopLoss: strategy?.stop_loss,
      takeProfit: strategy?.take_profit,
      finalPnl: finalPnl,
      finalPnlPercent: finalPnlPercent,
      closedAt: this.execution.result.closed_at || this.execution.completed_at
    };
  }

  formatDate(date: string | null | undefined): string {
    if (!date) return 'N/A';
    
    try {
      const dateObj = new Date(date);
      return dateObj.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    } catch (error) {
      return 'Invalid date';
    }
  }

  getPositionData(): any {
    if (!this.isMonitoring()) return null;
    
    // Get the latest trade manager report
    const tradeManagerAgent = this.execution?.agent_states?.find(
      (agent: any) => agent.agent_type === 'trade_manager_agent'
    );
    
    if (!tradeManagerAgent) return null;
    
    const report = this.execution?.reports?.[tradeManagerAgent.agent_id];
    
    // Get position data from the latest monitoring report
    const positionData = report?.data;
    
    // Get strategy and trade execution info
    const strategy = this.execution?.result?.strategy;
    const tradeExecution = this.execution?.result?.trade_execution;
    
    return {
      symbol: this.execution.symbol,
      action: strategy?.action,
      qty: positionData?.qty || tradeExecution?.quantity,
      entryPrice: strategy?.entry_price,
      stopLoss: strategy?.stop_loss,
      takeProfit: strategy?.take_profit,
      unrealizedPl: positionData?.unrealized_pl,
      pnlPercent: positionData?.pnl_percent,
      nextCheckAt: this.execution.next_check_at,
      monitorInterval: this.execution.monitor_interval_minutes || 1
    };
  }

  getTimeUntilNextCheck(): string {
    if (!this.execution?.next_check_at) {
      return '-';
    }
    
    // Parse the ISO date string properly (it's in UTC)
    const now = Date.now();
    const nextCheck = new Date(this.execution.next_check_at).getTime();
    const diff = nextCheck - now;
    
    if (diff < 0) return 'Checking now...';
    
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    
    if (minutes > 0) {
      return `${minutes}m ${remainingSeconds}s`;
    } else {
      return `${seconds}s`;
    }
  }

  refreshExecution(): void {
    if (this.execution?.id) {
      this.loadExecution(this.execution.id);
    }
  }

  closePosition(): void {
    if (!this.execution?.id) return;
    
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '400px',
      data: {
        title: 'Close Position',
        message: `Are you sure you want to close the position for ${this.execution.symbol}? This will immediately close the trade in the broker.`,
        confirmText: 'Close Position',
        cancelText: 'Cancel'
      }
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        this.monitoringService.closePosition(this.execution.id).subscribe({
          next: (result) => {
            this.snackBar.open('Position closed successfully!', 'Dismiss', { duration: 3000 });
            // Reload execution to show updated status
            this.loadExecution(this.execution.id);
          },
          error: (error) => {
            console.error('Failed to close position:', error);
            this.snackBar.open(
              `Failed to close position: ${error.error?.detail || error.message || 'Unknown error'}`, 
              'Dismiss', 
              { duration: 5000 }
            );
          }
        });
      }
    });
  }
}
