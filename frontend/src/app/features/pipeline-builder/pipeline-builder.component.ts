/**
 * Visual Pipeline Builder Component
 * 
 * Features:
 * - Drag-and-drop nodes from palette to canvas
 * - Visual connections between nodes
 * - Node configuration
 * - Zoom and pan canvas
 */

import { Component, OnInit, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CdkDragDrop, CdkDragEnd, DragDropModule } from '@angular/cdk/drag-drop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { Router } from '@angular/router';

import { AgentService } from '../../core/services/agent.service';
import { PipelineService } from '../../core/services/pipeline.service';
import { ExecutionService } from '../../core/services/execution.service';
import { PipelineNode } from '../../core/models/pipeline.model';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { JsonSchemaFormComponent } from '../../shared/json-schema-form/json-schema-form.component';

// Define AgentMetadata locally since it might not be exported
interface AgentMetadata {
  agent_type: string;
  name: string;
  description: string;
  category: string;
  version: string;
  icon?: string;
  pricing_rate: number;
  is_free: boolean;
  requires_timeframes: string[];
  requires_market_data: boolean;
  requires_position: boolean;
  config_schema?: any; // JSON Schema for agent configuration
}

interface CanvasNode extends PipelineNode {
  position: { x: number; y: number };
  metadata?: AgentMetadata;
}

interface Connection {
  from: string;
  to: string;
}

@Component({
  selector: 'app-pipeline-builder',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    DragDropModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatSidenavModule,
    MatTooltipModule,
    MatSnackBarModule,
    MatInputModule,
    MatFormFieldModule,
    MatSelectModule,
    MatDialogModule,
    MatDividerModule,
    NavbarComponent,
    JsonSchemaFormComponent
  ],
  templateUrl: './pipeline-builder.component.html',
  styleUrls: ['./pipeline-builder.component.scss']
})
export class PipelineBuilderComponent implements OnInit {
  @ViewChild('canvas') canvasRef!: ElementRef<HTMLDivElement>;
  
  agents: AgentMetadata[] = [];
  canvasNodes: CanvasNode[] = [];
  connections: Connection[] = [];
  selectedNode: CanvasNode | null = null;
  connecting: { node: CanvasNode, port: 'output' } | null = null;
  
  loading = false;
  saving = false;
  executing = false;
  
  pipelineName = 'Untitled Pipeline';
  pipelineDescription = '';
  selectedSymbol = 'AAPL';
  executionMode = 'paper';
  
  // Canvas state
  canvasScale = 1;
  canvasOffset = { x: 0, y: 0 };
  isPanning = false;
  panStart = { x: 0, y: 0 };

  symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN', 'META', 'NVDA', 'AMD'];
  modes = [
    { value: 'paper', label: 'Paper Trading' },
    { value: 'simulation', label: 'Simulation' },
    { value: 'validation', label: 'Validation' },
    { value: 'live', label: 'Live Trading' }
  ];

  constructor(
    private agentService: AgentService,
    private pipelineService: PipelineService,
    private executionService: ExecutionService,
    private snackBar: MatSnackBar,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.loadAgents();
  }

  loadAgents(): void {
    this.loading = true;
    // Check if getAgents exists, otherwise use a fallback
    const agentsObservable = (this.agentService as any).getAgents ? 
      (this.agentService as any).getAgents() : 
      (this.agentService as any).loadAgents();
      
    agentsObservable.subscribe({
      next: (agents: AgentMetadata[]) => {
        this.agents = agents;
        this.loading = false;
      },
      error: (error: any) => {
        console.error('Failed to load agents', error);
        this.showNotification('Failed to load agents', 'error');
        this.loading = false;
      }
    });
  }

