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
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { PipelineService } from '../../core/services/pipeline.service';
import { ExecutionService } from '../../core/services/execution.service';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';

@Component({
  selector: 'app-pipelines',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatMenuModule,
    MatDividerModule,
    MatSnackBarModule,
    NavbarComponent
  ],
  templateUrl: './pipelines.component.html',
  styleUrls: ['./pipelines.component.scss']
})
export class PipelinesComponent implements OnInit {
  pipelines: any[] = [];
  loading = true;
  displayedColumns: string[] = ['name', 'status', 'created', 'actions'];

  constructor(
    private pipelineService: PipelineService,
    private executionService: ExecutionService,
    private router: Router,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.loadPipelines();
  }

  loadPipelines(): void {
    this.loading = true;
    console.log('🔄 Loading pipelines...');
    this.pipelineService.loadPipelines().subscribe({
      next: (pipelines) => {
        console.log('✅ Pipelines loaded:', pipelines);
        console.log('📊 Pipeline count:', pipelines.length);
        this.pipelines = pipelines;
        this.loading = false;
      },
      error: (error) => {
        console.error('❌ Failed to load pipelines:', error);
        this.loading = false;
        this.showNotification('Failed to load pipelines', 'error');
      }
    });
  }

  createNew(): void {
    this.router.navigate(['/pipeline-builder']);
  }

  editPipeline(pipeline: any): void {
    this.router.navigate(['/pipeline-builder', pipeline.id]);
  }

  executePipeline(pipeline: any, event: Event): void {
    event.stopPropagation();
    
    // Manual execution doesn't require the pipeline to be active
    // Active pipelines are for scheduled/automated runs
    
    const executionData = {
      pipeline_id: pipeline.id,
      mode: 'paper' as 'paper' | 'live' | 'simulation' | 'validation', // Type assertion for mode
      symbol: pipeline.config?.symbol || 'AAPL'
    };

    this.executionService.startExecution(executionData).subscribe({
      next: (execution) => {
        this.showNotification('Pipeline execution started!', 'success');
        this.router.navigate(['/monitoring', execution.id]);
      },
      error: (error) => {
        console.error('Failed to start execution:', error);
        this.showNotification('Failed to start execution', 'error');
      }
    });
  }

  deletePipeline(pipeline: any, event: Event): void {
    event.stopPropagation();
    
    if (confirm(`Delete pipeline "${pipeline.name}"? This cannot be undone.`)) {
      this.pipelineService.deletePipeline(pipeline.id).subscribe({
        next: () => {
          this.showNotification('Pipeline deleted', 'success');
          this.loadPipelines();
        },
        error: (error) => {
          console.error('Failed to delete pipeline:', error);
          this.showNotification('Failed to delete pipeline', 'error');
        }
      });
    }
  }

  toggleActive(pipeline: any, event: Event): void {
    event.stopPropagation();
    
    console.log('🔄 Toggling pipeline active status:', pipeline.name, 'Current:', pipeline.is_active);
    
    const updatedPipeline = {
      is_active: !pipeline.is_active
    };

    console.log('📤 Sending update:', updatedPipeline);

    this.pipelineService.updatePipeline(pipeline.id, updatedPipeline).subscribe({
      next: (response) => {
        console.log('✅ Pipeline updated:', response);
        this.showNotification(
          pipeline.is_active ? 'Pipeline deactivated' : 'Pipeline activated',
          'success'
        );
        this.loadPipelines();
      },
      error: (error) => {
        console.error('❌ Failed to update pipeline:', error);
        this.showNotification('Failed to update pipeline', 'error');
      }
    });
  }

  formatDate(dateString: string): string {
    if (!dateString) return '-';
    // Ensure UTC dates from backend are treated as UTC before converting to local
    let isoString = dateString;
    if (!dateString.endsWith('Z') && !dateString.match(/[+-]\d{2}:\d{2}$/)) {
      isoString = dateString + 'Z';
    }
    return new Date(isoString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  getAgentCount(pipeline: any): number {
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

