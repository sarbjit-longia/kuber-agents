import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { Pipeline } from '../../../core/models/pipeline.model';
import { BacktestRunSummary } from '../../../core/models/backtest.model';
import { NavbarComponent } from '../../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../../shared/components/footer/footer.component';
import { LocalDatePipe } from '../../../shared/pipes/local-date.pipe';
import { PipelineService } from '../../../core/services/pipeline.service';
import { BacktestService } from '../../../core/services/backtest.service';

@Component({
  selector: 'app-backtests-home',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    NavbarComponent,
    FooterComponent,
    LocalDatePipe,
  ],
  templateUrl: './backtests-home.component.html',
  styleUrls: ['./backtests-home.component.scss'],
})
export class BacktestsHomeComponent implements OnInit {
  pipelines: Pipeline[] = [];
  runs: BacktestRunSummary[] = [];
  loading = true;

  constructor(
    private readonly router: Router,
    private readonly pipelineService: PipelineService,
    private readonly backtestService: BacktestService,
  ) {}

  ngOnInit(): void {
    this.loadDashboard();
  }

  get activeRunCount(): number {
    return this.runs.filter(run => run.status === 'PENDING' || run.status === 'RUNNING').length;
  }

  get completedRunCount(): number {
    return this.runs.filter(run => run.status === 'COMPLETED').length;
  }

  get totalCost(): number {
    return this.runs.reduce((sum, run) => sum + Number(run.actual_cost || 0), 0);
  }

  get totalFilledOrders(): number {
    return this.runs.reduce((sum, run) => sum + Number(run.filled_orders_count || 0), 0);
  }

  get pipelineCards(): Array<{
    pipeline: Pipeline;
    runCount: number;
    activeCount: number;
    totalCost: number;
    filledOrders: number;
    latestRun: BacktestRunSummary | null;
    symbolsLabel: string;
  }> {
    return this.pipelines.map(pipeline => {
      const pipelineRuns = this.runs.filter(run => run.pipeline_id === pipeline.id);
      const scannerSymbols = pipeline.scanner_tickers || [];
      const configSymbol = pipeline.config?.symbol ? [pipeline.config.symbol] : [];
      const symbols = scannerSymbols.length ? scannerSymbols : configSymbol;

      return {
        pipeline,
        runCount: pipelineRuns.length,
        activeCount: pipelineRuns.filter(run => run.status === 'PENDING' || run.status === 'RUNNING').length,
        totalCost: pipelineRuns.reduce((sum, run) => sum + Number(run.actual_cost || 0), 0),
        filledOrders: pipelineRuns.reduce((sum, run) => sum + Number(run.filled_orders_count || 0), 0),
        latestRun: pipelineRuns[0] || null,
        symbolsLabel: symbols.join(', ') || 'No default symbols',
      };
    });
  }

  openPipelineWorkspace(pipelineId: string): void {
    this.router.navigate(['/backtests/workspace'], { queryParams: { pipelineId } });
  }

  refresh(): void {
    this.loadDashboard();
  }

  private loadDashboard(): void {
    this.loading = true;

    let pipelinesLoaded = false;
    let runsLoaded = false;

    const finish = () => {
      if (pipelinesLoaded && runsLoaded) {
        this.loading = false;
      }
    };

    this.pipelineService.loadPipelines().subscribe({
      next: pipelines => {
        this.pipelines = pipelines;
        pipelinesLoaded = true;
        finish();
      },
      error: () => {
        pipelinesLoaded = true;
        finish();
      },
    });

    this.backtestService.listBacktests(0, 100).subscribe({
      next: response => {
        this.runs = response.backtests || [];
        runsLoaded = true;
        finish();
      },
      error: () => {
        runsLoaded = true;
        finish();
      },
    });
  }
}