  /**
   * Handle drop on canvas from palette
   */
  onCanvasDrop(event: CdkDragDrop<any>): void {
    // Check if this is a drop from palette to canvas
    if (event.previousContainer.id === 'agent-palette' && event.container.id === 'canvas-dropzone') {
      const agent = event.item.data as AgentMetadata;
      
      // Get drop position relative to canvas
      const canvasRect = this.canvasRef.nativeElement.getBoundingClientRect();
      const dropX = event.dropPoint.x - canvasRect.left + this.canvasRef.nativeElement.scrollLeft;
      const dropY = event.dropPoint.y - canvasRect.top + this.canvasRef.nativeElement.scrollTop;

      this.addNodeToCanvas(agent, dropX, dropY);
    }
    // If it's within the same container (canvas), handle node repositioning
    else if (event.previousContainer === event.container) {
      // Node moved within canvas - handled by cdkDragMoved if needed
    }
  }

  /**
   * Add agent to center of canvas (double-click handler)
   */
  addAgentToCenter(agent: AgentMetadata): void {
    const canvasRect = this.canvasRef.nativeElement.getBoundingClientRect();
    
    // Calculate center position
    const centerX = (canvasRect.width / 2) + this.canvasRef.nativeElement.scrollLeft - 100; // 100 = half node width
    const centerY = (canvasRect.height / 2) + this.canvasRef.nativeElement.scrollTop - 80; // 80 = half node height
    
    this.addNodeToCanvas(agent, centerX, centerY);
    
    // Show feedback
    this.snackBar.open(`${agent.name} added to canvas`, 'Close', {
      duration: 2000,
      horizontalPosition: 'center',
      verticalPosition: 'bottom'
    });
  }

  /**
   * Handle node drag within canvas
   */
  onNodeDragEnded(event: CdkDragEnd, node: CanvasNode): void {
    // Get the drag distance (how far the element moved)
    const distance = event.distance;
    
    // Update node position by adding the drag distance to current position
    node.position.x += distance.x;
    node.position.y += distance.y;
    
    // Update connections if needed
    this.updateConnectionLines();
  }

  /**
   * Update connection line positions
   */
  updateConnectionLines(): void {
    // Force change detection to update SVG lines
    // This ensures connection lines follow the nodes
    this.connections = [...this.connections];
  }

