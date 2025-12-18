/**
 * Execution Report Modal Component
 * 
 * Displays a comprehensive AI-generated executive report with all agent details,
 * charts, and actionable recommendations
 */

import { Component, Inject, OnInit, ElementRef, ViewChild, QueryList, ViewChildren } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatExpansionModule, MatExpansionPanel } from '@angular/material/expansion';
import { MatTabsModule } from '@angular/material/tabs';
import { environment } from '../../../../environments/environment';

import { TradingChartComponent } from '../../../shared/components/trading-chart/trading-chart.component';
import { ApiService } from '../../../core/services/api.service';

@Component({
  selector: 'app-execution-report-modal',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatExpansionModule,
    MatTabsModule,
    TradingChartComponent,
  ],
  templateUrl: './execution-report-modal.component.html',
  styleUrls: ['./execution-report-modal.component.scss']
})
export class ExecutionReportModalComponent implements OnInit {
  execution: any;
  executiveReport: any = null;
  loading = true;
  error: string | null = null;

  constructor(
    public dialogRef: MatDialogRef<ExecutionReportModalComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
    private apiService: ApiService,
    private http: HttpClient
  ) {
    this.execution = data.execution;
  }

  ngOnInit(): void {
    this.loadExecutiveReport();
  }

  loadExecutiveReport(): void {
    console.log('Loading executive report for execution:', this.execution.id);
    
    // Set a timeout - if AI summary takes too long, show basic report
    const timeout = setTimeout(() => {
      if (this.loading) {
        console.warn('AI summary generation timed out, showing basic report');
        this.executiveReport = {
          execution_context: {
            id: this.execution.id,
            pipeline_name: this.execution.pipeline_name || 'Unknown',
            symbol: this.execution.symbol,
            mode: this.execution.mode,
            started_at: this.execution.started_at,
            completed_at: this.execution.completed_at,
            duration_seconds: this.execution.duration_seconds,
            total_cost: this.execution.cost
          },
          executive_summary: 'Report available - AI summary generation in progress...',
          agent_reports: this.execution.reports || {},
          execution_artifacts: this.execution.result?.execution_artifacts || {}
        };
        this.loading = false;
      }
    }, 5000); // 5 second timeout
    
    this.apiService.get(`/api/v1/executions/${this.execution.id}/executive-report`).subscribe({
      next: (report) => {
        clearTimeout(timeout);
        console.log('Executive report received:', report);
        this.executiveReport = report;
        this.loading = false;
      },
      error: (error) => {
        clearTimeout(timeout);
        console.error('Failed to generate report:', error);
        // Show basic report even on error
        this.executiveReport = {
          execution_context: {
            id: this.execution.id,
            pipeline_name: this.execution.pipeline_name || 'Unknown',
            symbol: this.execution.symbol,
            mode: this.execution.mode,
            started_at: this.execution.started_at,
            completed_at: this.execution.completed_at,
            duration_seconds: this.execution.duration_seconds,
            total_cost: this.execution.cost
          },
          executive_summary: 'AI summary generation failed - showing basic report',
          agent_reports: this.execution.reports || {},
          execution_artifacts: this.execution.result?.execution_artifacts || {},
          error: error.error?.detail || error.message
        };
        this.loading = false;
      }
    });
  }

  close(): void {
    this.dialogRef.close();
  }

  downloadReport(): void {
    // Use HttpClient with blob response type (auth interceptor will add token automatically)
    const url = `${environment.apiUrl}/api/v1/executions/${this.execution.id}/report.pdf`;
    
    this.http.get(url, { responseType: 'blob' }).subscribe({
      next: (blob: Blob) => {
        // Create download link
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = `execution-report-${this.execution.symbol || 'unknown'}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(downloadUrl);
        console.log('PDF downloaded successfully');
      },
      error: (error) => {
        console.error('Failed to download PDF:', error);
        const errorMsg = error.status === 404 
          ? 'PDF not yet generated for this execution'
          : error.status === 401
          ? 'Authentication required - please log in again'
          : error.error?.detail || error.message || 'Failed to download PDF';
        alert(`Failed to download PDF: ${errorMsg}`);
      }
    });
  }


  formatDuration(seconds: number | undefined): string {
    if (!seconds) return '-';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  }

  getStatusClass(): string {
    return `status-${this.execution.status.toLowerCase()}`;
  }

  hasChart(): boolean {
    return this.executiveReport?.execution_artifacts?.strategy_chart;
  }

  getChartData(): any {
    return this.executiveReport?.execution_artifacts?.strategy_chart;
  }

  isArray(value: any): boolean {
    return Array.isArray(value);
  }

  isObject(value: any): boolean {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  hasAgentChart(agentReport: any): boolean {
    // Check if agent report has chart data (look in data.chart or directly in data)
    if (!agentReport || !agentReport.data) {
      return false;
    }
    return !!(agentReport.data.chart || agentReport.data.strategy_chart);
  }

  getAgentChartData(agentReport: any): any {
    if (!agentReport || !agentReport.data) {
      return null;
    }
    return agentReport.data.chart || agentReport.data.strategy_chart || null;
  }
}
