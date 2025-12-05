/**
 * Visual Pipeline Builder Component
 * 
 * Features:
 * - Drag-and-drop nodes from palette to canvas
 * - Visual connections between nodes
 * - Node configuration
 * - Zoom and pan canvas
 */

import { Component, OnInit, ViewChild, ElementRef, QueryList, ViewChildren } from '@angular/core';
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
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { Router, ActivatedRoute } from '@angular/router';

import { AgentService } from '../../core/services/agent.service';
import { PipelineService } from '../../core/services/pipeline.service';
import { ExecutionService } from '../../core/services/execution.service';
import { ToolService } from '../../core/services/tool.service'; // Added
import { PipelineNode } from '../../core/models/pipeline.model';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { JsonSchemaFormComponent } from '../../shared/json-schema-form/json-schema-form.component';
import { ToolSelectorComponent } from '../../shared/tool-selector/tool-selector.component';
import { ValidationErrorDialogComponent } from '../../shared/validation-error-dialog/validation-error-dialog.component';

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
  supported_tools?: string[]; // List of tool types this agent supports
}

// Added ToolMetadata interface
interface ToolMetadata {
  tool_type: string;
  name: string;
  description: string;
  category: string;
  version: string;
  icon?: string;
  requires_credentials: boolean;
  config_schema?: any;
}

interface CanvasNode extends PipelineNode {
  position: { x: number; y: number };
  metadata?: AgentMetadata | ToolMetadata; // Can be either agent or tool
  node_category?: 'agent' | 'tool'; // Added to distinguish node types
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
    JsonSchemaFormComponent,
    ToolSelectorComponent
  ],
  templateUrl: './pipeline-builder.component.html',
  styleUrls: ['./pipeline-builder.component.scss']
})
export class PipelineBuilderComponent implements OnInit {
  @ViewChild('canvas') canvasRef!: ElementRef<HTMLDivElement>;
  
  agents: AgentMetadata[] = [];
  tools: ToolMetadata[] = [];
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
  
  // Canvas state - Infinite Canvas
  canvasScale = 1;
  canvasPosition = { x: 0, y: 0 }; // Current pan position
  isPanning = false;
  lastMousePosition = { x: 0, y: 0 };
  
  // Constants for zoom limits
  readonly MIN_SCALE = 0.1;
  readonly MAX_SCALE = 3;
  readonly ZOOM_SENSITIVITY = 0.001;

  symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN', 'META', 'NVDA', 'AMD'];
  modes = [
    { value: 'paper', label: 'Paper Trading' },
    { value: 'simulation', label: 'Simulation' },
    { value: 'validation', label: 'Validation' },
    { value: 'live', label: 'Live Trading' }
  ];

  currentPipelineId: string | null = null;
  
  // Configuration editing state
  editingConfig: any = null;
  originalConfig: any = null;
  
  @ViewChild('jsonSchemaForm') jsonSchemaForm?: JsonSchemaFormComponent;

  constructor(
    private agentService: AgentService,
    private pipelineService: PipelineService,
    private executionService: ExecutionService,
    private toolService: ToolService,
    private snackBar: MatSnackBar,
    private dialog: MatDialog,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    this.loadAgents();
    this.loadTools();
    
    this.route.paramMap.subscribe(params => {
      const pipelineId = params.get('id');
      if (pipelineId) {
        this.currentPipelineId = pipelineId;
        this.waitForAgentsAndLoadPipeline(pipelineId);
      }
    });
  }
  
  /**
   * Wait for agents and tools to be loaded, then load the pipeline
   */
  waitForAgentsAndLoadPipeline(pipelineId: string): void {
    if (this.agents.length > 0 && this.tools.length > 0) {
      this.loadPipeline(pipelineId);
    } else {
      let attempts = 0;
      const maxAttempts = 50;
      const interval = setInterval(() => {
        attempts++;
        if (this.agents.length > 0 && this.tools.length > 0) {
          clearInterval(interval);
          this.loadPipeline(pipelineId);
        } else if (attempts >= maxAttempts) {
          clearInterval(interval);
          console.warn('Agents/tools not loaded in time, loading pipeline anyway');
          this.loadPipeline(pipelineId);
        }
      }, 100);
    }
  }