  /**
   * Add node to canvas at specific position
   */
  addNodeToCanvas(agent: AgentMetadata, x: number, y: number): void {
    const newNode: CanvasNode = {
      id: `node-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      agent_type: agent.agent_type,
      config: {},
      position: { x, y },
      metadata: agent
    };
    
    this.canvasNodes.push(newNode);
    this.showNotification(`Added ${agent.name}`, 'success');
  }

  /**
   * Start connecting nodes
   */
  startConnection(node: CanvasNode): void {
    this.connecting = { node, port: 'output' };
  }

  /**
   * Complete connection
   */
  completeConnection(targetNode: CanvasNode): void {
    if (!this.connecting || this.connecting.node.id === targetNode.id) {
      this.connecting = null;
      return;
    }

    const newConnection: Connection = {
      from: this.connecting.node.id,
      to: targetNode.id
    };

    // Check if connection already exists
    const exists = this.connections.some(
      c => c.from === newConnection.from && c.to === newConnection.to
    );

    if (!exists) {
      this.connections.push(newConnection);
      this.showNotification('Connection created', 'success');
    }

    this.connecting = null;
  }

  /**
   * Remove connection
   */
  removeConnection(connection: Connection): void {
    this.connections = this.connections.filter(
      c => !(c.from === connection.from && c.to === connection.to)
    );
    this.showNotification('Connection removed', 'info');
  }

  /**
   * Select node for configuration
   */
  selectNode(node: CanvasNode): void {
    this.selectedNode = node;
  }

  /**
   * Handle configuration changes from JSON Schema form
   */
  onConfigChange(config: any, node: CanvasNode): void {
    node.config = config;
    this.showNotification('Configuration updated', 'success');
  }

  /**
   * Remove node from canvas
   */
  removeNode(nodeId: string): void {
    // Remove node
    this.canvasNodes = this.canvasNodes.filter(n => n.id !== nodeId);
    
    // Remove connections
    this.connections = this.connections.filter(
      c => c.from !== nodeId && c.to !== nodeId
    );
    
    if (this.selectedNode?.id === nodeId) {
      this.selectedNode = null;
    }
    
    this.showNotification('Node removed', 'info');
  }

  /**
   * Get connection path (SVG line)
   */
  getConnectionPath(connection: Connection): string {
    const fromNode = this.canvasNodes.find(n => n.id === connection.from);
    const toNode = this.canvasNodes.find(n => n.id === connection.to);
    
    if (!fromNode || !toNode) return '';

    const fromX = fromNode.position.x + 150; // Center + half width
    const fromY = fromNode.position.y + 100; // Bottom of node
    const toX = toNode.position.x + 150;
    const toY = toNode.position.y; // Top of node

    // Bezier curve for smooth connection
    const midY = (fromY + toY) / 2;
    return `M ${fromX} ${fromY} C ${fromX} ${midY}, ${toX} ${midY}, ${toX} ${toY}`;
  }

  /**
   * Calculate total pipeline cost
   */
  calculateTotalCost(): number {
    return this.canvasNodes.reduce((total, node) => {
      return total + (node.metadata?.pricing_rate || 0);
    }, 0);
  }

  /**
   * Clear canvas
   */
  clearCanvas(): void {
    if (confirm('Are you sure you want to clear the entire canvas?')) {
      this.canvasNodes = [];
      this.connections = [];
      this.selectedNode = null;
      this.showNotification('Canvas cleared', 'info');
    }
  }

  /**
   * Save pipeline
   */
  savePipeline(): void {
    if (this.canvasNodes.length === 0) {
      this.showNotification('Please add at least one agent', 'warning');
      return;
    }

    this.saving = true;
    const pipelineData: any = {
      name: this.pipelineName,
      description: this.pipelineDescription,
      config: {
        nodes: this.canvasNodes.map(node => ({
          id: node.id,
          agent_type: node.agent_type,
          config: node.config,
          position: node.position
        })),
        edges: this.connections.map(conn => ({
          from: conn.from,
          to: conn.to
        })),
        symbol: this.selectedSymbol,
        mode: this.executionMode
      },
      is_active: false
    };

    this.pipelineService.createPipeline(pipelineData).subscribe({
      next: (pipeline: any) => {
        this.saving = false;
        this.showNotification('Pipeline saved successfully!', 'success');
        console.log('Pipeline saved:', pipeline);
      },
      error: (error: any) => {
        this.saving = false;
        this.showNotification('Failed to save pipeline', 'error');
        console.error('Save error:', error);
      }
    });
  }

  /**
   * Execute pipeline
   */
  executePipeline(): void {
    if (this.canvasNodes.length === 0) {
      this.showNotification('Please add agents to the pipeline', 'warning');
      return;
    }

    this.executing = true;
    
    const pipelineData: any = {
      name: this.pipelineName,
      description: this.pipelineDescription,
      config: {
        nodes: this.canvasNodes.map(node => ({
          id: node.id,
          agent_type: node.agent_type,
          config: node.config,
          position: node.position
        })),
        edges: this.connections.map(conn => ({
          from: conn.from,
          to: conn.to
        })),
        symbol: this.selectedSymbol,
        mode: this.executionMode
      },
      is_active: true
    };

    this.pipelineService.createPipeline(pipelineData).subscribe({
      next: (pipeline: any) => {
        const executionData: any = {
          pipeline_id: pipeline.id,
          symbol: this.selectedSymbol,
          mode: this.executionMode as 'live' | 'paper' | 'simulation' | 'validation'
        };

        this.executionService.startExecution(executionData).subscribe({
          next: (execution: any) => {
            this.executing = false;
            this.showNotification('Pipeline execution started!', 'success');
            console.log('Execution started:', execution);
          },
          error: (error: any) => {
            this.executing = false;
            this.showNotification('Failed to start execution', 'error');
            console.error('Execution error:', error);
          }
        });
      },
      error: (error: any) => {
        this.executing = false;
        this.showNotification('Failed to save pipeline', 'error');
        console.error('Save error:', error);
      }
    });
  }

  /**
   * Show notification
   */
  private showNotification(message: string, type: 'success' | 'error' | 'warning' | 'info'): void {
    this.snackBar.open(message, 'Close', {
      duration: 3000,
      horizontalPosition: 'end',
      verticalPosition: 'top',
      panelClass: [`snackbar-${type}`]
    });
  }
}
