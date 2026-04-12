import { CommonModule } from '@angular/common';
import { Component, Inject, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Subscription, interval } from 'rxjs';

import { Pipeline } from '../../../core/models/pipeline.model';
import { LocalDatePipe } from '../../../shared/pipes/local-date.pipe';
import {
  BacktestCreateRequest,
  BacktestRunSummary,
  BacktestRunStatus,
} from '../../../core/models/backtest.model';
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
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    LocalDatePipe,
  ],
  templateUrl: './backtest-launch-dialog.component.html',
  styleUrls: ['./backtest-launch-dialog.component.scss']
})
export class BacktestLaunchDialogComponent implements OnInit, OnDestroy {
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
    startDate: ['', [Validators.required]],
    endDate: ['', [Validators.required]],
    timeframe: ['5m', [Validators.required]],
    initialCapital: [10000, [Validators.required, Validators.min(1)]],
    slippageModel: ['fixed', [Validators.required]],
    slippageValue: [0.01, [Validators.required, Validators.min(0)]],
    commissionModel: ['per_share', [Validators.required]],
    commissionValue: [0.005, [Validators.required, Validators.min(0)]],
    maxCostUsd: [null as number | null],
  });

  loadingRuns = false;
  launching = false;
  cancellingRunId: string | null = null;
  recentRuns: BacktestRunSummary[] = [];
  latestRun: BacktestRunSummary | null = null;
  private pollSub?: Subscription;

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: BacktestLaunchDialogData,
    private dialogRef: MatDialogRef<BacktestLaunchDialogComponent>,
    private fb: FormBuilder,
    private backtestService: BacktestService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.seedDefaults();
    this.loadRecentRuns();
    this.pollSub = interval(5000).subscribe(() => {
      if (this.hasActiveRun()) {
        this.loadRecentRuns(false);
      }
    });
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
  }

  get pipeline(): Pipeline {
    return this.data.pipeline;
  }

  get estimatedCostUsd(): number {
    const start = this.form.controls.startDate.value ?? '';
    const end = this.form.controls.endDate.value ?? '';
    const symbols = this.parseSymbols(this.form.controls.symbolsText.value ?? '');

    if (!start || !end || symbols.length === 0) {
      return 0;
    }

    const startDate = new Date(start);
    const endDate = new Date(end);
    const days = Math.max(
      1,
      Math.round((endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24))
    );
    const estimatedExecutions = symbols.length * Math.max(1, Math.round((days / 30) * 100));
    return Number((estimatedExecutions * 0.075).toFixed(2));
  }

  get formHasDateError(): boolean {
    const start = this.form.controls.startDate.value ?? '';
    const end = this.form.controls.endDate.value ?? '';
    return !!(start && end && start > end);
  }

  get canLaunch(): boolean {
    return this.form.valid && !this.formHasDateError && !this.launching;
  }

  close(): void {
    this.dialogRef.close();
  }

  loadRecentRuns(showSpinner = true): void {
    if (showSpinner) {
      this.loadingRuns = true;
    }

    this.backtestService.listBacktests(0, 100).subscribe({
      next: (response) => {
        this.recentRuns = (response.backtests || [])
          .filter(run => run.pipeline_id === this.pipeline.id)
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
          .slice(0, 8);
        this.latestRun = this.recentRuns[0] ?? null;
        this.loadingRuns = false;
      },
      error: () => {
        this.loadingRuns = false;
        this.toast('Failed to load backtest runs', 'error');
      }
    });
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
      start_date: this.form.controls.startDate.value ?? '',
      end_date: this.form.controls.endDate.value ?? '',
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
      next: () => {
        this.launching = false;
        this.toast('Backtest launched', 'success');
        this.loadRecentRuns();
      },
      error: (error) => {
        this.launching = false;
        const message = error?.error?.detail || 'Failed to start backtest';
        this.toast(message, 'error');
      }
    });
  }

  cancelRun(run: BacktestRunSummary): void {
    if (!this.isActive(run.status)) {
      return;
    }

    this.cancellingRunId = run.id;
    this.backtestService.cancelBacktest(run.id).subscribe({
      next: () => {
        this.cancellingRunId = null;
        this.toast('Backtest cancelled', 'success');
        this.loadRecentRuns(false);
      },
      error: () => {
        this.cancellingRunId = null;
        this.toast('Failed to cancel backtest', 'error');
      }
    });
  }

  isActive(status: BacktestRunStatus): boolean {
    return status === 'PENDING' || status === 'RUNNING';
  }

  hasActiveRun(): boolean {
    return this.recentRuns.some(run => this.isActive(run.status));
  }

  statusLabel(status: BacktestRunStatus): string {
    return status.charAt(0) + status.slice(1).toLowerCase();
  }

  statusClass(status: BacktestRunStatus): string {
    return `status-${status.toLowerCase()}`;
  }

  progressValue(run: BacktestRunSummary): number {
    return Number(run.progress?.['percent_complete'] || 0);
  }

  symbolsSummary(run: BacktestRunSummary): string {
    const symbols = run.config?.['symbols'];
    if (!Array.isArray(symbols) || symbols.length === 0) {
      return 'No symbols recorded';
    }
    return symbols.join(', ');
  }

  currentSymbol(run: BacktestRunSummary | null): string {
    return String(run?.progress?.['current_symbol'] || '');
  }

  runTimeframe(run: BacktestRunSummary): string {
    return String(run.config?.['timeframe'] || '5m');
  }

  metricValue(run: BacktestRunSummary, key: string): number | null {
    const raw = run.metrics?.[key];
    return typeof raw === 'number' ? raw : null;
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
      startDate: this.toDateInput(startDate),
      endDate: this.toDateInput(endDate),
    });
  }

  private parseSymbols(raw: string): string[] {
    return raw
      .split(',')
      .map(symbol => symbol.trim().toUpperCase())
      .filter(Boolean);
  }

  private toDateInput(value: Date): string {
    return value.toISOString().slice(0, 10);
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
