/**
 * Execution Detail Component
 * 
 * Displays detailed information about a pipeline execution including agent reports and charts
 */

import { Component, OnInit } from '@angular/core';
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

import { MonitoringService } from '../../../core/services/monitoring.service';
import { NavbarComponent } from '../../../core/components/navbar/navbar.component';
import { TradingChartComponent } from '../../../shared/components/trading-chart/trading-chart.component';
import { ExecutionReportModalComponent } from '../execution-report-modal/execution-report-modal.component';

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
    NavbarComponent,
    TradingChartComponent,
  ],
  templateUrl: './execution-detail.component.html',
  styleUrls: ['./execution-detail.component.scss']
})
export class ExecutionDetailComponent implements OnInit {
  execution: any = null;
  loading = true;
  error: string | null = null;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private monitoringService: MonitoringService,
    private dialog: MatDialog
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.loadExecution(id);
    } else {
      this.error = 'No execution ID provided';
      this.loading = false;
    }
  }

  loadExecution(id: string): void {
    this.monitoringService.getExecutionDetail(id).subscribe({
      next: (data) => {
        this.execution = data;
        this.loading = false;
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

  formatDate(dateString: string): string {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString();
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
}
