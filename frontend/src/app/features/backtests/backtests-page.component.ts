import { CommonModule } from '@angular/common';
import { Component, HostListener, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatNativeDateModule } from '@angular/material/core';
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
import { BacktestLaunchDialogComponent } from '../pipelines/backtest-launch-dialog/backtest-launch-dialog.component';
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
    MatDialogModule,
    MatDividerModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTabsModule,
    MatNativeDateModule,
    NavbarComponent,
    FooterComponent,
    LocalDatePipe,
  ],
  templateUrl: './backtests-page.component.html',
  styleUrls: ['./backtests-page.component.scss'],
})
export class BacktestsPageComponent implements OnInit, OnDestroy {
  private static readonly EXECUTION_DRAWER_WIDTH_KEY = 'backtests.executionDrawerWidth';
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

  pipelines: Pipeline[] = [];
  runs: BacktestRunSummary[] = [];
  selectedRun: BacktestRunResult | null = null;
  selectedRunSummary: BacktestRunSummary | null = null;
  selectedExecutions: BacktestExecutionSummary[] = [];
  selectedExecution: BacktestExecutionSummary | null = null;
  selectedTimeline: BacktestTimelineEvent[] = [];
  selectedReport: BacktestReportResponse | null = null;
  selectedRunId: string | null = null;
  selectedPipelineId: string | null = null;
  executionFilter = 'all';
  executionSymbolFilter = 'all';
  executionDecisionFilter = 'all';

  loadingPipelines = true;
  loadingRuns = true;
  loadingDetails = false;
  launching = false;
  cancellingRunId: string | null = null;
  executionDrawerWidth = 720;
  private draggingExecutionDrawer = false;

  private pollSub?: Subscription;
  private routeSub?: Subscription;

