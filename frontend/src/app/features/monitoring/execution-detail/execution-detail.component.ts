/**
 * Execution Detail Component
 * 
 * Detailed view of a single pipeline execution with agent progress and logs
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';

import { MonitoringService } from '../../../core/services/monitoring.service';
import { Execution, AgentState, ExecutionLog } from '../../../core/models/execution.model';
import { NavbarComponent } from '../../../core/components/navbar/navbar.component';

@Component({
  selector: 'app-execution-detail',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatExpansionModule,
    MatSnackBarModule,
    MatTabsModule,
    NavbarComponent
  ],
  templateUrl: './execution-detail.component.html',
  styleUrls: ['./execution-detail.component.scss']
})
export class ExecutionDetailComponent implements OnInit, OnDestroy {
  execution: Execution | null = null;
  logs: ExecutionLog[] = [];
  loading = true;
  executionId: string = '';

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private monitoringService: MonitoringService,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.executionId = this.route.snapshot.paramMap.get('id') || '';
    this.loadExecution();
    this.loadLogs();

    // Start polling if execution is running
    this.monitoringService.currentExecution$.subscribe(execution => {
      if (execution && ['running', 'pending'].includes(execution.status)) {
        this.monitoringService.startPolling(this.executionId);
      }
    });
  }

  ngOnDestroy(): void {
    this.monitoringService.stopPolling();
  }

  loadExecution(): void {
    this.monitoringService.getExecution(this.executionId).subscribe({
      next: (execution) => {
        this.execution = execution;
        this.loading = false;
      },
      error: (error) => {
        console.error('Failed to load execution:', error);
        this.loading = false;
        this.showNotification('Failed to load execution details', 'error');
      }
    });
  }

  loadLogs(): void {
    this.monitoringService.getExecutionLogs(this.executionId, 100).subscribe({
      next: (logs) => {
        this.logs = logs;
      },
      error: (error) => {
        console.error('Failed to load logs:', error);
      }
    });
  }

  stopExecution(): void {
    if (confirm('Stop this execution?')) {
      this.monitoringService.stopExecution(this.executionId).subscribe({
        next: () => {
          this.showNotification('Execution stopped', 'success');
          this.loadExecution();
        },
        error: (error) => {
          console.error('Failed to stop execution:', error);
          this.showNotification('Failed to stop execution', 'error');
        }
      });
    }
  }

  pauseExecution(): void {
    this.monitoringService.pauseExecution(this.executionId).subscribe({
      next: () => {
        this.showNotification('Execution paused', 'success');
        this.loadExecution();
      },
      error: (error) => {
        console.error('Failed to pause execution:', error);
        this.showNotification('Failed to pause execution', 'error');
      }
    });
  }

  resumeExecution(): void {
    this.monitoringService.resumeExecution(this.executionId).subscribe({
      next: () => {
        this.showNotification('Execution resumed', 'success');
        this.loadExecution();
      },
      error: (error) => {
        console.error('Failed to resume execution:', error);
        this.showNotification('Failed to resume execution', 'error');
      }
    });
  }

  getAgentProgress(): number {
    if (!this.execution || !this.execution.agent_states) return 0;
    const completed = this.execution.agent_states.filter(a => a.status === 'completed').length;
    return (completed / this.execution.agent_states.length) * 100;
  }

  getAgentStatusIcon(status: string): string {
    const icons: any = {
      'pending': 'schedule',
      'running': 'play_circle',
      'completed': 'check_circle',
      'failed': 'error',
      'skipped': 'skip_next'
    };
    return icons[status] || 'help';
  }

  getAgentStatusColor(status: string): string {
    const colors: any = {
      'pending': 'default',
      'running': 'primary',
      'completed': 'accent',
      'failed': 'warn',
      'skipped': 'default'
    };
    return colors[status] || 'default';
  }

  getLogLevelIcon(level: string): string {
    const icons: any = {
      'debug': 'bug_report',
      'info': 'info',
      'warning': 'warning',
      'error': 'error',
      'critical': 'report_problem'
    };
    return icons[level] || 'info';
  }

  getLogLevelClass(level: string): string {
    return `log-${level}`;
  }

  formatDate(dateString: string): string {
    return new Date(dateString).toLocaleString();
  }

  formatDuration(agent: AgentState): string {
    if (!agent.started_at) return '-';
    const start = new Date(agent.started_at).getTime();
    const end = agent.completed_at ? new Date(agent.completed_at).getTime() : Date.now();
    const duration = Math.floor((end - start) / 1000);
    return `${duration}s`;
  }

  formatCost(cost: number | undefined): string {
    return cost ? `$${cost.toFixed(4)}` : '$0.0000';
  }

  back(): void {
    this.router.navigate(['/monitoring']);
  }

  showNotification(message: string, type: 'success' | 'error' | 'info'): void {
    this.snackBar.open(message, 'Close', {
      duration: 3000,
      horizontalPosition: 'right',
      verticalPosition: 'top',
      panelClass: [`snackbar-${type}`]
    });
  }
}

