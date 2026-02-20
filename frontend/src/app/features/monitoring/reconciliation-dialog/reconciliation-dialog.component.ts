/**
 * Reconciliation Dialog Component
 *
 * Dialog for handling NEEDS_RECONCILIATION executions:
 * - Auto-reconcile from broker (if trade_id exists)
 * - Close trade manually with calculated or user-supplied P&L
 * - Resume monitoring to let system take over
 */

import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { trigger, transition, style, animate } from '@angular/animations';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatDividerModule } from '@angular/material/divider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

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
    MatDividerModule,
    MatProgressSpinnerModule,
    MatTooltipModule
  ],
  templateUrl: './reconciliation-dialog.component.html',
  styleUrls: ['./reconciliation-dialog.component.scss'],
  animations: [
    trigger('fadeSlide', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(-8px)' }),
        animate('200ms ease-out', style({ opacity: 1, transform: 'translateY(0)' }))
      ]),
      transition(':leave', [
        animate('150ms ease-in', style({ opacity: 0, transform: 'translateY(-8px)' }))
      ])
    ])
  ]
})
export class ReconciliationDialogComponent implements OnInit {
  execution: ExecutionSummary;
  action: 'auto' | 'close' | 'resume' = 'close';

  // Whether the execution has a trade_id (auto-reconcile possible)
  hasTradeId = false;
  tradeId: string | null = null;

  // Form data for manual reconciliation
  reconciliationForm = {
    pnl: null as number | null,
    pnl_percent: null as number | null,
    exit_reason: '',
    exit_price: null as number | null,
    entry_price: null as number | null,
    closed_at: null as Date | null
  };

  // Computed P&L from prices
  calculatedPnl: number | null = null;
  storedQty: number = 1;
  storedSide: string = 'buy';

  loading = false;
  error: string | null = null;
  successMessage: string | null = null;

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
        const te = result.trade_execution;
        this.reconciliationForm.entry_price = te.filled_price || null;
        this.tradeId = te.trade_id || te.order_id || null;
        this.hasTradeId = !!this.tradeId;
        this.storedQty = te.filled_quantity || te.units || te.quantity || 1;

        // Extract side from trade_execution or broker_response
        const brokerResponse = te.broker_response || {};
        this.storedSide = (te.side || brokerResponse.action || 'buy').toLowerCase();
      }
      if (result.trade_outcome) {
        this.reconciliationForm.exit_price = result.trade_outcome.exit_price || null;
        this.reconciliationForm.exit_reason = result.trade_outcome.exit_reason || '';
      }
    }

    // Default action: auto-reconcile if trade_id exists
    if (this.hasTradeId) {
      this.action = 'auto';
    }

    // Default closed_at to now
    this.reconciliationForm.closed_at = new Date();

    // Calculate initial P&L if both prices available
    this.recalculatePnl();
  }

  onActionChange(action: 'auto' | 'close' | 'resume'): void {
    this.action = action;
    this.error = null;
    this.successMessage = null;
  }

  /** Recalculate P&L whenever entry or exit price changes */
  onPriceChange(): void {
    this.recalculatePnl();
  }

  private recalculatePnl(): void {
    const entry = this.reconciliationForm.entry_price;
    const exit = this.reconciliationForm.exit_price;

    if (entry && exit && entry > 0) {
      const qty = Math.abs(this.storedQty);
      if (this.storedSide === 'buy' || this.storedSide === 'long') {
        this.calculatedPnl = (exit - entry) * qty;
      } else {
        this.calculatedPnl = (entry - exit) * qty;
      }
      // Auto-fill P&L and P&L percent
      this.reconciliationForm.pnl = parseFloat(this.calculatedPnl.toFixed(2));
      let pnlPct = ((exit - entry) / entry) * 100;
      if (this.storedSide === 'sell' || this.storedSide === 'short') {
        pnlPct = -pnlPct;
      }
      this.reconciliationForm.pnl_percent = parseFloat(pnlPct.toFixed(2));
    } else {
      this.calculatedPnl = null;
    }
  }

  validateForm(): boolean {
    if (this.action === 'close') {
      // P&L is now optional — backend can calculate from prices or fetch from broker
      // But we need EITHER prices OR pnl
      const hasPnl = this.reconciliationForm.pnl !== null && this.reconciliationForm.pnl !== undefined;
      const hasPrices = this.reconciliationForm.entry_price !== null && this.reconciliationForm.exit_price !== null;

      if (!hasPnl && !hasPrices) {
        this.error = 'Please provide either entry & exit prices (P&L will be calculated) or P&L directly.';
        return false;
      }
    }
    return true;
  }

  submit(): void {
    this.error = null;
    this.successMessage = null;

    if (this.action === 'auto') {
      this.submitAutoReconcile();
    } else if (this.action === 'close') {
      if (!this.validateForm()) {
        return;
      }
      this.submitManualReconcile();
    } else {
      this.submitResumeMonitoring();
    }
  }

  private submitAutoReconcile(): void {
    this.loading = true;

    const reconciliationData: any = {
      auto_reconcile: true
    };

    // Include any user-provided overrides
    if (this.reconciliationForm.exit_reason) {
      reconciliationData.exit_reason = this.reconciliationForm.exit_reason;
    }
    if (this.reconciliationForm.closed_at) {
      reconciliationData.closed_at = this.reconciliationForm.closed_at.toISOString();
    }

    this.monitoringService.reconcileExecution(this.execution.id, reconciliationData).subscribe({
      next: (result) => {
        this.loading = false;
        this.dialogRef.close({ success: true, action: 'auto', result });
      },
      error: (error) => {
        this.loading = false;
        this.error = error.error?.detail || error.message || 'Auto-reconciliation failed. Try closing manually.';
      }
    });
  }

  private submitManualReconcile(): void {
    this.loading = true;

    const reconciliationData: any = {};

    if (this.reconciliationForm.pnl !== null) {
      reconciliationData.pnl = this.reconciliationForm.pnl;
    }
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
  }

  private submitResumeMonitoring(): void {
    this.loading = true;

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

  cancel(): void {
    this.dialogRef.close();
  }

  getSymbol(): string {
    return this.execution.symbol || 'N/A';
  }

  getPipelineName(): string {
    return this.execution.pipeline_name || 'Unknown Pipeline';
  }

  /** Format P&L with sign and color hint */
  formatPnl(value: number | null): string {
    if (value === null || value === undefined) return '—';
    return (value >= 0 ? '+' : '') + value.toFixed(2);
  }
}