  constructor(
    private readonly fb: FormBuilder,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly pipelineService: PipelineService,
    private readonly backtestService: BacktestService,
    private readonly snackBar: MatSnackBar,
    private readonly dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this.restoreExecutionDrawerWidth();

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

  @HostListener('document:keydown.escape')
  onEscapeKey(): void {
    this.closeExecutionDrawer();
  }

  @HostListener('document:mousemove', ['$event'])
  onDocumentMouseMove(event: MouseEvent): void {
    if (!this.draggingExecutionDrawer) {
      return;
    }

    const viewportWidth = window.innerWidth || 1440;
    const nextWidth = viewportWidth - event.clientX;
    const minWidth = 420;
    const maxWidth = Math.min(1100, Math.floor(viewportWidth * 0.92));
    this.executionDrawerWidth = Math.max(minWidth, Math.min(maxWidth, nextWidth));
    this.persistExecutionDrawerWidth();
  }

  @HostListener('document:mouseup')
  onDocumentMouseUp(): void {
    this.draggingExecutionDrawer = false;
    this.persistExecutionDrawerWidth();
  }

  get canLaunch(): boolean {
    return this.form.valid && !this.launching && !this.formHasDateError;
  }

  get formHasDateError(): boolean {
    const start = this.form.controls.startDate.value;
    const end = this.form.controls.endDate.value;
    return !!(start && end && start.getTime() > end.getTime());
  }

  get estimatedCostUsd(): number {
    const start = this.form.controls.startDate.value;
    const end = this.form.controls.endDate.value;
    const symbols = this.parseSymbols(this.form.controls.symbolsText.value ?? '');
    if (!start || !end || symbols.length === 0) {
      return 0;
    }
    const days = Math.max(1, Math.round((end.getTime() - start.getTime()) / 86400000));
    const estimatedExecutions = symbols.length * Math.max(1, Math.round((days / 30) * 100));
    return Number((estimatedExecutions * 0.075).toFixed(2));
  }

  get equityChartPath(): string {
    const series = this.selectedRun?.equity_series || [];
    if (series.length < 2) {
      return '';
    }
    const values = series.map(point => Number(point.equity));
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
    if (!this.equityChartPath || !(this.selectedRun?.equity_series?.length)) {
      return '';
    }
    const width = 720;
    const height = 220;
    return `${this.equityChartPath} L${width},${height} L0,${height} Z`;
  }

  get latestVisibleEvents(): BacktestTimelineEvent[] {
    return this.selectedTimeline.slice(0, 60);
  }

  get executionSymbols(): string[] {
    return Array.from(
      new Set(
        this.selectedExecutions
          .map(execution => String(execution.symbol || '').trim())
          .filter(Boolean),
      ),
    ).sort();
  }

  get filteredExecutions(): BacktestExecutionSummary[] {
    return this.selectedExecutions.filter(execution => {
      if (this.executionSymbolFilter !== 'all' && execution.symbol !== this.executionSymbolFilter) {
        return false;
      }

      const strategyDecision = this.executionStrategyDecision(execution).toUpperCase();
      const reviewDecision = this.executionReviewDecision(execution).toUpperCase();

      if (this.executionDecisionFilter !== 'all') {
        const filterValue = this.executionDecisionFilter.toUpperCase();
        if (strategyDecision !== filterValue && reviewDecision !== filterValue) {
          return false;
        }
      }

      const filter = this.executionFilter;
      if (filter === 'all') {
        return true;
      }

      const tradeStatus = this.executionTradeStatus(execution).toLowerCase();
      const hasOpenPosition = this.getOpenPositionForExecution(execution) !== null;
      const hasRealizedPnl = this.getClosedTradeForExecution(execution) !== null;
      const hasAnyPnl = this.hasExecutionPnl(execution);
      const isApproved = reviewDecision === 'APPROVED';
      const isRejected = reviewDecision === 'REJECTED';
      const isHold = strategyDecision === 'HOLD';

      switch (filter) {
        case 'filled':
          return tradeStatus === 'filled';
        case 'open':
          return hasOpenPosition;
        case 'closed':
          return hasRealizedPnl;
        case 'with_pnl':
          return hasAnyPnl;
        case 'approved':
          return isApproved;
        case 'rejected':
          return isRejected;
        case 'hold':
          return isHold;
        default:
          return true;
      }
    });
  }

  get hasDailyPnl(): boolean {
    return (this.selectedRun?.daily_pnl?.length || 0) > 0;
  }

  get activeRunCount(): number {
    return this.runs.filter(run => this.isActive(run.status)).length;
  }

  get selectedSymbolsLabel(): string {
    const symbols = this.selectedRun?.config?.['symbols'];
    return Array.isArray(symbols) && symbols.length > 0 ? symbols.join(', ') : 'No symbols';
  }

  get virtualSpeedMultiplier(): string {
    if (!this.selectedRun) {
      return '—';
    }

    const currentTsRaw = this.selectedRun.progress?.['current_ts'];
    const startDateRaw = this.selectedRun.config?.['start_date'];
    const runtimeSeconds = Number(this.selectedRun.metrics?.['runtime']?.['runtime_seconds'] || 0);

    if (!currentTsRaw || !startDateRaw || runtimeSeconds <= 0) {
      return '—';
    }

    const currentTs = new Date(String(currentTsRaw)).getTime();
    const startTs = new Date(`${String(startDateRaw)}T00:00:00Z`).getTime();
    if (!Number.isFinite(currentTs) || !Number.isFinite(startTs) || currentTs <= startTs) {
      return '—';
    }

    const simulatedSeconds = (currentTs - startTs) / 1000;
    if (simulatedSeconds <= 0) {
      return '—';
    }

    const multiplier = simulatedSeconds / runtimeSeconds;
    if (!Number.isFinite(multiplier) || multiplier <= 0) {
      return '—';
    }

    if (multiplier >= 100) {
      return `${Math.round(multiplier)}x`;
    }
    if (multiplier >= 10) {
      return `${multiplier.toFixed(1)}x`;
    }
    return `${multiplier.toFixed(2)}x`;
  }

  loadWorkspace(): void {
    this.loadPipelines();
    this.loadRuns(true);
  }

  openLaunchDialog(): void {
    const pipeline = this.resolveLaunchPipeline();
    if (!pipeline) {
      this.toast('Load a pipeline before starting a backtest', 'error');
      return;
    }

    const dialogRef = this.dialog.open(BacktestLaunchDialogComponent, {
      width: '1080px',
      maxWidth: '96vw',
      panelClass: 'backtest-launch-overlay',
      data: { pipeline },
    });

    dialogRef.afterClosed().subscribe((result?: { runId?: string }) => {
      if (result?.runId) {
        this.selectedPipelineId = pipeline.id;
        this.router.navigate(['/backtests', result.runId], {
          queryParams: { pipelineId: pipeline.id },
        });
        return;
      }

      this.loadRuns(false);
    });
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
        const allRuns = response.backtests || [];
        const pipelineId = this.activePipelineId();
        this.runs = pipelineId
          ? allRuns.filter(run => run.pipeline_id === pipelineId)
          : allRuns;
        if (this.selectedRunId) {
          this.loadSelectedRun(this.selectedRunId, false);
        } else if (this.runs.length > 0) {
          this.selectRun(this.runs[0].id, false);
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
    const run = this.runs.find(item => item.id === runId);
    if (run?.pipeline_id) {
      this.selectedPipelineId = run.pipeline_id;
      this.form.patchValue({ pipelineId: run.pipeline_id }, { emitEvent: false });
    }
    if (navigate) {
      this.router.navigate(['/backtests', runId], {
        queryParams: {
          pipelineId: run?.pipeline_id || this.selectedPipelineId || this.form.controls.pipelineId.value || null,
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
        if (run.pipeline_id && run.pipeline_id !== this.selectedPipelineId) {
          this.selectedPipelineId = run.pipeline_id;
          this.form.patchValue({ pipelineId: run.pipeline_id }, { emitEvent: false });
          this.seedFormFromPipeline(run.pipeline_id);
          this.loadRuns(false);
        }
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
        this.selectedExecution = this.filteredExecutions[0] || this.selectedExecutions[0] || null;
      },
      error: () => {
        this.selectedExecutions = [];
        this.selectedExecution = null;
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
      start_date: this.formatDateForApi(this.form.controls.startDate.value),
      end_date: this.formatDateForApi(this.form.controls.endDate.value),
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
    const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const start = new Date(end.getTime() - 14 * 86400000);
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
      ['Closed Trades', this.selectedRun?.trades_count ?? 0],
      ['Filled Orders', this.selectedRun?.filled_orders_count ?? 0],
      ['Open Positions', this.selectedRun?.open_positions_count ?? 0],
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
    return this.executionStrategyDecision(execution);
  }

  executionStrategyDecision(execution: BacktestExecutionSummary): string {
    const strategy = execution.result?.['strategy'] || {};
    return String(strategy['action'] || 'N/A');
  }

  executionReviewDecision(execution: BacktestExecutionSummary): string {
    const review = execution.reports?.['node-trade_review_agent']?.['data'] || {};
    const resultReview = execution.result?.['trade_review'] || {};
    return String(review['decision'] || resultReview['decision'] || '—');
  }

  executionVirtualTs(execution: BacktestExecutionSummary): string {
    return (
      execution.result?.['backtest_ts'] ||
      execution.result?.['trade_execution']?.['execution_time'] ||
      execution.created_at
    );
  }

  executionTradeStatus(execution: BacktestExecutionSummary): string {
    const status = execution.result?.['trade_execution']?.['status'];
    return status ? String(status).toUpperCase() : '—';
  }

  executionFilledPrice(execution: BacktestExecutionSummary): string {
    const value = execution.result?.['trade_execution']?.['filled_price'];
    return value === null || value === undefined || value === '' ? '—' : String(value);
  }

  executionFilledQuantity(execution: BacktestExecutionSummary): string {
    const value = execution.result?.['trade_execution']?.['filled_quantity'];
    return value === null || value === undefined || value === '' ? '—' : String(value);
  }

  biasReasoning(execution: BacktestExecutionSummary | null): string {
    return (
      execution?.reports?.['node-bias_agent']?.['summary'] ||
      execution?.reports?.['node-bias_agent']?.['data']?.['Detailed Analysis'] ||
      execution?.result?.['bias']?.['reasoning'] ||
      'No bias analysis recorded.'
    );
  }

  executionPnl(execution: BacktestExecutionSummary): string {
    const openPosition = this.getOpenPositionForExecution(execution);
    if (openPosition) {
      const unrealized = openPosition['unrealized_pnl'];
      if (unrealized !== null && unrealized !== undefined) {
        return `${Number(unrealized).toFixed(2)} (open)`;
      }
      return 'Open';
    }

    const closedTrade = this.getClosedTradeForExecution(execution);
    if (closedTrade) {
      const netPnl = closedTrade['net_pnl'];
      return netPnl === null || netPnl === undefined ? '—' : Number(netPnl).toFixed(2);
    }

    return '—';
  }

  private getOpenPositionForExecution(execution: BacktestExecutionSummary): Record<string, unknown> | null {
    return (
      (this.selectedRun?.open_positions || []).find(
        position => position['execution_id'] === execution.id
      ) || null
    );
  }

  private getClosedTradeForExecution(execution: BacktestExecutionSummary): Record<string, unknown> | null {
    return (
      (this.selectedRun?.trades || []).find(
        trade => trade['execution_id'] === execution.id
      ) || null
    );
  }

  private hasExecutionPnl(execution: BacktestExecutionSummary): boolean {
    const openPosition = this.getOpenPositionForExecution(execution);
    if (openPosition && openPosition['unrealized_pnl'] !== null && openPosition['unrealized_pnl'] !== undefined) {
      return true;
    }

    const closedTrade = this.getClosedTradeForExecution(execution);
    return !!(closedTrade && closedTrade['net_pnl'] !== null && closedTrade['net_pnl'] !== undefined);
  }

  selectExecution(execution: BacktestExecutionSummary): void {
    this.selectedExecution = execution;
    this.draggingExecutionDrawer = false;
  }

  setExecutionFilter(filter: string): void {
    this.executionFilter = filter;
    if (this.selectedExecution && !this.filteredExecutions.some(item => item.id === this.selectedExecution?.id)) {
      this.selectedExecution = this.filteredExecutions[0] || null;
    }
  }

  onExecutionSelectorChanged(): void {
    if (this.selectedExecution && !this.filteredExecutions.some(item => item.id === this.selectedExecution?.id)) {
      this.selectedExecution = this.filteredExecutions[0] || null;
    }
  }

  closeExecutionDrawer(): void {
    this.selectedExecution = null;
    this.draggingExecutionDrawer = false;
  }

  startExecutionDrawerResize(event: MouseEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.draggingExecutionDrawer = true;
  }

  strategyReasoning(execution: BacktestExecutionSummary | null): string {
    return execution?.result?.['strategy']?.['reasoning'] || 'No strategy reasoning recorded.';
  }

  riskReasoning(execution: BacktestExecutionSummary | null): string {
    return execution?.result?.['risk_assessment']?.['reasoning'] || 'No risk reasoning recorded.';
  }

  reviewReasoning(execution: BacktestExecutionSummary | null): string {
    return (
      execution?.result?.['trade_review']?.['reasoning'] ||
      execution?.reports?.['node-trade_review_agent']?.['summary'] ||
      'No trade review reasoning recorded.'
    );
  }

  biasDetails(execution: BacktestExecutionSummary | null): Array<{ label: string; value: string }> {
    const reportData = execution?.reports?.['node-bias_agent']?.['data'] || {};
    const entries = [
      ['Bias', reportData['Market Bias'] || execution?.result?.['bias']?.['market_bias']],
      ['Confidence', reportData['Confidence Level'] || execution?.result?.['bias']?.['confidence']],
      ['Timeframe', reportData['Analyzed Timeframe']],
      ['Key Factors', reportData['Key Market Factors']],
    ];
    return entries
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([label, value]) => ({ label: String(label), value: String(value) }));
  }

  strategyDetails(execution: BacktestExecutionSummary | null): Array<{ label: string; value: string }> {
    const strategy = execution?.result?.['strategy'] || {};
    const entries = [
      ['Action', strategy['action']],
      ['Confidence', strategy['confidence']],
      ['Pattern', strategy['pattern_detected']],
      ['Entry Price', strategy['entry_price']],
      ['Stop Loss', strategy['stop_loss']],
      ['Take Profit', strategy['take_profit']],
      ['Position Size', strategy['position_size']],
    ];
    return entries
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([label, value]) => ({ label: String(label), value: String(value) }));
  }

  riskDetails(execution: BacktestExecutionSummary | null): Array<{ label: string; value: string }> {
    const risk = execution?.result?.['risk_assessment'] || {};
    const entries = [
      ['Approved', risk['approved']],
      ['Position Size', risk['position_size']],
      ['Max Loss', risk['max_loss']],
      ['Risk / Reward', risk['risk_reward_ratio']],
      ['Portfolio Exposure', risk['total_exposure_pct']],
    ];
    return entries
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([label, value]) => ({ label: String(label), value: String(value) }));
  }

  reviewDetails(execution: BacktestExecutionSummary | null): Array<{ label: string; value: string }> {
    const review = execution?.result?.['trade_review'] || execution?.reports?.['node-trade_review_agent']?.['data'] || {};
    const entries = [
      ['Decision', review['decision']],
      ['Confidence', review['confidence']],
      ['Risk / Reward', review['risk_reward_ratio']],
      ['Approval', review['approved']],
    ];
    return entries
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([label, value]) => ({ label: String(label), value: String(value) }));
  }

  outcomeDetails(execution: BacktestExecutionSummary | null): Array<{ label: string; value: string }> {
    if (!execution) {
      return [];
    }
    const openPosition = (this.selectedRun?.open_positions || []).find(
      position => position['execution_id'] === execution.id
    );
    const closedTrade = (this.selectedRun?.trades || []).find(
      trade => trade['execution_id'] === execution.id
    );
    const tradeExecution = execution.result?.['trade_execution'] || {};
    const entries = [
      ['Trade Status', tradeExecution['status'] || this.executionTradeStatus(execution)],
      ['Filled Price', tradeExecution['filled_price']],
      ['Filled Quantity', tradeExecution['filled_quantity']],
      ['P&L', this.executionPnl(execution)],
      ['Open Position', openPosition ? 'Yes' : 'No'],
      ['Unrealized P&L', openPosition?.['unrealized_pnl']],
      ['Realized P&L', closedTrade?.['net_pnl']],
      ['Commission', tradeExecution['commission']],
      ['Trade ID', tradeExecution['trade_id']],
      ['Order ID', tradeExecution['order_id']],
      ['Execution Time', tradeExecution['execution_time']],
    ];
    return entries
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([label, value]) => ({ label: String(label), value: String(value) }));
  }

  tradeExecutionDetails(execution: BacktestExecutionSummary | null): Array<{ label: string; value: string }> {
    const tradeExecution = execution?.result?.['trade_execution'] || {};
    const entries = [
      ['Trade Status', tradeExecution['status']],
      ['Filled Price', tradeExecution['filled_price']],
      ['Filled Quantity', tradeExecution['filled_quantity']],
      ['Trade ID', tradeExecution['trade_id']],
      ['Order ID', tradeExecution['order_id']],
      ['Commission', tradeExecution['commission']],
      ['Execution Time', tradeExecution['execution_time']],
      ['Broker Reason', tradeExecution?.['broker_response']?.['reason']],
    ];
    return entries
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([label, value]) => ({ label: String(label), value: String(value) }));
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

  private resolveLaunchPipeline(): Pipeline | undefined {
    const preferredPipelineId =
      this.selectedRun?.pipeline_id ||
      this.selectedPipelineId ||
      this.form.controls.pipelineId.value ||
      this.pipelines[0]?.id;

    return this.pipelines.find(pipeline => pipeline.id === preferredPipelineId) || this.pipelines[0];
  }

  private activePipelineId(): string | null {
    return (
      this.selectedPipelineId ||
      this.selectedRun?.pipeline_id ||
      this.form.controls.pipelineId.value ||
      null
    );
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

  private toast(message: string, panelClass: 'success' | 'error'): void {
    this.snackBar.open(message, 'Dismiss', {
      duration: 3200,
      panelClass: [`toast-${panelClass}`],
    });
  }

  private restoreExecutionDrawerWidth(): void {
    if (typeof window === 'undefined') {
      return;
    }

    const stored = window.localStorage.getItem(BacktestsPageComponent.EXECUTION_DRAWER_WIDTH_KEY);
    if (!stored) {
      return;
    }

    const parsed = Number(stored);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return;
    }

    const viewportWidth = window.innerWidth || 1440;
    const minWidth = 420;
    const maxWidth = Math.min(1100, Math.floor(viewportWidth * 0.92));
    this.executionDrawerWidth = Math.max(minWidth, Math.min(maxWidth, parsed));
  }

  private persistExecutionDrawerWidth(): void {
    if (typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(
      BacktestsPageComponent.EXECUTION_DRAWER_WIDTH_KEY,
      String(Math.round(this.executionDrawerWidth)),
    );
  }
}
