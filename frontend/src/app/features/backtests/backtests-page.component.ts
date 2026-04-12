import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { Subscription, interval } from 'rxjs';

import {
  BacktestCreateRequest,
  BacktestExecutionSummary,
  BacktestReportResponse,
  BacktestRunResult,
  BacktestRunSummary,
  BacktestTimelineEvent,
} from '../../core/models/backtest.model';
import { Pipeline } from '../../core/models/pipeline.model';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { BacktestService } from '../../core/services/backtest.service';
import { PipelineService } from '../../core/services/pipeline.service';
import { FooterComponent } from '../../shared/components/footer/footer.component';
import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';

@Component({
  selector: 'app-backtests-page',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTabsModule,
    NavbarComponent,
    FooterComponent,
    LocalDatePipe,
  ],
  templateUrl: './backtests-page.component.html',
  styleUrls: ['./backtests-page.component.scss'],
})
export class BacktestsPageComponent implements OnInit, OnDestroy {
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
    pipelineId: ['', [Validators.required]],
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

  pipelines: Pipeline[] = [];
  runs: BacktestRunSummary[] = [];
  selectedRun: BacktestRunResult | null = null;
  selectedRunSummary: BacktestRunSummary | null = null;
  selectedExecutions: BacktestExecutionSummary[] = [];
  selectedTimeline: BacktestTimelineEvent[] = [];
  selectedReport: BacktestReportResponse | null = null;
  selectedRunId: string | null = null;
  selectedPipelineId: string | null = null;

  loadingPipelines = true;
  loadingRuns = true;
  loadingDetails = false;
  launching = false;
  cancellingRunId: string | null = null;

  private pollSub?: Subscription;
  private routeSub?: Subscription;

  constructor(
    private readonly fb: FormBuilder,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly pipelineService: PipelineService,
    private readonly backtestService: BacktestService,
    private readonly snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.routeSub = this.route.paramMap.subscribe(params => {
      this.selectedRunId = params.get('id');
      this.selectedPipelineId = this.route.snapshot.queryParamMap.get('pipelineId');
      this.loadWorkspace();
    });

    this.pollSub = interval(5000).subscribe(() => {
      if (this.hasActiveRun()) {
        this.loadRuns(false);
        if (this.selectedRunId) {
          this.loadSelectedRun(this.selectedRunId, false);
        }
      }
    });
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
    this.routeSub?.unsubscribe();
  }

  get canLaunch(): boolean {
    return this.form.valid && !this.launching && !this.formHasDateError;
  }

  get formHasDateError(): boolean {
    const start = this.form.controls.startDate.value ?? '';
    const end = this.form.controls.endDate.value ?? '';
    return !!(start && end && start > end);
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
    const days = Math.max(1, Math.round((endDate.getTime() - startDate.getTime()) / 86400000));
    const estimatedExecutions = symbols.length * Math.max(1, Math.round((days / 30) * 100));
    return Number((estimatedExecutions * 0.075).toFixed(2));
  }

