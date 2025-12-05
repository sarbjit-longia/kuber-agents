  /**
   * Remove a node from the canvas
   */
  removeNode(nodeId: string): void {
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
          this.showNotification('Pipeline execution started! Redirecting to monitoring...', 'success');
          console.log('Execution started:', execution);
          // Navigate to execution detail page to see real-time progress
          setTimeout(() => {
            this.router.navigate(['/monitoring', execution.id]);
          }, 1500);
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
            this.showNotification('Pipeline execution started! Redirecting to monitoring...', 'success');
            console.log('Execution started:', execution);
            // Navigate to execution detail page to see real-time progress
            setTimeout(() => {
              this.router.navigate(['/monitoring', execution.id]);
            }, 1500);
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
    if (!node || !node.config) return false;
    const tools = node.config['tools'] || [];
    return pegIndex < tools.length;
  }

  /**
   * Helper to expose Math to the template
   */
  Math = Math;
}
