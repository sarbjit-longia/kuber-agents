import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatChipsModule } from '@angular/material/chips';
import { ToolService, ToolMetadata } from '../../core/services/tool.service';

export interface ToolInstance {
  tool_type: string;
  enabled: boolean;
  config: any;
  metadata?: ToolMetadata;
}

@Component({
  selector: 'app-tool-selector',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatMenuModule,
    MatTooltipModule,
    MatDialogModule,
    MatSnackBarModule,
    MatChipsModule
  ],
  templateUrl: './tool-selector.component.html',
  styleUrls: ['./tool-selector.component.scss']
})
export class ToolSelectorComponent implements OnInit, OnChanges {
  @Input() supportedTools: string[] = [];  // List of tool types this agent supports
  @Input() attachedTools: ToolInstance[] = [];  // Currently attached tools
  @Output() toolsChange = new EventEmitter<ToolInstance[]>();

  availableTools: ToolMetadata[] = [];
  loading = false;

  // Broker tool types that are mutually exclusive
  private readonly BROKER_TOOLS = ['alpaca_broker', 'oanda_broker', 'tradier_broker'];

  constructor(
    private toolService: ToolService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.loadAvailableTools();
    // Enrich attached tools with metadata
    this.enrichToolMetadata();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['attachedTools'] && this.availableTools.length > 0) {
      this.enrichToolMetadata();
    }
  }

  loadAvailableTools(): void {
    this.loading = true;
    this.toolService.getTools().subscribe({
      next: (tools) => {
        console.log('All tools from API:', tools);
        console.log('Supported tools for this agent:', this.supportedTools);
        // Filter to only show supported tools
        this.availableTools = tools.filter(tool => 
          this.supportedTools.includes(tool.tool_type)
        );
        console.log('Filtered available tools:', this.availableTools);
        this.enrichToolMetadata();
        this.loading = false;
      },
      error: (error) => {
        console.error('Failed to load tools:', error);
        this.loading = false;
      }
    });
  }

  enrichToolMetadata(): void {
    console.log('Enriching metadata for attached tools:', this.attachedTools);
    // Add metadata to attached tools
    this.attachedTools.forEach(tool => {
      if (!tool.metadata) {
        tool.metadata = this.availableTools.find(t => t.tool_type === tool.tool_type);
      }
    });
    console.log('Attached tools after enrichment:', this.attachedTools);
  }

  addTool(toolType: string): void {
    const toolMetadata = this.availableTools.find(t => t.tool_type === toolType);
    if (!toolMetadata) return;

    // Check if tool is already attached
    if (this.attachedTools.some(t => t.tool_type === toolType)) {
      return;
    }

    // ⚠️ BROKER VALIDATION: Prevent multiple brokers
    if (this.BROKER_TOOLS.includes(toolType)) {
      const attachedBroker = this.attachedTools.find(t => this.BROKER_TOOLS.includes(t.tool_type));
      if (attachedBroker) {
        const brokerNames: { [key: string]: string } = {
          'alpaca_broker': 'Alpaca',
          'oanda_broker': 'Oanda',
          'tradier_broker': 'Tradier'
        };
        const currentBrokerName = brokerNames[attachedBroker.tool_type] || attachedBroker.tool_type;
        const newBrokerName = brokerNames[toolType] || toolType;
        
        this.snackBar.open(
          `⚠️ Only one broker allowed! ${currentBrokerName} is already attached. Remove it first to add ${newBrokerName}.`,
          'Close',
          {
            duration: 5000,
            horizontalPosition: 'center',
            verticalPosition: 'top',
            panelClass: ['error-snackbar']
          }
        );
        return;
      }
    }

    const newTool: ToolInstance = {
      tool_type: toolType,
      enabled: true,
      config: {},
      metadata: toolMetadata
    };

    this.attachedTools.push(newTool);
    this.emitChange();
  }

  removeTool(toolType: string): void {
    this.attachedTools = this.attachedTools.filter(t => t.tool_type !== toolType);
    this.emitChange();
  }

  emitChange(): void {
    // Emit tools without metadata (backend doesn't need it)
    const toolsForBackend = this.attachedTools.map(({ tool_type, enabled, config }) => ({
      tool_type,
      enabled,
      config
    }));
    this.toolsChange.emit(toolsForBackend as ToolInstance[]);
  }

  getAvailableToolsForMenu(): ToolMetadata[] {
    // Return tools that are not yet attached
    const available = this.availableTools.filter(tool => 
      !this.attachedTools.some(t => t.tool_type === tool.tool_type)
    );
    //console.log('Available tools for menu:', available);
    //console.log('Already attached tools:', this.attachedTools.map(t => t.tool_type));
    return available;
  }

  /**
   * Check if a tool should be disabled in the menu (e.g., broker when another broker is attached)
   */
  isToolDisabled(toolType: string): boolean {
    if (this.BROKER_TOOLS.includes(toolType)) {
      // If this is a broker tool, disable it if another broker is already attached
      return this.attachedTools.some(t => 
        this.BROKER_TOOLS.includes(t.tool_type) && t.tool_type !== toolType
      );
    }
    return false;
  }

  /**
   * Get a tooltip explaining why a tool is disabled
   */
  getDisabledTooltip(toolType: string): string {
    if (this.isToolDisabled(toolType) && this.BROKER_TOOLS.includes(toolType)) {
      const attachedBroker = this.attachedTools.find(t => this.BROKER_TOOLS.includes(t.tool_type));
      if (attachedBroker) {
        const brokerNames: { [key: string]: string } = {
          'alpaca_broker': 'Alpaca',
          'oanda_broker': 'Oanda',
          'tradier_broker': 'Tradier'
        };
        const currentBrokerName = brokerNames[attachedBroker.tool_type] || attachedBroker.tool_type;
        return `Only one broker allowed. ${currentBrokerName} is already attached. Remove it first.`;
      }
    }
    return '';
  }
}
