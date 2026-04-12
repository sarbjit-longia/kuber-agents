import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatNativeDateModule } from '@angular/material/core';

import { Pipeline } from '../../../core/models/pipeline.model';
import { BacktestCreateRequest } from '../../../core/models/backtest.model';
import { BacktestService } from '../../../core/services/backtest.service';

export interface BacktestLaunchDialogData {
  pipeline: Pipeline;
}

@Component({
  selector: 'app-backtest-launch-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatDatepickerModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatNativeDateModule,
  ],
  templateUrl: './backtest-launch-dialog.component.html',
  styleUrls: ['./backtest-launch-dialog.component.scss']
})
export class BacktestLaunchDialogComponent implements OnInit {
  readonly timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'];
  readonly slippageModels = [
    { value: 'fixed', label: 'Fixed' },
    { value: 'bps', label: 'Basis points' },
  ];
  readonly commissionModels = [
    { value: 'per_share', label: 'Per share' },
    { value: 'fixed', label: 'Fixed ticket' },
    { value: 'percent', label: 'Percent of notional' },
  ];

  readonly form = this.fb.group({
    symbolsText: ['', [Validators.required]],
    startDate: [null as Date | null, [Validators.required]],
    endDate: [null as Date | null, [Validators.required]],
    timeframe: ['5m', [Validators.required]],
    initialCapital: [10000, [Validators.required, Validators.min(1)]],
    slippageModel: ['fixed', [Validators.required]],
    slippageValue: [0.01, [Validators.required, Validators.min(0)]],
    commissionModel: ['per_share', [Validators.required]],
    commissionValue: [0.005, [Validators.required, Validators.min(0)]],
    maxCostUsd: [null as number | null],
  });

  launching = false;

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: BacktestLaunchDialogData,
    private dialogRef: MatDialogRef<BacktestLaunchDialogComponent>,
    private fb: FormBuilder,
    private backtestService: BacktestService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.seedDefaults();
  }

  get pipeline(): Pipeline {
    return this.data.pipeline;
  }

  get estimatedCostUsd(): number {
    const start = this.form.controls.startDate.value;
    const end = this.form.controls.endDate.value;
    const symbols = this.parseSymbols(this.form.controls.symbolsText.value ?? '');

    if (!start || !end || symbols.length === 0) {
      return 0;
    }

    const days = Math.max(
      1,
      Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24))
    );
    const estimatedExecutions = symbols.length * Math.max(1, Math.round((days / 30) * 100));
    return Number((estimatedExecutions * 0.075).toFixed(2));
  }

  get formHasDateError(): boolean {
    const start = this.form.controls.startDate.value;
    const end = this.form.controls.endDate.value;
    return !!(start && end && start.getTime() > end.getTime());
  }

  get canLaunch(): boolean {
    return this.form.valid && !this.formHasDateError && !this.launching;
  }

  close(): void {
    this.dialogRef.close();
  }

  launchBacktest(): void {
    if (!this.canLaunch) {
      this.form.markAllAsTouched();
      return;
    }

    this.launching = true;
    const payload: BacktestCreateRequest = {
      pipeline_id: this.pipeline.id,
      symbols: this.parseSymbols(this.form.controls.symbolsText.value ?? ''),
      start_date: this.formatDateForApi(this.form.controls.startDate.value),
      end_date: this.formatDateForApi(this.form.controls.endDate.value),
      timeframe: this.form.controls.timeframe.value ?? '5m',
      initial_capital: Number(this.form.controls.initialCapital.value ?? 0),
      slippage_model: this.form.controls.slippageModel.value ?? 'fixed',
      slippage_value: Number(this.form.controls.slippageValue.value),
      commission_model: this.form.controls.commissionModel.value ?? 'per_share',
      commission_value: Number(this.form.controls.commissionValue.value),
      max_cost_usd: this.form.controls.maxCostUsd.value
        ? Number(this.form.controls.maxCostUsd.value)
        : null,
    };

    this.backtestService.startBacktest(payload).subscribe({
      next: (response) => {
        this.launching = false;
        this.toast('Backtest launched', 'success');
        this.dialogRef.close({ runId: response.run_id });
      },
      error: (error) => {
        this.launching = false;
        const message = error?.error?.detail || 'Failed to start backtest';
        this.toast(message, 'error');
      }
    });
  }

  private seedDefaults(): void {
    const defaultSymbols = this.pipeline.scanner_tickers?.length
      ? this.pipeline.scanner_tickers
      : this.pipeline.config?.symbol
        ? [this.pipeline.config.symbol]
        : ['AAPL'];

    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - 30);

    this.form.patchValue({
      symbolsText: defaultSymbols.join(', '),
      startDate,
      endDate,
    });
  }

  private parseSymbols(raw: string): string[] {
    return raw
      .split(',')
      .map(symbol => symbol.trim().toUpperCase())
      .filter(Boolean);
  }

  private formatDateForApi(value: Date | null): string {
    if (!value) {
      return '';
    }
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private toast(message: string, type: 'success' | 'error'): void {
    this.snackBar.open(message, 'Close', {
      duration: 3500,
      horizontalPosition: 'right',
      verticalPosition: 'top',
      panelClass: [`snackbar-${type}`]
    });
  }
}
