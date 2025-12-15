/**
 * Execution Report Modal Component
 * 
 * Displays a summary report of the pipeline execution in a modal
 */

import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { MatChipsModule } from '@angular/material/chips';

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
  ],
  templateUrl: './execution-report-modal.component.html',
  styleUrls: ['./execution-report-modal.component.scss']
})
export class ExecutionReportModalComponent {
  execution: any;

  constructor(
    public dialogRef: MatDialogRef<ExecutionReportModalComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any
  ) {
    this.execution = data.execution;
  }

  close(): void {
    this.dialogRef.close();
  }

  downloadReport(): void {
    const report = this.generateReportText();
    const blob = new Blob([report], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `execution-report-${this.execution.id}.txt`;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  private generateReportText(): string {
    let report = `EXECUTION REPORT\n`;
    report += `================\n\n`;
    report += `Pipeline: ${this.execution.pipeline_name}\n`;
    report += `Symbol: ${this.execution.symbol}\n`;
    report += `Status: ${this.execution.status}\n`;
    report += `Duration: ${this.formatDuration(this.execution.duration_seconds)}\n`;
    report += `Cost: $${this.execution.cost.toFixed(4)}\n`;
    report += `Started: ${new Date(this.execution.started_at).toLocaleString()}\n`;
    report += `\n`;

    // Add agent reports
    if (this.execution.reports) {
      report += `AGENT REPORTS\n`;
      report += `=============\n\n`;
      
      Object.values(this.execution.reports).forEach((agentReport: any) => {
        report += `${agentReport.title}\n`;
        report += `${'-'.repeat(agentReport.title.length)}\n`;
        report += `${agentReport.summary}\n\n`;
      });
    }

    // Add strategy
    if (this.execution.result?.strategy) {
      report += `STRATEGY\n`;
      report += `========\n`;
      report += `Action: ${this.execution.result.strategy.action}\n`;
      report += `Confidence: ${(this.execution.result.strategy.confidence * 100).toFixed(0)}%\n`;
      if (this.execution.result.strategy.reasoning) {
        report += `Reasoning: ${this.execution.result.strategy.reasoning}\n`;
      }
      report += `\n`;
    }

    return report;
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

  formatCost(cost: number): string {
    return `$${cost.toFixed(4)}`;
  }

  getStatusClass(): string {
    return `status-${this.execution.status.toLowerCase()}`;
  }

  getRecommendation(): string {
    const strategy = this.execution.result?.strategy;
    if (!strategy) return 'No strategy available';

    const action = strategy.action;
    const confidence = (strategy.confidence * 100).toFixed(0);

    if (action === 'BUY') {
      return `Bullish signal detected with ${confidence}% confidence. Consider entering a long position.`;
    } else if (action === 'SELL') {
      return `Bearish signal detected with ${confidence}% confidence. Consider entering a short position.`;
    } else {
      return `Hold position. Market conditions don't warrant a trade at this time.`;
    }
  }

  getKeyInsights(): string[] {
    const insights: string[] = [];
    
    // Add bias insight
    if (this.execution.result?.biases) {
      const biasKeys = Object.keys(this.execution.result.biases);
      if (biasKeys.length > 0) {
        const primaryBias = this.execution.result.biases[biasKeys[0]];
        insights.push(`Market Bias: ${primaryBias.bias} (${(primaryBias.confidence * 100).toFixed(0)}% confidence)`);
      }
    }

    // Add strategy insight
    if (this.execution.result?.strategy) {
      const strategy = this.execution.result.strategy;
      if (strategy.pattern_detected) {
        insights.push(`Pattern Detected: ${strategy.pattern_detected}`);
      }
      if (strategy.entry_price) {
        insights.push(`Entry Price: $${strategy.entry_price.toFixed(2)}`);
      }
    }

    // Add risk insight
    if (this.execution.result?.risk_assessment) {
      const risk = this.execution.result.risk_assessment;
      insights.push(`Risk Level: ${risk.risk_level || 'N/A'}`);
      if (risk.position_size) {
        insights.push(`Position Size: ${risk.position_size} shares`);
      }
    }

    return insights.length > 0 ? insights : ['No key insights available'];
  }
}

