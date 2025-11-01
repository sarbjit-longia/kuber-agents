import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { ToolService, ToolMetadata } from '../../core/services/tool.service';
import { JsonSchemaFormComponent } from '../json-schema-form/json-schema-form.component';

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
    JsonSchemaFormComponent
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

  constructor(
    private toolService: ToolService,
    private dialog: MatDialog
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

  toggleTool(toolType: string): void {
    const tool = this.attachedTools.find(t => t.tool_type === toolType);
    if (tool) {
      tool.enabled = !tool.enabled;
      this.emitChange();
    }
  }

  onToolConfigChange(config: any, tool: ToolInstance): void {
    tool.config = config;
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
    console.log('Available tools for menu:', available);
    console.log('Already attached tools:', this.attachedTools.map(t => t.tool_type));
    return available;
  }
}
