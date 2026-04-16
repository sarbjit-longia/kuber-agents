/**
 * Pipelines Component
 * 
 * List view of all saved pipelines with actions to edit, execute, or delete
 */

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';

import { PipelineService } from '../../core/services/pipeline.service';
import { ExecutionService } from '../../core/services/execution.service';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../shared/components/footer/footer.component';
import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';
import { Pipeline } from '../../core/models/pipeline.model';
import {
  LiquidationConfirmDialogComponent,
  LiquidationDialogResult
} from '../../shared/components/liquidation-confirm-dialog/liquidation-confirm-dialog.component';
import { ConfirmDialogComponent, ConfirmDialogData } from '../../shared/confirm-dialog/confirm-dialog.component';
import { ClonePipelineDialogComponent } from './clone-pipeline-dialog/clone-pipeline-dialog.component';
import { StrategyService } from '../../core/services/strategy.service';

@Component({
  selector: 'app-pipelines',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatMenuModule,
    MatDividerModule,
    MatSnackBarModule,
    MatDialogModule,
    NavbarComponent,
    FooterComponent,
    LocalDatePipe
  ],
  templateUrl: './pipelines.component.html',
  styleUrls: ['./pipelines.component.scss']
})
export class PipelinesComponent implements OnInit {
  pipelines: Pipeline[] = [];
  loading = true;
  displayedColumns: string[] = ['name', 'status', 'trigger', 'updated', 'actions'];

  constructor(
    private pipelineService: PipelineService,
    private executionService: ExecutionService,
    private router: Router,
    private snackBar: MatSnackBar,
    private dialog: MatDialog,
    private strategyService: StrategyService
  ) {}

  ngOnInit(): void {
    this.loadPipelines();
  }

  get activeCount(): number {
    return this.pipelines.filter(p => p.is_active).length;
  }

  get inactiveCount(): number {
    return this.pipelines.filter(p => !p.is_active).length;
  }

  get signalCount(): number {
    return this.pipelines.filter(p => p.trigger_mode === 'signal').length;
  }

  loadPipelines(): void {
    this.loading = true;
    this.pipelineService.loadPipelines().subscribe({
      next: (pipelines) => {
        this.pipelines = pipelines;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.showNotification('Failed to load pipelines', 'error');
      }
    });
  }

  createNew(): void {
    this.router.navigate(['/pipeline-builder']);
  }

  editPipeline(pipeline: Pipeline): void {
    this.router.navigate(['/pipeline-builder', pipeline.id]);
  }

  executePipeline(pipeline: Pipeline, event: Event): void {
    event.stopPropagation();
    
    // Manual execution doesn't require the pipeline to be active
    // Active pipelines are for scheduled/automated runs
    
    const executionData = {
      pipeline_id: pipeline.id,
      mode: (pipeline.config?.mode || 'paper') as 'paper' | 'live' | 'simulation' | 'validation',
      symbol: pipeline.config?.symbol || 'AAPL'
    };

    this.executionService.startExecution(executionData).subscribe({
      next: (execution) => {
        this.showNotification('Pipeline execution started!', 'success');
        this.router.navigate(['/monitoring', execution.id]);
      },
      error: () => {
        this.showNotification('Failed to start execution', 'error');
      }
    });
  }

  deletePipeline(pipeline: Pipeline, event: Event): void {
    event.stopPropagation();

    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '440px',
      data: {
        title: 'Delete Pipeline',
        message: `Delete pipeline "${pipeline.name}"? This cannot be undone.`,
        confirmText: 'Delete',
        cancelText: 'Cancel',
      } as ConfirmDialogData
    });

    dialogRef.afterClosed().subscribe(confirmed => {
      if (!confirmed) {
        return;
      }

      this.pipelineService.deletePipeline(pipeline.id).subscribe({
        next: () => {
          this.showNotification('Pipeline deleted', 'success');
          this.loadPipelines();
        },
        error: () => {
          this.showNotification('Failed to delete pipeline', 'error');
        }
      });
    });
  }

  clonePipeline(pipeline: Pipeline, event: Event): void {
    event.stopPropagation();

    const dialogRef = this.dialog.open(ClonePipelineDialogComponent, {
      width: '460px',
      data: { pipelineName: pipeline.name },
    });

    dialogRef.afterClosed().subscribe((cloneName?: string) => {
      const trimmedName = cloneName?.trim();
      if (!trimmedName) {
        return;
      }

      this.pipelineService.clonePipeline(pipeline.id, { name: trimmedName }).subscribe({
        next: (cloned) => {
          this.showNotification(`Pipeline cloned as "${cloned.name}"`, 'success');
          this.loadPipelines();
        },
        error: () => {
          this.showNotification('Failed to clone pipeline', 'error');
        }
      });
    });
  }

  openBacktest(pipeline: Pipeline, event: Event): void {
    event.stopPropagation();
    this.router.navigate(['/backtests/workspace'], { queryParams: { pipelineId: pipeline.id } });
  }

  exportStrategy(pipeline: Pipeline, event: Event): void {
    event.stopPropagation();
    this.strategyService.exportPipelineAsStrategy(pipeline.id).subscribe({
      next: (strategy) => {
        this.showNotification('Pipeline exported as strategy draft', 'success');
        this.router.navigate(['/strategies', strategy.id]);
      },
      error: () => {
        this.showNotification('Failed to export strategy', 'error');
      }
    });
  }

  toggleActive(pipeline: Pipeline, event: Event): void {
    event.stopPropagation();

    if (pipeline.is_active) {
      // Deactivating — open dialog to optionally liquidate
      const dialogRef = this.dialog.open(LiquidationConfirmDialogComponent, {
        width: '440px',
      });

      dialogRef.afterClosed().subscribe((result: LiquidationDialogResult | undefined) => {
        if (!result?.confirmed) return;

        this.pipelineService.deactivateWithLiquidation(pipeline.id, result.liquidate).subscribe({
          next: () => {
            const msg = result.liquidate
              ? 'Pipeline deactivated — positions being closed'
              : 'Pipeline deactivated';
            this.showNotification(msg, 'success');
            this.loadPipelines();
          },
          error: () => {
            this.showNotification('Failed to deactivate pipeline', 'error');
          }
        });
      });
    } else {
      // Activating — simple update
      this.pipelineService.updatePipeline(pipeline.id, { is_active: true }).subscribe({
        next: () => {
          this.showNotification('Pipeline activated', 'success');
          this.loadPipelines();
        },
        error: () => {
          this.showNotification('Failed to activate pipeline', 'error');
        }
      });
    }
  }

  getAgentCount(pipeline: Pipeline): number {
    return pipeline.config?.nodes?.length || 0;
  }

  showNotification(message: string, type: 'success' | 'error' | 'info' | 'warning'): void {
    this.snackBar.open(message, 'Close', {
      duration: 3000,
      horizontalPosition: 'right',
      verticalPosition: 'top',
      panelClass: [`snackbar-${type}`]
    });
  }
}