  get equityChartPath(): string {
    if (!this.selectedRun?.equity_curve?.length || this.selectedRun.equity_curve.length < 2) {
      return '';
    }
    const values = this.selectedRun.equity_curve;
    const width = 720;
    const height = 220;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = Math.max(max - min, 1);
    return values
      .map((value, index) => {
        const x = (index / Math.max(values.length - 1, 1)) * width;
        const y = height - ((value - min) / range) * height;
        return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  }

  get equityChartAreaPath(): string {
    if (!this.equityChartPath || !this.selectedRun?.equity_curve?.length) {
      return '';
    }
    const width = 720;
    const height = 220;
    return `${this.equityChartPath} L${width},${height} L0,${height} Z`;
  }

  get latestVisibleEvents(): BacktestTimelineEvent[] {
    return this.selectedTimeline.slice(0, 60);
  }

  get activeRunCount(): number {
    return this.runs.filter(run => this.isActive(run.status)).length;
  }

  get selectedSymbolsLabel(): string {
    const symbols = this.selectedRun?.config?.['symbols'];
    return Array.isArray(symbols) && symbols.length > 0 ? symbols.join(', ') : 'No symbols';
  }

  loadWorkspace(): void {
    this.loadPipelines();
    this.loadRuns(true);
  }

  loadPipelines(): void {
    this.loadingPipelines = true;
    this.pipelineService.loadPipelines().subscribe({
      next: (pipelines) => {
        this.pipelines = pipelines;
        const pipelineId = this.selectedPipelineId || this.form.controls.pipelineId.value || pipelines[0]?.id || '';
        this.form.patchValue({ pipelineId }, { emitEvent: false });
        this.seedFormFromPipeline(pipelineId);
        this.loadingPipelines = false;
      },
      error: () => {
        this.loadingPipelines = false;
        this.toast('Failed to load pipelines', 'error');
      },
    });
  }

  loadRuns(showSpinner = true): void {
    if (showSpinner) {
      this.loadingRuns = true;
    }
    this.backtestService.listBacktests(0, 100).subscribe({
      next: (response) => {
        this.runs = response.backtests || [];
        if (this.selectedRunId) {
          this.loadSelectedRun(this.selectedRunId, false);
        } else if (this.runs.length > 0) {
          const preferred =
            this.runs.find(run => run.pipeline_id === this.form.controls.pipelineId.value) ||
            this.runs[0];
          this.selectRun(preferred.id, false);
        }
        this.loadingRuns = false;
      },
      error: () => {
        this.loadingRuns = false;
        this.toast('Failed to load backtests', 'error');
      },
    });
  }

  selectRun(runId: string, navigate = true): void {
    this.selectedRunId = runId;
    if (navigate) {
      this.router.navigate(['/backtests', runId], {
        queryParams: {
          pipelineId: this.form.controls.pipelineId.value || this.selectedPipelineId || null,
        },
      });
    }
    this.loadSelectedRun(runId, true);
  }

  loadSelectedRun(runId: string, showSpinner = true): void {
    if (showSpinner) {
      this.loadingDetails = true;
    }
    this.backtestService.getBacktestResults(runId).subscribe({
      next: (run) => {
        this.selectedRun = run;
        this.selectedRunSummary = run;
        this.loadExecutions(runId);
        this.loadTimeline(runId);
        this.loadReport(runId);
        this.loadingDetails = false;
      },
      error: () => {
        this.loadingDetails = false;
        this.toast('Failed to load backtest details', 'error');
      },
    });
  }

  loadExecutions(runId: string): void {
    this.backtestService.getBacktestExecutions(runId).subscribe({
      next: (response) => {
        this.selectedExecutions = response.executions || [];
      },
      error: () => {
        this.selectedExecutions = [];
      },
    });
  }

  loadTimeline(runId: string): void {
    this.backtestService.getBacktestTimeline(runId).subscribe({
      next: (response) => {
        this.selectedTimeline = response.events || [];
      },
      error: () => {
        this.selectedTimeline = [];
      },
    });
  }

  loadReport(runId: string): void {
    this.backtestService.getBacktestReport(runId).subscribe({
      next: (report) => {
        this.selectedReport = report;
      },
      error: () => {
        this.selectedReport = null;
      },
    });
  }

  launchBacktest(): void {
    if (!this.canLaunch) {
      this.form.markAllAsTouched();
      return;
    }

    this.launching = true;
    const payload: BacktestCreateRequest = {
      pipeline_id: this.form.controls.pipelineId.value ?? '',
      symbols: this.parseSymbols(this.form.controls.symbolsText.value ?? ''),
      start_date: this.form.controls.startDate.value ?? '',
      end_date: this.form.controls.endDate.value ?? '',
      timeframe: this.form.controls.timeframe.value ?? '5m',
      initial_capital: Number(this.form.controls.initialCapital.value ?? 0),
      slippage_model: this.form.controls.slippageModel.value ?? 'fixed',
      slippage_value: Number(this.form.controls.slippageValue.value ?? 0),
      commission_model: this.form.controls.commissionModel.value ?? 'per_share',
      commission_value: Number(this.form.controls.commissionValue.value ?? 0),
      max_cost_usd: this.form.controls.maxCostUsd.value
        ? Number(this.form.controls.maxCostUsd.value)
        : null,
    };

    this.backtestService.startBacktest(payload).subscribe({
      next: (response) => {
        this.launching = false;
        this.toast('Backtest launched', 'success');
        this.router.navigate(['/backtests', response.run_id], {
          queryParams: { pipelineId: payload.pipeline_id },
        });
      },
      error: (error) => {
        this.launching = false;
        this.toast(error?.error?.detail || 'Failed to launch backtest', 'error');
      },
    });
  }

  cancelRun(runId: string): void {
    this.cancellingRunId = runId;
    this.backtestService.cancelBacktest(runId).subscribe({
      next: () => {
        this.cancellingRunId = null;
        this.toast('Backtest cancelled', 'success');
        this.loadRuns(false);
        if (this.selectedRunId === runId) {
          this.loadSelectedRun(runId, false);
        }
      },
      error: () => {
        this.cancellingRunId = null;
        this.toast('Failed to cancel backtest', 'error');
      },
    });
  }

  onPipelineChanged(): void {
    const pipelineId = this.form.controls.pipelineId.value ?? '';
    this.selectedPipelineId = pipelineId;
    this.seedFormFromPipeline(pipelineId);
    this.router.navigate(['/backtests'], { queryParams: { pipelineId } });
  }

  seedFormFromPipeline(pipelineId: string): void {
    const pipeline = this.pipelines.find(item => item.id === pipelineId);
    if (!pipeline) {
      return;
    }
    const today = new Date();
    const end = today.toISOString().slice(0, 10);
    const start = new Date(today.getTime() - 14 * 86400000).toISOString().slice(0, 10);
    const defaultSymbols = this.defaultSymbolsForPipeline(pipeline);
    this.form.patchValue(
      {
        pipelineId,
        symbolsText: defaultSymbols.join(', '),
        startDate: this.form.controls.startDate.value || start,
        endDate: this.form.controls.endDate.value || end,
      },
      { emitEvent: false },
    );
  }

  defaultSymbolsForPipeline(pipeline: Pipeline): string[] {
    const scannerTickers = pipeline.scanner_tickers || [];
    if (scannerTickers.length > 0) {
      return scannerTickers;
    }
    const symbol = pipeline.config?.symbol;
    return symbol ? [symbol] : [];
  }

  parseSymbols(input: string): string[] {
    return input
      .split(/[\s,]+/)
      .map(value => value.trim().toUpperCase())
      .filter(Boolean);
  }

  hasActiveRun(): boolean {
    return this.runs.some(run => this.isActive(run.status));
  }

  isActive(status: string): boolean {
    return status === 'PENDING' || status === 'RUNNING';
  }

  progressValue(run: BacktestRunSummary | BacktestRunResult | null): number {
    return Number(run?.progress?.['percent_complete'] || 0);
  }

  statusClass(status: string | undefined | null): string {
    return `status-${String(status || 'unknown').toLowerCase()}`;
  }

  statusLabel(status: string | undefined | null): string {
    return String(status || 'UNKNOWN').replace(/_/g, ' ');
  }

  metricEntries(): Array<{ label: string; value: string }> {
    const metrics = this.selectedRun?.metrics || {};
    const entries = [
      ['Processed Bars', this.selectedRun?.progress?.['current_bar'] ?? 0],
      ['Trade Count', this.selectedRun?.trades_count ?? 0],
      ['Win Rate', metrics['win_rate']],
      ['Profit Factor', metrics['profit_factor']],
      ['Max Drawdown', metrics['max_drawdown']],
      ['Sharpe', metrics['sharpe_ratio']],
      ['Avg Winner', metrics['avg_winner']],
      ['Avg Loser', metrics['avg_loser']],
    ];
    return entries.map(([label, value]) => ({
      label: String(label),
      value: value === null || value === undefined || value === '' ? 'N/A' : String(value),
    }));
  }

  latestDecision(execution: BacktestExecutionSummary): string {
    const strategy = execution.result?.['strategy'] || {};
    const review = execution.reports?.['node-trade_review_agent']?.['data'] || {};
    const decision = review['decision'] || strategy['action'] || 'N/A';
    return String(decision);
  }

  trackByRunId(_index: number, run: BacktestRunSummary): string {
    return run.id;
  }

  trackByEventId(_index: number, event: BacktestTimelineEvent): string {
    return event.id;
  }

  reportArrayItems(values: unknown): string[] {
    return Array.isArray(values) ? values.map(value => String(value)) : [];
  }

  private toast(message: string, panelClass: 'success' | 'error'): void {
    this.snackBar.open(message, 'Dismiss', {
      duration: 3200,
      panelClass: [`toast-${panelClass}`],
    });
  }
}
