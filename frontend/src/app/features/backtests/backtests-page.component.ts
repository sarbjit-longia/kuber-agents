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
import { Subscription, combineLatest, interval } from 'rxjs';

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
  private static readonly SELECTED_PIPELINE_KEY = 'backtests.selectedPipelineId';
  private static readonly EQUITY_CHART = {
    width: 720,
    height: 260,
    leftPad: 60,
    rightPad: 18,
    topPad: 18,
    bottomPad: 34,
  };
  private static readonly DAILY_PNL_CHART = {
    width: 720,
    height: 260,
    leftPad: 56,
    rightPad: 18,
    topPad: 18,
    bottomPad: 34,
  };
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
  allRuns: BacktestRunSummary[] = [];
  runs: BacktestRunSummary[] = [];
  selectedRun: BacktestRunResult | null = null;
  selectedRunSummary: BacktestRunSummary | null = null;
  selectedExecutions: BacktestExecutionSummary[] = [];
  selectedExecution: BacktestExecutionSummary | null = null;
  selectedTimeline: BacktestTimelineEvent[] = [];
  selectedReport: BacktestReportResponse | null = null;
  selectedReportRunId: string | null = null;
  selectedRunId: string | null = null;
  selectedPipelineId: string | null = null;
  launcherPipelineId: string | null = null;
  reportState: 'idle' | 'loading' | 'ready' | 'error' = 'idle';
  reportErrorMessage = '';
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

    this.routeSub = combineLatest([this.route.paramMap, this.route.queryParamMap]).subscribe(([params, queryParams]) => {
      this.selectedRunId = params.get('id');
      const scopedPipelineId = queryParams.get('pipelineId');
      const restoredLaunchPipelineId = scopedPipelineId || this.restoreSelectedPipelineId();
      this.selectedPipelineId = scopedPipelineId;
      this.launcherPipelineId = restoredLaunchPipelineId;
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

  get equityChartModel(): {
    viewBox: string;
    linePath: string;
    positiveAreaPath: string;
    negativeAreaPath: string;
    baselineY: number;
    baselineLabel: string;
    xTicks: Array<{ x: number; label: string }>;
    yTicks: Array<{ y: number; label: string }>;
  } | null {
    const series = this.selectedRun?.equity_series || [];
    if (!series.length) {
      return null;
    }

    const dims = BacktestsPageComponent.EQUITY_CHART;
    const points = series
      .map((point: Record<string, unknown>, index) => {
        const ts = String(point['ts'] || point['date'] || '');
        const equity = Number(point['equity']);
        return Number.isFinite(equity)
          ? { index, ts, equity }
          : null;
      })
      .filter((point): point is { index: number; ts: string; equity: number } => point !== null);

    if (points.length < 2) {
      return null;
    }

    const baseline = Number(this.selectedRun?.config?.['initial_capital'] || points[0].equity || 0);
    const values = points.map(point => point.equity).concat(baseline);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max(Math.abs(max - min) * 0.12, baseline * 0.003, 25);
    const domainMin = Math.min(min, baseline) - padding;
    const domainMax = Math.max(max, baseline) + padding;
    const plotWidth = dims.width - dims.leftPad - dims.rightPad;
    const plotHeight = dims.height - dims.topPad - dims.bottomPad;
    const valueRange = Math.max(domainMax - domainMin, 1);
    const scaleX = (index: number) => dims.leftPad + (index / Math.max(points.length - 1, 1)) * plotWidth;
    const scaleY = (value: number) => dims.topPad + (domainMax - value) / valueRange * plotHeight;
    const baselineY = scaleY(baseline);

    const chartPoints = points.map(point => ({
      ...point,
      x: scaleX(point.index),
      y: scaleY(point.equity),
    }));

    return {
      viewBox: `0 0 ${dims.width} ${dims.height}`,
      linePath: chartPoints.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' '),
      positiveAreaPath: this.buildSignedAreaPath(chartPoints, baseline, 'positive'),
      negativeAreaPath: this.buildSignedAreaPath(chartPoints, baseline, 'negative'),
      baselineY,
      baselineLabel: this.formatCurrencyLabel(baseline),
      xTicks: this.buildEquityXTicks(chartPoints),
      yTicks: this.buildEquityYTicks(domainMin, baseline, domainMax, scaleY),
    };
  }

  get latestVisibleEvents(): BacktestTimelineEvent[] {
    return this.selectedTimeline.slice(0, 60);
  }

  get dailyPnlChartModel(): {
    viewBox: string;
    baselineY: number;
    bars: Array<{ date: string; pnl: number; x: number; y: number; width: number; height: number; positive: boolean }>;
    xTicks: Array<{ x: number; label: string }>;
    yTicks: Array<{ y: number; label: string }>;
  } | null {
    const rows = this.selectedRun?.daily_pnl || [];
    if (!rows.length) {
      return null;
    }

    const dims = BacktestsPageComponent.DAILY_PNL_CHART;
    const maxAbs = Math.max(...rows.map(item => Math.abs(Number(item.pnl) || 0)), 1);
    const plotWidth = dims.width - dims.leftPad - dims.rightPad;
    const plotHeight = dims.height - dims.topPad - dims.bottomPad;
    const baselineY = dims.topPad + plotHeight / 2;
    const step = plotWidth / Math.max(rows.length, 1);
    const barWidth = Math.max(14, Math.min(44, step * 0.64));
    const yScale = (Math.abs(plotHeight / 2 - 8)) / maxAbs;

    const bars = rows.map((item, index) => {
      const pnl = Number(item.pnl) || 0;
      const scaled = Math.max(Math.abs(pnl) * yScale, 2);
      const x = dims.leftPad + index * step + (step - barWidth) / 2;
      const positive = pnl >= 0;
      const y = positive ? baselineY - scaled : baselineY;
      return {
        date: item.date,
        pnl,
        x,
        y,
        width: barWidth,
        height: scaled,
        positive,
      };
    });

    return {
      viewBox: `0 0 ${dims.width} ${dims.height}`,
      baselineY,
      bars,
      xTicks: bars.map(bar => ({
        x: bar.x + bar.width / 2,
        label: this.formatChartDate(bar.date),
      })),
      yTicks: [
        { y: dims.topPad, label: this.formatCurrencyLabel(maxAbs) },
        { y: baselineY, label: '$0' },
        { y: dims.topPad + plotHeight, label: this.formatCurrencyLabel(-maxAbs) },
      ],
    };
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
    return this.allRuns.filter(run => this.isActive(run.status)).length;
  }

  get completedRunCount(): number {
    return this.allRuns.filter(run => run.status === 'COMPLETED').length;
  }

  get failedRunCount(): number {
    return this.allRuns.filter(run => run.status === 'FAILED').length;
  }

  get totalBacktestCost(): number {
    return this.allRuns.reduce((sum, run) => sum + Number(run.actual_cost || 0), 0);
  }

  get totalFilledOrders(): number {
    return this.allRuns.reduce((sum, run) => sum + Number(run.filled_orders_count || 0), 0);
  }

  get pipelineLaunchCards(): Array<{
    pipeline: Pipeline;
    runCount: number;
    activeCount: number;
    filledOrders: number;
    totalCost: number;
    latestRun: BacktestRunSummary | null;
    symbolsLabel: string;
  }> {
    return this.pipelines.map(pipeline => {
      const pipelineRuns = this.allRuns.filter(run => run.pipeline_id === pipeline.id);
      return {
        pipeline,
        runCount: pipelineRuns.length,
        activeCount: pipelineRuns.filter(run => this.isActive(run.status)).length,
        filledOrders: pipelineRuns.reduce((sum, run) => sum + Number(run.filled_orders_count || 0), 0),
        totalCost: pipelineRuns.reduce((sum, run) => sum + Number(run.actual_cost || 0), 0),
        latestRun: pipelineRuns[0] || null,
        symbolsLabel: this.defaultSymbolsForPipeline(pipeline).join(', ') || 'No default symbols',
      };
    });
  }

  get selectedLaunchCard():
    | {
        pipeline: Pipeline;
        runCount: number;
        activeCount: number;
        filledOrders: number;
        totalCost: number;
        latestRun: BacktestRunSummary | null;
        symbolsLabel: string;
      }
    | null {
    return this.pipelineLaunchCards.find(item => item.pipeline.id === this.selectedLaunchPipelineId) || null;
  }

  get selectedWorkspaceCard():
    | {
        pipeline: Pipeline;
        runCount: number;
        activeCount: number;
        filledOrders: number;
        totalCost: number;
        latestRun: BacktestRunSummary | null;
        symbolsLabel: string;
      }
    | null {
    if (!this.selectedPipelineId) {
      return null;
    }
    return this.pipelineLaunchCards.find(item => item.pipeline.id === this.selectedPipelineId) || null;
  }

  get pipelineCostChartModel():
    | {
        viewBox: string;
        bars: Array<{ x: number; y: number; width: number; height: number; label: string; valueLabel: string; selected: boolean }>;
      }
    | null {
    const rows = this.pipelineLaunchCards.filter(item => item.totalCost > 0);
    if (!rows.length) {
      return null;
    }

    const width = 720;
    const height = 240;
    const left = 28;
    const right = 20;
    const top = 18;
    const bottom = 44;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const maxValue = Math.max(...rows.map(item => item.totalCost), 1);
    const step = plotWidth / rows.length;
    const barWidth = Math.min(72, Math.max(28, step * 0.58));

    return {
      viewBox: `0 0 ${width} ${height}`,
      bars: rows.map((item, index) => {
        const heightValue = (item.totalCost / maxValue) * (plotHeight - 10);
        const x = left + index * step + (step - barWidth) / 2;
        const y = top + (plotHeight - heightValue);
        return {
          x,
          y,
          width: barWidth,
          height: Math.max(heightValue, 8),
          label: item.pipeline.name,
          valueLabel: `$${item.totalCost.toFixed(2)}`,
          selected: item.pipeline.id === this.selectedLaunchPipelineId,
        };
      }),
    };
  }

  get pipelineOrdersChartModel():
    | {
        viewBox: string;
        bars: Array<{ x: number; y: number; width: number; height: number; label: string; valueLabel: string; selected: boolean }>;
      }
    | null {
    const rows = this.pipelineLaunchCards.filter(item => item.runCount > 0 || item.filledOrders > 0);
    if (!rows.length) {
      return null;
    }

    const width = 720;
    const height = 240;
    const left = 28;
    const right = 20;
    const top = 18;
    const bottom = 44;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const maxValue = Math.max(...rows.map(item => item.filledOrders), 1);
    const step = plotWidth / rows.length;
    const barWidth = Math.min(72, Math.max(28, step * 0.58));

    return {
      viewBox: `0 0 ${width} ${height}`,
      bars: rows.map((item, index) => {
        const heightValue = (item.filledOrders / maxValue) * (plotHeight - 10);
        const x = left + index * step + (step - barWidth) / 2;
        const y = top + (plotHeight - heightValue);
        return {
          x,
          y,
          width: barWidth,
          height: Math.max(heightValue, 8),
          label: item.pipeline.name,
          valueLabel: `${item.filledOrders}`,
          selected: item.pipeline.id === this.selectedLaunchPipelineId,
        };
      }),
    };
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
    const endDateRaw = this.selectedRun.config?.['end_date'];
    const persistedRuntimeSeconds = Number(this.selectedRun.metrics?.['runtime']?.['runtime_seconds'] || 0);

    if (!startDateRaw) {
      return '—';
    }

    const startTs = this.parseBacktestDate(startDateRaw, false);
    let currentTs = currentTsRaw ? new Date(String(currentTsRaw)).getTime() : NaN;

    if ((!Number.isFinite(currentTs) || currentTs <= startTs) && endDateRaw) {
      const endTs = this.parseBacktestDate(endDateRaw, true);
      const currentBar = Number(this.selectedRun.progress?.['current_bar'] || 0);
      const totalBars = Number(this.selectedRun.progress?.['total_bars'] || 0);
      if (Number.isFinite(endTs) && endTs > startTs && totalBars > 0 && currentBar >= 0) {
        const progressRatio = Math.max(0, Math.min(1, currentBar / totalBars));
        currentTs = startTs + (endTs - startTs) * progressRatio;
      }
    }

    if (!Number.isFinite(currentTs) || !Number.isFinite(startTs) || currentTs <= startTs) {
      return '—';
    }

    const simulatedSeconds = (currentTs - startTs) / 1000;
    if (simulatedSeconds <= 0) {
      return '—';
    }

    let runtimeSeconds = persistedRuntimeSeconds;
    if (runtimeSeconds <= 0) {
      const runtimeStartRaw = this.selectedRun.started_at || this.selectedRun.created_at;
      const startedAt = new Date(String(runtimeStartRaw)).getTime();
      const nowTs = Date.now();
      if (Number.isFinite(startedAt) && nowTs > startedAt) {
        runtimeSeconds = (nowTs - startedAt) / 1000;
      }
    }

    if (runtimeSeconds <= 0) {
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

  private parseBacktestDate(value: unknown, endOfDay: boolean): number {
    if (!value) {
      return Number.NaN;
    }

    if (value instanceof Date) {
      return value.getTime();
    }

    const text = String(value);
    const suffix = endOfDay ? 'T23:59:59Z' : 'T00:00:00Z';
    return new Date(text.includes('T') ? text : `${text}${suffix}`).getTime();
  }

  loadWorkspace(): void {
    this.loadPipelines();
    this.loadRuns(true);
  }

  get selectedLaunchPipelineId(): string | null {
    return (
      this.form.controls.pipelineId.value ||
      this.launcherPipelineId ||
      null
    );
  }

  get selectedLaunchPipeline(): Pipeline | undefined {
    const explicitPipelineId = this.selectedLaunchPipelineId;
    if (!explicitPipelineId) {
      return undefined;
    }
    return this.pipelines.find(pipeline => pipeline.id === explicitPipelineId);
  }

  get selectedLaunchPipelineName(): string {
    return this.selectedLaunchPipeline?.name || 'No pipeline selected';
  }

  openLaunchDialog(pipelineId?: string): void {
    const pipeline = this.resolveLaunchPipeline(!pipelineId, pipelineId);
    if (!pipeline) {
      this.toast('Select a pipeline before starting a backtest', 'error');
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
        this.launcherPipelineId = pipeline.id;
        this.router.navigate(['/backtests/workspace', result.runId], {
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
        const pipelineId = this.launcherPipelineId || this.form.controls.pipelineId.value || pipelines[0]?.id || '';
        this.launcherPipelineId = pipelineId || null;
        this.form.patchValue({ pipelineId }, { emitEvent: false });
        if (pipelineId) {
          this.seedFormFromPipeline(pipelineId);
        }
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
        this.allRuns = allRuns;
        const pipelineId = this.activePipelineId();
        this.runs = pipelineId
          ? allRuns.filter(run => run.pipeline_id === pipelineId)
          : allRuns;
        if (this.selectedRunId) {
          this.loadSelectedRun(this.selectedRunId, false);
        } else {
          this.selectedRun = null;
          this.selectedRunSummary = null;
          this.selectedExecutions = [];
          this.selectedExecution = null;
          this.selectedTimeline = [];
          this.selectedReport = null;
          this.selectedReportRunId = null;
          this.reportState = 'idle';
          this.reportErrorMessage = '';
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
      this.launcherPipelineId = run.pipeline_id;
      this.persistSelectedPipelineId(run.pipeline_id);
      this.form.patchValue({ pipelineId: run.pipeline_id }, { emitEvent: false });
    }
    if (navigate) {
      this.router.navigate(['/backtests/workspace', runId], {
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
    if (this.selectedReportRunId !== runId) {
      this.reportState = 'loading';
      this.reportErrorMessage = '';
    }
    this.backtestService.getBacktestResults(runId).subscribe({
      next: (run) => {
        if (this.selectedRunId !== runId) {
          return;
        }
        this.selectedRun = run;
        this.selectedRunSummary = run;
        if (run.pipeline_id && run.pipeline_id !== this.selectedPipelineId) {
          this.selectedPipelineId = run.pipeline_id;
          this.launcherPipelineId = run.pipeline_id;
          this.persistSelectedPipelineId(run.pipeline_id);
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
        if (this.selectedExecution) {
          this.selectedExecution =
            this.selectedExecutions.find(execution => execution.id === this.selectedExecution?.id) || null;
        } else {
          this.selectedExecution = null;
        }
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
    if (this.selectedReportRunId === runId && this.selectedReport) {
      this.reportState = 'ready';
      return;
    }
    this.reportState = 'loading';
    this.reportErrorMessage = '';
    this.backtestService.getBacktestReport(runId).subscribe({
      next: (report) => {
        if (this.selectedRunId !== runId) {
          return;
        }
        this.selectedReport = report;
        this.selectedReportRunId = runId;
        this.reportState = 'ready';
      },
      error: () => {
        if (this.selectedRunId !== runId) {
          return;
        }
        if (this.selectedReportRunId === runId && this.selectedReport) {
          this.reportState = 'ready';
          return;
        }
        this.selectedReport = null;
        this.selectedReportRunId = null;
        this.reportState = 'error';
        this.reportErrorMessage = 'Report could not be loaded right now. Refresh and try again.';
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
        this.router.navigate(['/backtests/workspace', response.run_id], {
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
    this.launcherPipelineId = pipelineId;
    this.persistSelectedPipelineId(pipelineId);
    this.seedFormFromPipeline(pipelineId);
  }

  openPipelineBacktests(pipelineId: string): void {
    this.launcherPipelineId = pipelineId;
    this.selectedPipelineId = pipelineId;
    this.persistSelectedPipelineId(pipelineId);
    this.form.patchValue({ pipelineId }, { emitEvent: false });
    this.seedFormFromPipeline(pipelineId);
    this.selectedRunId = null;
    this.selectedRun = null;
    this.selectedRunSummary = null;
    this.selectedExecutions = [];
    this.selectedExecution = null;
    this.selectedTimeline = [];
    this.selectedReport = null;
    this.selectedReportRunId = null;
    this.reportState = 'idle';
    this.reportErrorMessage = '';
    this.router.navigate(['/backtests/workspace'], { queryParams: { pipelineId } });
  }

  selectPipelineForBacktests(pipelineId: string): void {
    this.openPipelineBacktests(pipelineId);
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

  reportSummaryEntries(): Array<{ key: string; label: string; value: string }> {
    const summary = this.selectedReport?.summary || {};
    const preferredOrder = [
      'status',
      'date_range',
      'symbols',
      'timeframe',
      'trade_count',
      'winning_trades',
      'losing_trades',
      'win_rate',
      'net_pnl',
      'gross_pnl',
      'return_pct',
      'actual_cost',
      'execution_count',
      'matched_signal_batches',
      'review_rejections',
      'strategy_holds',
      'runtime_seconds',
      'max_drawdown',
    ];

    const keys = preferredOrder.filter(key => key in summary);
    return keys.map(key => ({
      key,
      label: this.formatReportLabel(key),
      value: this.formatReportValue(key, summary[key]),
    }));
  }

  reportVisualMetrics(): Array<{ label: string; value: string; tone?: 'positive' | 'negative' | 'neutral' }> {
    const summary = this.selectedReport?.summary || {};
    const metrics = [
      {
        label: 'Net P&L',
        value: this.formatReportValue('net_pnl', summary['net_pnl']),
        tone: Number(summary['net_pnl'] || 0) > 0 ? 'positive' as const : Number(summary['net_pnl'] || 0) < 0 ? 'negative' as const : 'neutral' as const,
      },
      {
        label: 'Win Rate',
        value: this.formatReportValue('win_rate', summary['win_rate']),
        tone: 'neutral' as const,
      },
      {
        label: 'Executions',
        value: this.formatReportValue('execution_count', summary['execution_count']),
        tone: 'neutral' as const,
      },
      {
        label: 'Review Rejections',
        value: this.formatReportValue('review_rejections', summary['review_rejections']),
        tone: 'neutral' as const,
      },
    ];
    return metrics;
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
    return this.formatDisplayNumber(value);
  }

  executionFilledQuantity(execution: BacktestExecutionSummary): string {
    const value = execution.result?.['trade_execution']?.['filled_quantity'];
    return this.formatDisplayNumber(value);
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

  executionPnlValue(execution: BacktestExecutionSummary | null): number | null {
    if (!execution) {
      return null;
    }

    const openPosition = this.getOpenPositionForExecution(execution);
    if (openPosition) {
      const unrealized = openPosition['unrealized_pnl'];
      return unrealized === null || unrealized === undefined ? null : Number(unrealized);
    }

    const closedTrade = this.getClosedTradeForExecution(execution);
    if (closedTrade) {
      const netPnl = closedTrade['net_pnl'];
      return netPnl === null || netPnl === undefined ? null : Number(netPnl);
    }

    return null;
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
      ['Confidence', this.formatDisplayNumber(strategy['confidence'])],
      ['Pattern', strategy['pattern_detected']],
      ['Entry Price', this.formatDisplayNumber(strategy['entry_price'])],
      ['Stop Loss', this.formatDisplayNumber(strategy['stop_loss'])],
      ['Take Profit', this.formatDisplayNumber(strategy['take_profit'])],
      ['Position Size', this.formatDisplayNumber(strategy['position_size'])],
    ];
    return entries
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([label, value]) => ({ label: String(label), value: String(value) }));
  }

  riskDetails(execution: BacktestExecutionSummary | null): Array<{ label: string; value: string }> {
    const risk = execution?.result?.['risk_assessment'] || {};
    const entries = [
      ['Approved', risk['approved']],
      ['Position Size', this.formatDisplayNumber(risk['position_size'])],
      ['Max Loss', this.formatDisplayNumber(risk['max_loss'])],
      ['Risk / Reward', this.formatDisplayNumber(risk['risk_reward_ratio'])],
      ['Portfolio Exposure', this.formatDisplayNumber(risk['total_exposure_pct'])],
    ];
    return entries
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([label, value]) => ({ label: String(label), value: String(value) }));
  }

  reviewDetails(execution: BacktestExecutionSummary | null): Array<{ label: string; value: string }> {
    const review = execution?.result?.['trade_review'] || execution?.reports?.['node-trade_review_agent']?.['data'] || {};
    const entries = [
      ['Decision', review['decision']],
      ['Confidence', this.formatDisplayNumber(review['confidence'])],
      ['Risk / Reward', this.formatDisplayNumber(review['risk_reward_ratio'])],
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
      ['Filled Price', this.formatDisplayNumber(tradeExecution['filled_price'])],
      ['Filled Quantity', this.formatDisplayNumber(tradeExecution['filled_quantity'])],
      ['P&L', this.executionPnl(execution)],
      ['Open Position', openPosition ? 'Yes' : 'No'],
      ['Unrealized P&L', this.formatDisplayNumber(openPosition?.['unrealized_pnl'])],
      ['Realized P&L', this.formatDisplayNumber(closedTrade?.['net_pnl'])],
      ['Commission', this.formatDisplayNumber(tradeExecution['commission'])],
      ['Trade ID', tradeExecution['trade_id']],
      ['Order ID', tradeExecution['order_id']],
      ['Execution Time', this.formatTimestampDisplay(tradeExecution['execution_time'])],
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
      ['Execution Time', this.formatTimestampDisplay(tradeExecution['execution_time'])],
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
    if (!Array.isArray(values)) {
      return [];
    }

    return values
      .map(value => this.formatLlmValue(value))
      .filter((value): value is string => Boolean(value));
  }

  llmSummaryText(value: unknown): string {
    return this.formatLlmValue(value) || 'No executive summary returned.';
  }

  formatReportLabel(key: string): string {
    return key
      .split('_')
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  }

  formatReportValue(key: string, value: unknown): string {
    if (value === null || value === undefined || value === '') {
      return 'N/A';
    }

    if (key === 'date_range' && typeof value === 'object') {
      const start = (value as Record<string, unknown>)['start'];
      const end = (value as Record<string, unknown>)['end'];
      return `${start || 'N/A'} - ${end || 'N/A'}`;
    }

    if (Array.isArray(value)) {
      return value.join(', ');
    }

    if (key === 'symbols') {
      return Array.isArray(value) ? value.join(', ') : String(value);
    }

    if (['actual_cost', 'net_pnl', 'gross_pnl', 'max_drawdown'].includes(key)) {
      const formatted = this.formatDisplayNumber(value);
      return formatted === '—' ? 'N/A' : `$${formatted}`;
    }

    if (['win_rate', 'return_pct'].includes(key)) {
      const formatted = this.formatDisplayNumber(value);
      return formatted === '—' ? 'N/A' : `${formatted}%`;
    }

    if (key === 'runtime_seconds') {
      const formatted = this.formatDisplayNumber(value);
      return formatted === '—' ? 'N/A' : `${formatted}s`;
    }

    return this.formatDisplayNumber(value);
  }

  private buildEquityXTicks(points: Array<{ x: number; ts: string }>): Array<{ x: number; label: string }> {
    if (points.length <= 3) {
      return points.map(point => ({ x: point.x, label: this.formatChartDate(point.ts) }));
    }

    const indexes = Array.from(new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]));
    return indexes.map(index => ({
      x: points[index].x,
      label: this.formatChartDate(points[index].ts),
    }));
  }

  private buildEquityYTicks(min: number, baseline: number, max: number, scaleY: (value: number) => number): Array<{ y: number; label: string }> {
    const values = Array.from(new Set([max, baseline, min])).sort((a, b) => b - a);
    return values.map(value => ({
      y: scaleY(value),
      label: this.formatCurrencyLabel(value),
    }));
  }

  private buildSignedAreaPath(
    points: Array<{ x: number; y: number; equity: number }>,
    baseline: number,
    mode: 'positive' | 'negative',
  ): string {
    const segments: string[] = [];
    const isPositive = mode === 'positive';

    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const startDiff = start.equity - baseline;
      const endDiff = end.equity - baseline;
      const baselineY = this.equityValueToY(baseline);

      if ((isPositive && startDiff >= 0 && endDiff >= 0) || (!isPositive && startDiff <= 0 && endDiff <= 0)) {
        segments.push(
          `M${start.x.toFixed(2)},${baselineY.toFixed(2)} L${start.x.toFixed(2)},${start.y.toFixed(2)} L${end.x.toFixed(2)},${end.y.toFixed(2)} L${end.x.toFixed(2)},${baselineY.toFixed(2)} Z`,
        );
        continue;
      }

      if ((startDiff >= 0 && endDiff < 0) || (startDiff <= 0 && endDiff > 0)) {
        const ratio = Math.abs(startDiff) / (Math.abs(startDiff) + Math.abs(endDiff));
        const crossX = start.x + (end.x - start.x) * ratio;
        const crossY = baselineY;
        if ((isPositive && startDiff > 0) || (!isPositive && startDiff < 0)) {
          segments.push(
            `M${start.x.toFixed(2)},${baselineY.toFixed(2)} L${start.x.toFixed(2)},${start.y.toFixed(2)} L${crossX.toFixed(2)},${crossY.toFixed(2)} Z`,
          );
        }
        if ((isPositive && endDiff > 0) || (!isPositive && endDiff < 0)) {
          segments.push(
            `M${crossX.toFixed(2)},${crossY.toFixed(2)} L${end.x.toFixed(2)},${end.y.toFixed(2)} L${end.x.toFixed(2)},${baselineY.toFixed(2)} Z`,
          );
        }
      }
    }

    return segments.join(' ');
  }

  private equityValueToY(value: number): number {
    const model = this.selectedRun?.equity_series || [];
    if (!model.length) {
      return 0;
    }
    const dims = BacktestsPageComponent.EQUITY_CHART;
    const values = model.map(point => Number(point['equity'])).filter(valueItem => Number.isFinite(valueItem));
    const baseline = Number(this.selectedRun?.config?.['initial_capital'] || values[0] || 0);
    const min = Math.min(...values, baseline);
    const max = Math.max(...values, baseline);
    const padding = Math.max(Math.abs(max - min) * 0.12, baseline * 0.003, 25);
    const domainMin = Math.min(min, baseline) - padding;
    const domainMax = Math.max(max, baseline) + padding;
    const plotHeight = dims.height - dims.topPad - dims.bottomPad;
    const range = Math.max(domainMax - domainMin, 1);
    return dims.topPad + (domainMax - value) / range * plotHeight;
  }

  private formatChartDate(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date);
  }

  private formatCurrencyLabel(value: number): string {
    if (!Number.isFinite(value)) {
      return '$0';
    }
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(value);
  }

  reportSectionEntries(items: string[]): Array<{ label: string; value: string }> {
    return items.map(item => {
      const separatorIndex = item.indexOf(':');
      if (separatorIndex === -1) {
        return { label: 'Note', value: item };
      }

      return {
        label: item.slice(0, separatorIndex).trim(),
        value: item.slice(separatorIndex + 1).trim(),
      };
    });
  }

  exportReportPdf(): void {
    if (!this.selectedRun || !this.selectedReport || typeof window === 'undefined') {
      return;
    }

    const popup = window.open('', '_blank', 'width=1200,height=900');
    if (!popup) {
      this.toast('Allow pop-ups to export the report as PDF', 'error');
      return;
    }

    const summaryHtml = this.reportSummaryEntries()
      .map(
        item => `<div class="metric"><span>${item.label}</span><strong>${item.value}</strong></div>`,
      )
      .join('');

    const sectionsHtml = (this.selectedReport.sections || [])
      .map(section => {
        const entries = this.reportSectionEntries(section.items || [])
          .map(item => `<div class="entry"><span>${this.escapeHtml(item.label)}</span><strong>${this.escapeHtml(item.value)}</strong></div>`)
          .join('');
        return `<section class="section"><h2>${this.escapeHtml(section.title)}</h2><div class="entries">${entries}</div></section>`;
      })
      .join('');

    const llmHtml = this.selectedReport.llm_analysis
      ? `
        <section class="section llm">
          <h2>LLM Analysis</h2>
          <p>${this.escapeHtml(this.selectedReport.llm_analysis['executive_summary'] || '')}</p>
          <div class="columns">
            <div>
              <h3>Strengths</h3>
              <ul>${this.reportArrayItems(this.selectedReport.llm_analysis['strengths']).map(item => `<li>${this.escapeHtml(item)}</li>`).join('')}</ul>
            </div>
            <div>
              <h3>Weaknesses</h3>
              <ul>${this.reportArrayItems(this.selectedReport.llm_analysis['weaknesses']).map(item => `<li>${this.escapeHtml(item)}</li>`).join('')}</ul>
            </div>
            <div>
              <h3>Recommendations</h3>
              <ul>${this.reportArrayItems(this.selectedReport.llm_analysis['recommendations']).map(item => `<li>${this.escapeHtml(item)}</li>`).join('')}</ul>
            </div>
          </div>
        </section>`
      : '';

    const config = this.selectedRun.config || {};
    const pipelineSnapshot = (config['pipeline_snapshot'] || {}) as Record<string, unknown>;
    const runtimeSnapshot = (config['runtime_snapshot'] || {}) as Record<string, unknown>;
    const configRows = [
      ['Pipeline', String(this.selectedRun.pipeline_name || 'N/A')],
      ['Symbols', this.selectedSymbolsLabel],
      ['Date Range', `${config['start_date'] || 'N/A'} to ${config['end_date'] || 'N/A'}`],
      ['Timeframe', String(config['timeframe'] || 'N/A')],
      ['Initial Capital', `$${this.formatDisplayNumber(config['initial_capital'])}`],
      ['Trigger Mode', String(pipelineSnapshot['trigger_mode'] || 'N/A')],
      ['Schedule', pipelineSnapshot['schedule_enabled'] ? `${pipelineSnapshot['schedule_start_time'] || 'N/A'} - ${pipelineSnapshot['schedule_end_time'] || 'N/A'}` : 'Disabled'],
      ['Liquidate on Deactivation', String(Boolean(pipelineSnapshot['liquidate_on_deactivation']))],
      ['Timezone Snapshot', String(pipelineSnapshot['user_timezone'] || 'America/New_York')],
    ];
    const configHtml = configRows
      .map(([label, value]) => `<div class="metric"><span>${this.escapeHtml(label)}</span><strong>${this.escapeHtml(value)}</strong></div>`)
      .join('');

    const agentSections = Object.entries((runtimeSnapshot['agent_configs'] || {}) as Record<string, Record<string, unknown>>)
      .map(([agentName, agentConfig]) => {
        const title = agentName.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
        return `
          <section class="section">
            <h2>${this.escapeHtml(title)}</h2>
            <div class="entries single-column">
              <div class="entry"><span>Model</span><strong>${this.escapeHtml(String(agentConfig['model'] || 'N/A'))}</strong></div>
              <div class="entry code-block"><span>Instructions</span><strong>${this.escapeHtml(String(agentConfig['instructions'] || 'None'))}</strong></div>
            </div>
          </section>
        `;
      })
      .join('');

    const html = `
      <html>
        <head>
          <title>${this.escapeHtml(this.selectedRun.pipeline_name || 'Backtest Report')} Report</title>
          <style>
            @page { size: A4; margin: 16mm; }
            body { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 0; color: #111827; background: #ffffff; }
            .page { max-width: 1100px; margin: 0 auto; }
            h1 { margin: 0 0 8px; font-size: 28px; line-height: 1.05; }
            h2 { margin: 0 0 14px; font-size: 18px; line-height: 1.2; }
            h3 { margin: 0 0 10px; font-size: 14px; line-height: 1.2; }
            p.meta { color: #6b7280; margin: 0 0 24px; font-size: 13px; }
            .hero { padding-bottom: 18px; margin-bottom: 22px; border-bottom: 2px solid #e5eef7; }
            .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 24px; }
            .metric, .entry, .section { border: 1px solid #dbe4ee; border-radius: 12px; padding: 14px; background: #ffffff; break-inside: avoid; }
            .metric span, .entry span { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; margin-bottom: 8px; font-weight: 700; }
            .metric strong, .entry strong { font-size: 15px; line-height: 1.5; font-weight: 600; white-space: pre-wrap; }
            .section { margin-bottom: 16px; }
            .entries { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
            .entries.single-column { grid-template-columns: 1fr; }
            .columns { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
            ul { margin: 8px 0 0; padding-left: 18px; }
            li { margin-bottom: 6px; line-height: 1.5; }
            .code-block strong { font-family: "SF Mono", "Fira Code", Menlo, monospace; font-size: 12px; background: #f8fafc; border-radius: 8px; padding: 10px; display: block; }
            .section-group { margin-bottom: 26px; }
            .section-group > h2 { margin-bottom: 12px; }
            @media print {
              body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
              .section, .metric, .entry { box-shadow: none; }
            }
          </style>
        </head>
        <body>
          <div class="page">
            <section class="hero">
              <h1>${this.escapeHtml(this.selectedRun.pipeline_name || 'Backtest Report')}</h1>
              <p class="meta">${this.escapeHtml(String(config['start_date'] || 'N/A'))} to ${this.escapeHtml(String(config['end_date'] || 'N/A'))} · ${this.escapeHtml(String(config['timeframe'] || 'N/A'))} · Generated ${this.escapeHtml(new Date().toLocaleString())}</p>
            </section>

            <section class="section-group">
              <h2>Executive Summary</h2>
              <div class="grid">${summaryHtml}</div>
            </section>

            <section class="section-group">
              <h2>Backtest Context</h2>
              <div class="grid">${configHtml}</div>
            </section>

            <section class="section-group">
              <h2>Analysis</h2>
              ${sectionsHtml}
            </section>

            <section class="section-group">
              <h2>Agent Configuration</h2>
              ${agentSections || '<section class="section"><h2>Agent Configuration</h2><div class="entries single-column"><div class="entry"><span>Status</span><strong>No runtime agent configuration was captured.</strong></div></div></section>'}
            </section>

            ${llmHtml}
          </div>
        </body>
      </html>
    `;

    const blob = new Blob([html], { type: 'text/html' });
    const blobUrl = window.URL.createObjectURL(blob);
    let cleanedUp = false;
    const cleanup = () => {
      if (cleanedUp) {
        return;
      }
      cleanedUp = true;
      window.URL.revokeObjectURL(blobUrl);
    };

    popup.onload = () => {
      window.setTimeout(() => {
        try {
          popup.focus();
          popup.print();
        } finally {
          window.setTimeout(cleanup, 1000);
        }
      }, 300);
    };
    popup.onafterprint = cleanup;
    popup.location.href = blobUrl;
  }

  private escapeHtml(value: unknown): string {
    const normalized =
      value === null || value === undefined
        ? ''
        : typeof value === 'string'
          ? value
          : typeof value === 'number' || typeof value === 'boolean'
            ? String(value)
            : JSON.stringify(value, null, 2);

    return normalized
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  private formatLlmValue(value: unknown): string {
    if (value === null || value === undefined) {
      return '';
    }

    if (typeof value === 'string') {
      return value;
    }

    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }

    if (Array.isArray(value)) {
      return value.map(item => this.formatLlmValue(item)).filter(Boolean).join(', ');
    }

    if (typeof value === 'object') {
      const record = value as Record<string, unknown>;
      if (typeof record['summary'] === 'string') {
        return record['summary'];
      }
      if (typeof record['text'] === 'string') {
        return record['text'];
      }
      if (typeof record['content'] === 'string') {
        return record['content'];
      }

      const parts = Object.entries(record)
        .map(([key, item]) => {
          const formatted = this.formatLlmValue(item);
          if (!formatted) {
            return '';
          }
          const label = key
            .replace(/_/g, ' ')
            .replace(/\b\w/g, char => char.toUpperCase());
          return `${label}: ${formatted}`;
        })
        .filter(Boolean);
      return parts.join(' | ');
    }

    return String(value);
  }

  private resolveLaunchPipeline(
    allowFallbackToFirst = true,
    preferredId?: string | null,
  ): Pipeline | undefined {
    const resolvedPipelineId =
      preferredId ||
      this.selectedRun?.pipeline_id ||
      this.selectedPipelineId ||
      this.form.controls.pipelineId.value ||
      (allowFallbackToFirst ? this.pipelines[0]?.id : null);

    if (!resolvedPipelineId) {
      return allowFallbackToFirst ? this.pipelines[0] : undefined;
    }

    return (
      this.pipelines.find(pipeline => pipeline.id === resolvedPipelineId) ||
      (allowFallbackToFirst ? this.pipelines[0] : undefined)
    );
  }

  private activePipelineId(): string | null {
    return (
      this.selectedPipelineId ||
      this.selectedRun?.pipeline_id ||
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

  private restoreSelectedPipelineId(): string | null {
    if (typeof window === 'undefined') {
      return null;
    }

    return window.localStorage.getItem(BacktestsPageComponent.SELECTED_PIPELINE_KEY);
  }

  private persistSelectedPipelineId(pipelineId: string | null | undefined): void {
    if (typeof window === 'undefined') {
      return;
    }

    if (!pipelineId) {
      window.localStorage.removeItem(BacktestsPageComponent.SELECTED_PIPELINE_KEY);
      return;
    }

    window.localStorage.setItem(BacktestsPageComponent.SELECTED_PIPELINE_KEY, pipelineId);
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

  formatDisplayNumber(value: unknown): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }

    if (typeof value === 'number' && Number.isFinite(value)) {
      return value.toFixed(2);
    }

    const parsed = Number(value);
    if (Number.isFinite(parsed) && String(value).trim() !== '') {
      return parsed.toFixed(2);
    }

    return String(value);
  }

  formatTimestampDisplay(value: unknown): string {
    if (!value) {
      return '—';
    }

    const parsed = new Date(String(value));
    if (Number.isNaN(parsed.getTime())) {
      return String(value);
    }

    return parsed.toLocaleString([], {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }
}
