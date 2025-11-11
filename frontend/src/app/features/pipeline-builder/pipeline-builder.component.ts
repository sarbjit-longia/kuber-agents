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
  tools: ToolMetadata[] = []; // Added tools array
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

  currentPipelineId: string | null = null;
  
  // Configuration editing state
  editingConfig: any = null; // Temporary config being edited
  originalConfig: any = null; // Original config before editing

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
    // Load agents and tools first
    this.loadAgents();
    this.loadTools();
    
    // Check if we're editing an existing pipeline
    // Wait for agents to load before loading pipeline
    this.route.paramMap.subscribe(params => {
      const pipelineId = params.get('id');
      if (pipelineId) {
        this.currentPipelineId = pipelineId;
        // Wait a bit for agents to load, or check if they're loaded
        this.waitForAgentsAndLoadPipeline(pipelineId);
      }
    });
  }
  
  /**
   * Wait for agents and tools to be loaded, then load the pipeline
   */
  waitForAgentsAndLoadPipeline(pipelineId: string): void {
    // If agents and tools are already loaded, load pipeline immediately
    if (this.agents.length > 0 && this.tools.length > 0) {
      this.loadPipeline(pipelineId);
    } else {
      // Wait for agents and tools to load (check every 100ms, max 5 seconds)
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
          console.log('Agents loaded:', this.agents.length, 'Tools loaded:', this.tools.length);
          this.loadPipeline(pipelineId);
        }
      }, 100);
    }
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

  loadTools(): void {
    this.toolService.getTools().subscribe({
      next: (tools) => {
        this.tools = tools;
        console.log('Loaded tools:', this.tools);
      },
      error: (error) => {
        console.error('Error loading tools:', error);
        this.showNotification('Failed to load tools', 'error');
      }
    });
  }

  /**
   * Load an existing pipeline from the backend
   */
  loadPipeline(pipelineId: string): void {
    console.log('🔄 Loading pipeline:', pipelineId);
    this.loading = true;
    
    this.pipelineService.getPipeline(pipelineId).subscribe({
      next: (pipeline) => {
        console.log('✅ Pipeline loaded:', pipeline);
        
        // Set pipeline metadata
        this.pipelineName = pipeline.name || 'Untitled Pipeline';
        this.pipelineDescription = pipeline.description || '';
        
        // Load pipeline configuration
        if (pipeline.config) {
          this.selectedSymbol = pipeline.config.symbol || 'AAPL';
          this.executionMode = pipeline.config.mode || 'paper';
          
          // Load nodes onto canvas
          if (pipeline.config.nodes && Array.isArray(pipeline.config.nodes)) {
            console.log('📦 Loading nodes:', pipeline.config.nodes.length);
            this.canvasNodes = pipeline.config.nodes.map((node: any) => {
              // Find agent metadata
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
            
            console.log('✅ Nodes loaded on canvas:', this.canvasNodes);
            
            // Recreate visual tool nodes for each agent that has tools attached
            this.canvasNodes.forEach((node: CanvasNode) => {
              if (node.node_category === 'agent' && node.config && node.config['tools']) {
                const tools = node.config['tools'];
                if (Array.isArray(tools) && tools.length > 0) {
                  console.log(`🔧 Recreating ${tools.length} tool nodes for agent:`, node.agent_type);
                  
                  // Create visual tool nodes for each attached tool
                  tools.forEach((toolData: any) => {
                    this.createToolNode(toolData.tool_type, node, toolData);
                  });
                  
                  // Reposition all tools for proper alignment
                  this.repositionAllToolsForAgent(node);
                }
              }
            });
          }
          
          // Load connections
          if (pipeline.config.edges && Array.isArray(pipeline.config.edges)) {
            console.log('🔗 Loading connections:', pipeline.config.edges.length);
            this.connections = pipeline.config.edges.map((edge: any) => ({
              from: edge.from,
              to: edge.to
            }));
            
            console.log('✅ Connections loaded:', this.connections);
          }
        }
        
        this.loading = false;
        this.showNotification('Pipeline loaded successfully', 'success');
      },
      error: (error) => {
        console.error('❌ Failed to load pipeline:', error);
        this.loading = false;
        this.showNotification('Failed to load pipeline', 'error');
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
    
    this.addNodeToCanvas(agent, centerX, centerY, 'agent');
    
    // Show feedback
    this.snackBar.open(`${agent.name} added to canvas`, 'Close', {
      duration: 2000,
      horizontalPosition: 'center',
      verticalPosition: 'bottom'
    });
  }

  /**
   * Add tool to center of canvas (on double-click)
   */
  addToolToCenter(tool: ToolMetadata): void {
    const canvasRect = this.canvasRef.nativeElement.getBoundingClientRect();
    
    // Calculate center position
    const centerX = (canvasRect.width / 2) + this.canvasRef.nativeElement.scrollLeft - 100;
    const centerY = (canvasRect.height / 2) + this.canvasRef.nativeElement.scrollTop - 80;
    
    this.addNodeToCanvas(tool, centerX, centerY, 'tool');
    
    // Show feedback
    this.snackBar.open(`${tool.name} added to canvas`, 'Close', {
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
    
    // If this is an agent with attached tools, move the tools too!
    if (node.node_category === 'agent' && node.config['_toolNodeIds']) {
      const toolRefs = node.config['_toolNodeIds'] as Array<{toolType: string, nodeId: string}>;
      
      console.log('Moving agent with attached tools:', toolRefs.length);
      
      toolRefs.forEach(ref => {
        const toolNode = this.canvasNodes.find(n => n.id === ref.nodeId);
        if (toolNode) {
          // Move tool by same distance as agent
          toolNode.position.x += distance.x;
          toolNode.position.y += distance.y;
          console.log('Moved tool:', ref.toolType, 'by', distance);
        }
      });
    }
    
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
  /**
   * Add node (agent or tool) to canvas
   */
  addNodeToCanvas(item: AgentMetadata | ToolMetadata, x: number, y: number, nodeCategory: 'agent' | 'tool' = 'agent'): void {
    const newNode: CanvasNode = {
      id: `node-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      agent_type: (item as any).agent_type || (item as any).tool_type, // Use tool_type for tools
      config: {},
      position: { x, y },
      metadata: item,
      node_category: nodeCategory
    };
    
    this.canvasNodes.push(newNode);
    this.showNotification(`Added ${item.name}`, 'success');
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
    // Initialize editing config (deep copy to avoid reference issues)
    this.originalConfig = JSON.parse(JSON.stringify(node.config || {}));
    this.editingConfig = JSON.parse(JSON.stringify(node.config || {}));
  }

  /**
   * Handle configuration changes from JSON Schema form (temporary, not saved yet)
   */
  onConfigChange(config: any, node: CanvasNode): void {
    // Just update the temporary editing config, don't save to node yet
    this.editingConfig = config;
  }
  
  /**
   * Save configuration changes
   */
  saveConfigChanges(): void {
    if (this.selectedNode && this.editingConfig) {
      this.selectedNode.config = JSON.parse(JSON.stringify(this.editingConfig));
      this.originalConfig = JSON.parse(JSON.stringify(this.editingConfig));
      this.showNotification('Configuration saved', 'success');
    }
  }
  
  /**
   * Cancel configuration changes
   */
  cancelConfigChanges(): void {
    if (this.selectedNode && this.originalConfig) {
      // Restore original config
      this.editingConfig = JSON.parse(JSON.stringify(this.originalConfig));
      this.selectedNode.config = JSON.parse(JSON.stringify(this.originalConfig));
      this.showNotification('Changes cancelled', 'info');
    }
  }
  
  /**
   * Check if config has unsaved changes
   */
  hasUnsavedConfigChanges(): boolean {
    return JSON.stringify(this.editingConfig) !== JSON.stringify(this.originalConfig);
  }

  /**
   * Handle tools changes from tool selector
   * Creates visual tool nodes on canvas and connects them to the parent agent
   */
  onToolsChange(tools: any[], node: CanvasNode): void {
    if (!node.config) {
      node.config = {};
    }
    
    // Get existing visual tool nodes on canvas (the source of truth)
    const existingToolNodes = this.getToolNodesForAgent(node.id);
    const existingToolTypes = existingToolNodes.map((n: CanvasNode) => n.agent_type);
    
    // Get new tool types from the tools array
    const newToolTypes = tools.map((t: any) => t.tool_type);
    
    // Find added tools (in new list but NOT on canvas)
    const addedToolTypes = newToolTypes.filter((type: string) => !existingToolTypes.includes(type));
    
    // Find removed tools (on canvas but NOT in new list)
    const removedToolTypes = existingToolTypes.filter((type: string) => !newToolTypes.includes(type));
    
    // Update agent's config FIRST (so createToolNode can see the correct total count)
    node.config['tools'] = [...tools];
    
    // Remove visual nodes for removed tools
    removedToolTypes.forEach((toolType: string) => {
      this.removeToolNode(toolType, node);
    });
    
    // Create visual nodes for newly added tools
    addedToolTypes.forEach((toolType: string) => {
      const toolData = tools.find((t: any) => t.tool_type === toolType);
      if (toolData) {
        this.createToolNode(toolType, node, toolData);
      }
    });
    
    // IMPORTANT: Reposition ALL existing tool nodes to maintain alignment
    // This is needed because when tools are added/removed, the spacing changes
    this.repositionAllToolsForAgent(node);
    
    this.showNotification('Tools updated', 'success');
  }

  /**
   * Reposition all tool nodes for an agent to maintain proper alignment with pegs
   * Called after tools are added or removed to ensure all tools align with their pegs
   */
  private repositionAllToolsForAgent(parentAgent: CanvasNode): void {
    const toolNodes = this.getToolNodesForAgent(parentAgent.id);
    const totalTools = toolNodes.length;
    
    if (totalTools === 0) return;
    
    // Constants (must match createToolNode) - n8n-style compact design
    const AGENT_WIDTH = 160; // Updated to accommodate longer names
    const AGENT_HEIGHT = 90; // Updated for better proportions
    const TOOL_SIZE = 36; // Circular tools (diameter)
    const PEG_SIZE = 5; // Half size gray pegs
    const PEG_GAP = 40; // Tighter spacing between pegs
    const VERTICAL_GAP = 25; // Reduced gap to tools
    
    // Calculate peg positions accounting for flexbox gap
    // With flexbox, gap is between elements, so distance between centers is: PEG_SIZE + PEG_GAP
    const pegCenterDistance = PEG_SIZE + PEG_GAP; // 5 + 40 = 45px between peg centers
    
    const agentCenterX = parentAgent.position.x + (AGENT_WIDTH / 2);
    
    // Total width from first peg center to last peg center
    const totalPegsWidth = (totalTools - 1) * pegCenterDistance;
    const firstPegCenterX = agentCenterX - (totalPegsWidth / 2);
    
    // Reposition each tool
    toolNodes.forEach((toolNode, index) => {
      const thisPegCenterX = firstPegCenterX + (index * pegCenterDistance);
      const newToolX = thisPegCenterX - (TOOL_SIZE / 2);
      const newToolY = parentAgent.position.y + AGENT_HEIGHT + VERTICAL_GAP;
      
      // Update position
      toolNode.position.x = newToolX;
      toolNode.position.y = newToolY;
    });
    
    // Update connection lines
    this.updateConnectionLines();
  }

  /**
   * Create a visual tool node on canvas and connect it to parent agent
   */
  private createToolNode(toolType: string, parentAgent: CanvasNode, toolConfig: any): void {
    // Find tool metadata
    const toolMetadata = this.tools.find(t => t.tool_type === toolType);
    if (!toolMetadata) {
      console.error('Tool metadata not found for:', toolType);
      return;
    }
    
    // Calculate position for tool node
    const existingToolNodes = this.getToolNodesForAgent(parentAgent.id);
    const toolIndex = existingToolNodes.length;
    
    // Agent dimensions and position - n8n-style compact design
    const AGENT_WIDTH = 160; // Updated to accommodate longer names
    const AGENT_HEIGHT = 90; // Updated for better proportions
    const TOOL_SIZE = 36; // Circular tools (diameter)
    const TOOL_GAP = 40; // Gap between tools horizontally
    const VERTICAL_GAP = 25; // Gap between agent bottom and tool top
    
    // Get total number of tools
    const totalTools = (parentAgent.config['tools'] || []).length;
    
    // Calculate tool position to align with pegs
    // Pegs are positioned with CSS flexbox: gap between elements
    // Distance between peg centers = PEG_SIZE + PEG_GAP
    
    const PEG_SIZE = 5; // CSS .tool-peg width (half size gray pegs)
    const PEG_GAP = 40; // CSS gap between pegs
    const pegCenterDistance = PEG_SIZE + PEG_GAP; // 45px between peg centers
    
    const agentCenterX = parentAgent.position.x + (AGENT_WIDTH / 2);
    
    // Total width from first peg center to last peg center
    const totalPegsWidth = (totalTools - 1) * pegCenterDistance;
    
    // First peg center X (leftmost peg)
    const firstPegCenterX = agentCenterX - (totalPegsWidth / 2);
    
    // This peg's center X
    const thisPegCenterX = firstPegCenterX + (toolIndex * pegCenterDistance);
    
    // Tool should be centered under the peg
    // Tool is TOOL_SIZE wide, so top-left corner is at pegCenter - (TOOL_SIZE / 2)
    const toolX = thisPegCenterX - (TOOL_SIZE / 2);
    
    // Y position: below agent with gap
    const toolY = parentAgent.position.y + AGENT_HEIGHT + VERTICAL_GAP;
    
    const toolNodeId = `tool-${parentAgent.id}-${toolType}-${Date.now()}`;
    
    // Create tool node
    const toolNode: CanvasNode = {
      id: toolNodeId,
      agent_type: toolType,
      config: toolConfig.config || {},
      position: {
        x: toolX,
        y: toolY
      },
      metadata: toolMetadata,
      node_category: 'tool'
    };
    
    // Add to canvas
    this.canvasNodes.push(toolNode);
    
    // Create connection from agent to tool
    this.connections.push({
      from: parentAgent.id,
      to: toolNodeId
    });
    
    // Store reference in parent agent's config
    if (!parentAgent.config['_toolNodeIds']) {
      parentAgent.config['_toolNodeIds'] = [];
    }
    parentAgent.config['_toolNodeIds'].push({
      toolType: toolType,
      nodeId: toolNodeId
    });
    
  }

  /**
   * Get all tool nodes attached to a specific agent
   */
  private getToolNodesForAgent(agentId: string): CanvasNode[] {
    return this.canvasNodes.filter(
      node => node.node_category === 'tool' && 
      this.connections.some(conn => conn.from === agentId && conn.to === node.id)
    );
  }

  /**
   * Remove a visual tool node and its connection
   */
  private removeToolNode(toolType: string, parentAgent: CanvasNode): void {
    const toolNodeMapping = parentAgent.config['_toolNodeIds']?.find(
      (mapping: any) => mapping.toolType === toolType
    );
    
    if (toolNodeMapping) {
      const nodeId = toolNodeMapping.nodeId;
      
      // Remove the node from canvas
      this.canvasNodes = this.canvasNodes.filter(n => n.id !== nodeId);
      
      // Remove connections
      this.connections = this.connections.filter(c => 
        c.from !== nodeId && c.to !== nodeId
      );
      
      // Remove from parent's reference list
      parentAgent.config['_toolNodeIds'] = parentAgent.config['_toolNodeIds'].filter(
        (mapping: any) => mapping.toolType !== toolType
      );
    }
  }

  /**
   * Check if a node is an agent (has supported_tools property)
   */
  isAgentNode(node: CanvasNode): boolean {
    return node.node_category === 'agent' && 'supported_tools' in (node.metadata || {});
  }

  /**
   * Get supported tools for an agent node (type-safe)
   */
  getAgentSupportedTools(node: CanvasNode): string[] {
    if (this.isAgentNode(node)) {
      return (node.metadata as AgentMetadata)?.supported_tools || [];
    }
    return [];
  }

  /**
   * Get agent metadata (type-safe cast)
   */
  getAgentMetadata(node: CanvasNode): AgentMetadata | null {
    if (this.isAgentNode(node)) {
      return node.metadata as AgentMetadata;
    }
    return null;
  }

  /**
   * Get tool metadata (type-safe cast)
   */
  getToolMetadata(node: CanvasNode): ToolMetadata | null {
    if (node.node_category === 'tool') {
      return node.metadata as ToolMetadata;
    }
    return null;
  }

  /**
   * Remove node from canvas
   */
  removeNode(nodeId: string): void {
    const nodeToRemove = this.canvasNodes.find(n => n.id === nodeId);
    
    // If removing an agent, also remove all its attached tools
    if (nodeToRemove && nodeToRemove.node_category === 'agent') {
      const toolNodes = this.getToolNodesForAgent(nodeId);
      toolNodes.forEach(toolNode => {
        // Remove tool node
        this.canvasNodes = this.canvasNodes.filter(n => n.id !== toolNode.id);
        // Remove tool connections
        this.connections = this.connections.filter(
          c => c.from !== toolNode.id && c.to !== toolNode.id
        );
      });
    }
    
    // Remove the node itself
    this.canvasNodes = this.canvasNodes.filter(n => n.id !== nodeId);
    
    // Remove connections to/from this node
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

    // Check if toNode is a tool (tools should have straight VERTICAL lines from agent)
    const isToolConnection = toNode.node_category === 'tool';
    
    if (isToolConnection) {
      // Straight vertical line (90 degrees) from peg to tool
      // Constants must match createToolNode
      const AGENT_WIDTH = 160; // Updated to match new card size
      const AGENT_HEIGHT = 90; // Updated to match new card size
      const TOOL_SIZE = 36;
      const PEG_OFFSET = 2.5; // Peg is at bottom: -2.5px in CSS (center of diamond)
      
      // Tool center X
      const toolCenterX = toNode.position.x + (TOOL_SIZE / 2);
      
      // Peg Y: agent bottom + peg offset (center of the diamond peg)
      const pegY = fromNode.position.y + AGENT_HEIGHT + PEG_OFFSET;
      
      // Tool top edge
      const toolTopY = toNode.position.y;
      
      // Perfectly vertical line: same X for start and end
      return `M ${toolCenterX} ${pegY} L ${toolCenterX} ${toolTopY}`;
    }

    // For agent-to-agent connections, use curved Bezier path
    // Connect from right side of source to left side of target
    const AGENT_WIDTH = 160; // Updated to match new card size
    const AGENT_HEIGHT = 90; // Updated to match new card size
    
    const fromX = fromNode.position.x + AGENT_WIDTH; // Right edge of source node
    const fromY = fromNode.position.y + (AGENT_HEIGHT / 2); // Middle (vertical center)
    const toX = toNode.position.x; // Left edge of target node
    const toY = toNode.position.y + (AGENT_HEIGHT / 2); // Middle (vertical center)

    // Bezier curve for smooth horizontal connection
    const midX = (fromX + toX) / 2;
    return `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`;
  }

  /**
   * Check if a connection is to a tool (for styling purposes)
   */
  isToolConnection(connection: Connection): boolean {
    const toNode = this.canvasNodes.find(n => n.id === connection.to);
    return toNode?.node_category === 'tool';
  }

  /**
   * Calculate total pipeline cost (only agents have pricing)
   */
  calculateTotalCost(): number {
    return this.canvasNodes.reduce((total, node) => {
      const agentMeta = this.getAgentMetadata(node);
      return total + (agentMeta?.pricing_rate || 0);
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
    // Check if user is authenticated
    const token = localStorage.getItem('auth_token');
    if (!token) {
      this.showNotification('Please login to save pipelines', 'warning');
      this.router.navigate(['/login']);
      return;
    }

    // Filter out tool nodes - only save agent nodes
    const agentNodes = this.canvasNodes.filter(node => node.node_category !== 'tool');
    
    if (agentNodes.length === 0) {
      this.showNotification('Please add at least one agent', 'warning');
      return;
    }

    // Filter connections to only include agent-to-agent connections (exclude tool connections)
    const agentConnections = this.connections.filter(conn => {
      const fromNode = this.canvasNodes.find(n => n.id === conn.from);
      const toNode = this.canvasNodes.find(n => n.id === conn.to);
      return fromNode?.node_category !== 'tool' && toNode?.node_category !== 'tool';
    });

    this.saving = true;
    const pipelineData: any = {
      name: this.pipelineName,
      description: this.pipelineDescription,
      config: {
        nodes: agentNodes.map(node => ({
          id: node.id,
          agent_type: node.agent_type,
          config: node.config,
          position: node.position,
          node_category: node.node_category // Include category for clarity
        })),
        edges: agentConnections.map(conn => ({
          from: conn.from,
          to: conn.to
        })),
        symbol: this.selectedSymbol,
        mode: this.executionMode
      },
      is_active: false
    };

    console.log('Saving pipeline:', pipelineData); // Debug log

    // Determine if we're updating or creating
    const saveOperation = this.currentPipelineId
      ? this.pipelineService.updatePipeline(this.currentPipelineId, pipelineData)
      : this.pipelineService.createPipeline(pipelineData);

    saveOperation.subscribe({
      next: (pipeline: any) => {
        this.saving = false;
        
        // If this was a new pipeline, store its ID
        if (!this.currentPipelineId && pipeline.id) {
          this.currentPipelineId = pipeline.id;
          // Update the URL without reloading the page
          this.router.navigate(['/pipeline-builder', pipeline.id], { replaceUrl: true });
        }
        
        this.showNotification('Pipeline saved successfully!', 'success');
        console.log('Pipeline saved:', pipeline);
      },
      error: (error: any) => {
        this.saving = false;
        this.showNotification('Failed to save pipeline', 'error');
        console.error('Save error:', error);
        // Show more detailed error message
        if (error.error?.detail) {
          console.error('Error details:', error.error.detail);
        }
      }
    });
  }

  /**
   * Execute pipeline
   */
  executePipeline(): void {
    // Filter out tool nodes - only execute agent nodes
    const agentNodes = this.canvasNodes.filter(node => node.node_category !== 'tool');
    
    if (agentNodes.length === 0) {
      this.showNotification('Please add agents to the pipeline', 'warning');
      return;
    }

    // Filter connections to only include agent-to-agent connections (exclude tool connections)
    const agentConnections = this.connections.filter(conn => {
      const fromNode = this.canvasNodes.find(n => n.id === conn.from);
      const toNode = this.canvasNodes.find(n => n.id === conn.to);
      return fromNode?.node_category !== 'tool' && toNode?.node_category !== 'tool';
    });

    this.executing = true;

    // If we have a currentPipelineId, just execute the existing pipeline
    if (this.currentPipelineId) {
      const executionData: any = {
        pipeline_id: this.currentPipelineId,
        symbol: this.selectedSymbol,
        mode: this.executionMode as 'live' | 'paper' | 'simulation' | 'validation'
      };

      console.log('Executing existing pipeline:', this.currentPipelineId);

      this.executionService.startExecution(executionData).subscribe({
        next: (execution: any) => {
          this.executing = false;
          this.showNotification('Pipeline execution started!', 'success');
          console.log('Execution started:', execution);
        },
        error: (error: any) => {
          this.executing = false;
          this.handleExecutionError(error);
        }
      });
      return;
    }

    // No currentPipelineId, so save the pipeline first, then execute
    const pipelineData: any = {
      name: this.pipelineName,
      description: this.pipelineDescription,
      config: {
        nodes: agentNodes.map(node => ({
          id: node.id,
          agent_type: node.agent_type,
          config: node.config,
          position: node.position,
          node_category: node.node_category
        })),
        edges: agentConnections.map(conn => ({
          from: conn.from,
          to: conn.to
        })),
        symbol: this.selectedSymbol,
        mode: this.executionMode
      },
      is_active: false
    };

    console.log('Creating new pipeline for execution:', pipelineData);

    this.pipelineService.createPipeline(pipelineData).subscribe({
      next: (pipeline: any) => {
        // Store the pipeline ID for future executions
        this.currentPipelineId = pipeline.id;

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
            this.handleExecutionError(error);
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
   * Handle execution errors with friendly validation messages
   */
  private handleExecutionError(error: any): void {
    console.error('Execution error:', error);
    
    // Check if this is a validation error (400 with errors array)
    if (error.status === 400 && error.error?.detail?.errors) {
      const errors = error.error.detail.errors;
      
      // Show validation error dialog
      this.dialog.open(ValidationErrorDialogComponent, {
        width: '600px',
        data: { errors }
      });
    } else {
      // Generic error
      const message = error.error?.detail?.message || error.error?.message || 'Failed to start execution';
      this.showNotification(message, 'error');
    }
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

  /**
   * Check if an agent has a tool attached at a specific peg index
   */
  hasToolAttached(node: CanvasNode, pegIndex: number): boolean {
    const tools = node.config['tools'] || [];
    return pegIndex < tools.length;
  }

  /**
   * Helper to expose Math to the template
   */
  Math = Math;
}