  loadAgents(): void {
    this.loading = true;
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

  loadTools(): void {
    this.toolService.getTools().subscribe({
      next: (tools) => {
        this.tools = tools;
      },
      error: (error) => {
        console.error('Error loading tools:', error);
        this.showNotification('Failed to load tools', 'error');
      }
    });
  }

  loadPipeline(pipelineId: string): void {
    this.loading = true;
    
    this.pipelineService.getPipeline(pipelineId).subscribe({
      next: (pipeline) => {
        this.pipelineName = pipeline.name || 'Untitled Pipeline';
        this.pipelineDescription = pipeline.description || '';
        
        if (pipeline.config) {
          this.selectedSymbol = pipeline.config.symbol || 'AAPL';
          this.executionMode = pipeline.config.mode || 'paper';
          
          if (pipeline.config.nodes && Array.isArray(pipeline.config.nodes)) {
            this.canvasNodes = pipeline.config.nodes.map((node: any) => {
              const agentMetadata = this.agents.find(a => a.agent_type === node.agent_type);
              
              return {
                id: node.id,
                agent_type: node.agent_type,
                config: node.config || {},
                position: node.position || { x: 100, y: 100 },
                metadata: agentMetadata,
                node_category: node.node_category || 'agent'
              };
            });
            
            // Recreate visual tool nodes
            this.canvasNodes.forEach((node: CanvasNode) => {
              if (node.node_category === 'agent' && node.config && node.config['tools']) {
                const tools = node.config['tools'];
                if (Array.isArray(tools) && tools.length > 0) {
                  tools.forEach((toolData: any) => {
                    this.createToolNode(toolData.tool_type, node, toolData);
                  });
                  this.repositionAllToolsForAgent(node);
                }
              }
            });
          }
          
          if (pipeline.config.edges && Array.isArray(pipeline.config.edges)) {
            this.connections = pipeline.config.edges.map((edge: any) => ({
              from: edge.from,
              to: edge.to
            }));
          }
        }
        
        this.loading = false;
        this.showNotification('Pipeline loaded successfully', 'success');
        
        // Center canvas on nodes if any exist
        if (this.canvasNodes.length > 0) {
          setTimeout(() => this.centerCanvasOnNodes(), 100);
        }
      },
      error: (error) => {
        console.error('❌ Failed to load pipeline:', error);
        this.loading = false;
        this.showNotification('Failed to load pipeline', 'error');
      }
    });
  }

  // --- Infinite Canvas Logic ---

  /**
   * Handle mouse wheel for zooming
   */
  onWheel(event: WheelEvent): void {
    event.preventDefault();
    
    const zoomDelta = -event.deltaY * this.ZOOM_SENSITIVITY;
    const newScale = Math.min(Math.max(this.canvasScale + zoomDelta, this.MIN_SCALE), this.MAX_SCALE);
    
    // Zoom towards mouse position
    if (newScale !== this.canvasScale) {
      const canvasRect = this.canvasRef.nativeElement.getBoundingClientRect();
      const mouseX = event.clientX - canvasRect.left;
      const mouseY = event.clientY - canvasRect.top;
      
      // Calculate mouse position in canvas coordinates
      const canvasMouseX = (mouseX - this.canvasPosition.x) / this.canvasScale;
      const canvasMouseY = (mouseY - this.canvasPosition.y) / this.canvasScale;
      
      // Update scale
      this.canvasScale = newScale;
      
      // Adjust position to keep mouse over same canvas point
      this.canvasPosition.x = mouseX - canvasMouseX * this.canvasScale;
      this.canvasPosition.y = mouseY - canvasMouseY * this.canvasScale;
    }
  }

  /**
   * Start panning on mouse down (middle click or space+click)
   */
  onMouseDown(event: MouseEvent): void {
    // Middle mouse button or Left click + Space
    if (event.button === 1 || (event.button === 0 && event.shiftKey)) {
      event.preventDefault();
      this.isPanning = true;
      this.lastMousePosition = { x: event.clientX, y: event.clientY };
      this.canvasRef.nativeElement.style.cursor = 'grabbing';
    }
  }

  /**
   * Handle panning movement
   */
  onMouseMove(event: MouseEvent): void {
    if (this.isPanning) {
      event.preventDefault();
      const dx = event.clientX - this.lastMousePosition.x;
      const dy = event.clientY - this.lastMousePosition.y;
      
      this.canvasPosition.x += dx;
      this.canvasPosition.y += dy;
      
      this.lastMousePosition = { x: event.clientX, y: event.clientY };
    }
  }

  /**
   * Stop panning
   */
  onMouseUp(event: MouseEvent): void {
    if (this.isPanning) {
      this.isPanning = false;
      this.canvasRef.nativeElement.style.cursor = 'default';
    }
  }

  /**
   * Center canvas on specific nodes or reset
   */
  centerCanvasOnNodes(): void {
    if (this.canvasNodes.length === 0) {
      this.resetCanvas();
      return;
    }

    // Calculate bounding box of all nodes
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    
    this.canvasNodes.forEach(node => {
      minX = Math.min(minX, node.position.x);
      minY = Math.min(minY, node.position.y);
      maxX = Math.max(maxX, node.position.x + 160); // Node width
      maxY = Math.max(maxY, node.position.y + 90);  // Node height
    });

    const canvasRect = this.canvasRef.nativeElement.getBoundingClientRect();
    const padding = 100;
    
    const contentWidth = maxX - minX + (padding * 2);
    const contentHeight = maxY - minY + (padding * 2);
    
    // Calculate scale to fit content
    const scaleX = canvasRect.width / contentWidth;
    const scaleY = canvasRect.height / contentHeight;
    this.canvasScale = Math.min(Math.min(scaleX, scaleY), 1); // Don't zoom in past 100%
    
    // Center content
    this.canvasPosition.x = (canvasRect.width - (contentWidth * this.canvasScale)) / 2 - (minX - padding) * this.canvasScale;
    this.canvasPosition.y = (canvasRect.height - (contentHeight * this.canvasScale)) / 2 - (minY - padding) * this.canvasScale;
  }

  resetCanvas(): void {
    this.canvasScale = 1;
    const canvasRect = this.canvasRef.nativeElement.getBoundingClientRect();
    this.canvasPosition = { x: canvasRect.width / 2, y: canvasRect.height / 2 };
  }

  zoomIn(): void {
    this.canvasScale = Math.min(this.canvasScale * 1.2, this.MAX_SCALE);
  }

  zoomOut(): void {
    this.canvasScale = Math.max(this.canvasScale / 1.2, this.MIN_SCALE);
  }

  // --- Drag & Drop Logic ---

  onCanvasDrop(event: CdkDragDrop<any>): void {
    if (event.previousContainer.id === 'agent-palette' && event.container.id === 'canvas-dropzone') {
      const agent = event.item.data as AgentMetadata;
      
      // Calculate drop position in canvas coordinates
      // 1. Get drop point relative to viewport
      const dropPoint = event.dropPoint;
      
      // 2. Get canvas rect
      const canvasRect = this.canvasRef.nativeElement.getBoundingClientRect();
      
      // 3. Calculate position relative to canvas container
      const relativeX = dropPoint.x - canvasRect.left;
      const relativeY = dropPoint.y - canvasRect.top;
      
      // 4. Apply inverse transform to get canvas coordinates
      const canvasX = (relativeX - this.canvasPosition.x) / this.canvasScale;
      const canvasY = (relativeY - this.canvasPosition.y) / this.canvasScale;

      this.addNodeToCanvas(agent, canvasX, canvasY);
    }
  }

  addAgentToCenter(agent: AgentMetadata): void {
    const canvasRect = this.canvasRef.nativeElement.getBoundingClientRect();
    
    // Center of viewport converted to canvas coordinates
    const centerX = (canvasRect.width / 2 - this.canvasPosition.x) / this.canvasScale - 80; // 80 = half node width
    const centerY = (canvasRect.height / 2 - this.canvasPosition.y) / this.canvasScale - 45; // 45 = half node height
    
    this.addNodeToCanvas(agent, centerX, centerY, 'agent');
    
    this.snackBar.open(`${agent.name} added to canvas`, 'Close', {
      duration: 2000,
      horizontalPosition: 'center',
      verticalPosition: 'bottom'
    });
  }

  onNodeDragEnded(event: CdkDragEnd, node: CanvasNode): void {
    // Adjust drag distance by scale
    const distance = event.distance;
    const scaledX = distance.x / this.canvasScale;
    const scaledY = distance.y / this.canvasScale;
    
    node.position.x += scaledX;
    node.position.y += scaledY;
    
    // Reset transform (CDK drag leaves a transform style)
    event.source.reset();
    
    // Move attached tools
    if (node.node_category === 'agent' && node.config['_toolNodeIds']) {
      const toolRefs = node.config['_toolNodeIds'] as Array<{toolType: string, nodeId: string}>;
      
      toolRefs.forEach(ref => {
        const toolNode = this.canvasNodes.find(n => n.id === ref.nodeId);
        if (toolNode) {
          toolNode.position.x += scaledX;
          toolNode.position.y += scaledY;
        }
      });
    }
    
    this.updateConnectionLines();
  }

  updateConnectionLines(): void {
    this.connections = [...this.connections];
  }

  addNodeToCanvas(item: AgentMetadata | ToolMetadata, x: number, y: number, nodeCategory: 'agent' | 'tool' = 'agent'): void {
    const newNode: CanvasNode = {
      id: `node-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      agent_type: (item as any).agent_type || (item as any).tool_type,
      config: {},
      position: { x, y },
      metadata: item,
      node_category: nodeCategory
    };
    
    this.canvasNodes.push(newNode);
    this.showNotification(`Added ${item.name}`, 'success');
  }

  // --- Connection Logic ---

  startConnection(node: CanvasNode): void {
    this.connecting = { node, port: 'output' };
  }

  completeConnection(targetNode: CanvasNode): void {
    if (!this.connecting || this.connecting.node.id === targetNode.id) {
      this.connecting = null;
      return;
    }

    const newConnection: Connection = {
      from: this.connecting.node.id,
      to: targetNode.id
    };

    const exists = this.connections.some(
      c => c.from === newConnection.from && c.to === newConnection.to
    );

    if (!exists) {
      this.connections.push(newConnection);
      this.showNotification('Connection created', 'success');
    }

    this.connecting = null;
  }

  removeConnection(connection: Connection): void {
    this.connections = this.connections.filter(
      c => !(c.from === connection.from && c.to === connection.to)
    );
    this.showNotification('Connection removed', 'info');
  }

  // --- Helper Methods ---

