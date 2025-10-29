/**
 * Pipeline Builder Component
 * 
 * Main visual pipeline editor with drag-and-drop functionality.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivatedRoute, Router } from '@angular/router';
import { Subject, takeUntil } from 'rxjs';

import { PipelineService } from '../../core/services/pipeline.service';
import { AgentService } from '../../core/services/agent.service';
import { ExecutionService } from '../../core/services/execution.service';
import { Pipeline, Agent, PipelineNode } from '../../core/models/pipeline.model';

@Component({
  selector: 'app-pipeline-builder',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatToolbarModule,
    MatSidenavModule,
    MatSnackBarModule
  ],
  templateUrl: './pipeline-builder.component.html',
  styleUrls: ['./pipeline-builder.component.scss']
})
export class PipelineBuilderComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();
  
  pipeline: Pipeline | null = null;
  agents: Agent[] = [];
  selectedNode: PipelineNode | null = null;
  
  // Canvas state
  nodes: PipelineNode[] = [];
  edges: any[] = [];
  
  // UI state
  loading = false;
  saving = false;
  sidenavOpened = true;

  constructor(
    private pipelineService: PipelineService,
    private agentService: AgentService,
    private executionService: ExecutionService,
    private route: ActivatedRoute,
    private router: Router,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    // Load agents
    this.loadAgents();
    
    // Load pipeline if editing existing one
    const pipelineId = this.route.snapshot.paramMap.get('id');
    if (pipelineId) {
      this.loadPipeline(pipelineId);
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  /**
   * Load available agents
   */
  loadAgents(): void {
    this.agentService.loadAgents()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (agents) => {
          this.agents = agents;
        },
        error: (error) => {
          this.showError('Failed to load agents');
          console.error('Error loading agents:', error);
        }
      });
  }

  /**
   * Load existing pipeline
   */
  loadPipeline(id: string): void {
    this.loading = true;
    this.pipelineService.getPipeline(id)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (pipeline) => {
          this.pipeline = pipeline;
          this.nodes = pipeline.config.nodes || [];
          this.edges = pipeline.config.edges || [];
          this.loading = false;
        },
        error: (error) => {
          this.showError('Failed to load pipeline');
          console.error('Error loading pipeline:', error);
          this.loading = false;
        }
      });
  }

  /**
   * Save pipeline
   */
  savePipeline(): void {
    if (!this.pipeline) {
      this.showError('No pipeline to save');
      return;
    }

    this.saving = true;
    const config = {
      nodes: this.nodes,
      edges: this.edges
    };

    this.pipelineService.updatePipeline(this.pipeline.id, { config })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (updated) => {
          this.pipeline = updated;
          this.saving = false;
          this.showSuccess('Pipeline saved');
        },
        error: (error) => {
          this.showError('Failed to save pipeline');
          console.error('Error saving pipeline:', error);
          this.saving = false;
        }
      });
  }

  /**
   * Execute pipeline
   */
  executePipeline(): void {
    if (!this.pipeline) {
      this.showError('No pipeline to execute');
      return;
    }

    // Save first, then execute
    this.saving = true;
    const config = {
      nodes: this.nodes,
      edges: this.edges
    };

    this.pipelineService.updatePipeline(this.pipeline.id, { config })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (updated) => {
          this.pipeline = updated;
          this.saving = false;
          
          // Now start execution
          this.startExecution();
        },
        error: (error) => {
          this.showError('Failed to save pipeline before execution');
          console.error('Error:', error);
          this.saving = false;
        }
      });
  }

  /**
   * Start execution
   */
  private startExecution(): void {
    if (!this.pipeline) return;

    this.executionService.startExecution({
      pipeline_id: this.pipeline.id,
      mode: 'paper'
    }).pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (execution) => {
          this.showSuccess('Execution started');
          // Navigate to execution monitor
          this.router.navigate(['/executions', execution.id]);
        },
        error: (error) => {
          this.showError('Failed to start execution');
          console.error('Error starting execution:', error);
        }
      });
  }

  /**
   * Add node to canvas
   */
  addNode(agentType: string): void {
    const agent = this.agents.find(a => a.agent_type === agentType);
    if (!agent) return;

    const newNode: PipelineNode = {
      id: `node-${Date.now()}`,
      agent_type: agentType,
      config: {},
      position: { x: 100, y: 100 }
    };

    this.nodes = [...this.nodes, newNode];
  }

  /**
   * Remove node from canvas
   */
  removeNode(nodeId: string): void {
    this.nodes = this.nodes.filter(n => n.id !== nodeId);
    this.edges = this.edges.filter(e => e.from !== nodeId && e.to !== nodeId);
  }

  /**
   * Select node for configuration
   */
  selectNode(node: PipelineNode): void {
    this.selectedNode = node;
  }

  /**
   * Update node configuration
   */
  updateNodeConfig(nodeId: string, config: any): void {
    const node = this.nodes.find(n => n.id === nodeId);
    if (node) {
      node.config = config;
    }
  }

  /**
   * Toggle sidenav
   */
  toggleSidenav(): void {
    this.sidenavOpened = !this.sidenavOpened;
  }

  /**
   * Show success message
   */
  private showSuccess(message: string): void {
    this.snackBar.open(message, 'Close', {
      duration: 3000,
      panelClass: ['success-snackbar']
    });
  }

  /**
   * Show error message
   */
  private showError(message: string): void {
    this.snackBar.open(message, 'Close', {
      duration: 5000,
      panelClass: ['error-snackbar']
    });
  }
}

