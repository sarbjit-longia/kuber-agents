/**
 * Reconciliation Dialog Component
 * 
 * Dialog for handling NEEDS_RECONCILIATION executions:
 * - Close trade manually with P&L information
 * - Resume monitoring to let system take over
 */

import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatTabsModule } from '@angular/material/tabs';
import { MatDividerModule } from '@angular/material/divider';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { MonitoringService } from '../../../core/services/monitoring.service';
import { ExecutionSummary } from '../../../core/models/execution.model';

@Component({
  selector: 'app-reconciliation-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatTabsModule,
    MatDividerModule,
    MatChipsModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './reconciliation-dialog.component.html',
  styleUrls: ['./reconciliation-dialog.component.scss']
})
export class ReconciliationDialogComponent implements OnInit {
  execution: ExecutionSummary;
  action: 'close' | 'resume' = 'close';
  
  // Form data for manual reconciliation
  reconciliationForm = {
    pnl: null as number | null,
    pnl_percent: null as number | null,
    exit_reason: '',
    exit_price: null as number | null,
    entry_price: null as number | null,
    closed_at: null as Date | null
  };
  
  loading = false;
  error: string | null = null;

  constructor(
    public dialogRef: MatDialogRef<ReconciliationDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { execution: ExecutionSummary },
    private monitoringService: MonitoringService
  ) {
    this.execution = data.execution;
  }

  ngOnInit(): void {
    // Pre-fill form with existing data if available
    if (this.execution.result) {
      const result = this.execution.result;
      if (result.trade_execution) {
        this.reconciliationForm.entry_price = result.trade_execution.filled_price || null;
      }
      if (result.trade_outcome) {
        this.reconciliationForm.exit_price = result.trade_outcome.exit_price || null;
        this.reconciliationForm.exit_reason = result.trade_outcome.exit_reason || '';
      }
    }
    
    // Default closed_at to now
    this.reconciliationForm.closed_at = new Date();
  }

  onActionChange(action: 'close' | 'resume'): void {
    this.action = action;
    this.error = null;
  }

  validateForm(): boolean {
    if (this.action === 'close') {
      if (this.reconciliationForm.pnl === null || this.reconciliationForm.pnl === undefined) {
        this.error = 'P&L is required';
        return false;
      }
    }
    return true;
  }

  submit(): void {
    this.error = null;
    
    if (!this.validateForm()) {
      return;
    }
    
    this.loading = true;
    
    if (this.action === 'close') {
      // Prepare reconciliation data
      const reconciliationData: any = {
        pnl: this.reconciliationForm.pnl
      };
      
      if (this.reconciliationForm.pnl_percent !== null) {
        reconciliationData.pnl_percent = this.reconciliationForm.pnl_percent;
      }
      if (this.reconciliationForm.exit_reason) {
        reconciliationData.exit_reason = this.reconciliationForm.exit_reason;
      }
      if (this.reconciliationForm.exit_price !== null) {
        reconciliationData.exit_price = this.reconciliationForm.exit_price;
      }
      if (this.reconciliationForm.entry_price !== null) {
        reconciliationData.entry_price = this.reconciliationForm.entry_price;
      }
      if (this.reconciliationForm.closed_at) {
        reconciliationData.closed_at = this.reconciliationForm.closed_at.toISOString();
      }
      
      this.monitoringService.reconcileExecution(this.execution.id, reconciliationData).subscribe({
        next: (result) => {
          this.loading = false;
          this.dialogRef.close({ success: true, action: 'close', result });
        },
        error: (error) => {
          this.loading = false;
          this.error = error.error?.detail || error.message || 'Failed to reconcile execution';
        }
      });
    } else {
      // Resume monitoring
      this.monitoringService.resumeMonitoring(this.execution.id).subscribe({
        next: (result) => {
          this.loading = false;
          this.dialogRef.close({ success: true, action: 'resume', result });
        },
        error: (error) => {
          this.loading = false;
          this.error = error.error?.detail || error.message || 'Failed to resume monitoring';
        }
      });
    }
  }

  cancel(): void {
    this.dialogRef.close();
  }

  getSymbol(): string {
    return this.execution.symbol || 'N/A';
  }

  getPipelineName(): string {
    return this.execution.pipeline_name || 'Unknown Pipeline';
  }
}
