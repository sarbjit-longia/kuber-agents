import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

import { ToolDetectionService, DetectedTool, ValidateInstructionsResponse } from '../../core/services/tool-detection.service';
import { CostEstimationService, LLMCostEstimate } from '../../core/services/cost-estimation.service';

@Component({
  selector: 'app-agent-instructions',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatChipsModule,
    MatTooltipModule
  ],
  templateUrl: './agent-instructions.component.html',
  styleUrls: ['./agent-instructions.component.scss']
})
export class AgentInstructionsComponent implements OnInit, OnDestroy, OnChanges {
  @Input() agentType: string = 'strategy';
  @Input() initialInstructions: string = '';
  @Input() autoDetect: boolean = true;
  @Input() showDetectButton: boolean = false;
  @Input() selectedModel: string = '';
  @Input() staticAgentCost: number = 0;
  @Input() attachedSkillIds: string[] = [];
  
  @Output() instructionsChange = new EventEmitter<{
    instructions: string;
    detectedTools: DetectedTool[];
    totalCost: number;
    llmCost: number;
  }>();

  instructions: string = '';
  
  detecting: boolean = false;
  detectedTools: DetectedTool[] = [];
  unsupportedFeatures: string[] = [];
  totalCost: number = 0;
  llmCost: number = 0;
  estimatedLLMCost: LLMCostEstimate | null = null;
  summary: string = '';
  confidence: number = 0;
  detectionStatus: 'success' | 'partial' | 'error' | 'none' = 'none';
  errorMessage: string = '';

  private destroy$ = new Subject<void>();
  private instructionsChanged$ = new Subject<string>();

  constructor(
    private toolDetectionService: ToolDetectionService,
    private costEstimationService: CostEstimationService
  ) {}

  ngOnInit(): void {
    // Initialize with existing values
    this.instructions = this.initialInstructions;

    // Compute initial cost estimate if model + instructions are already set
    this.recomputeLocalLLMCost();
    this.emitChanges();

    // If pricing data hasn't loaded yet, recalculate when it arrives
    this.costEstimationService.pricingLoaded$
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        this.recomputeLocalLLMCost();
        this.emitChanges();
      });

    if (this.autoDetect) {
      // Debounced tool detection (wait 2 seconds after user stops typing)
      this.instructionsChanged$
        .pipe(
          debounceTime(2000),
          distinctUntilChanged(),
          takeUntil(this.destroy$)
        )
        .subscribe(instructions => {
          if (instructions && instructions.length >= 20) {
            this.detectTools();
          }
        });
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    // Update instructions when initialInstructions input changes
    if (changes['initialInstructions'] && !changes['initialInstructions'].firstChange) {
      this.instructions = changes['initialInstructions'].currentValue || '';
    }

    // Recalculate LLM cost when model changes (including first render)
    if (changes['selectedModel']) {
      this.recomputeLocalLLMCost();
      this.emitChanges();
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onInstructionsInput(value: string): void {
    this.instructions = value;

    // If user edits instructions, any previously detected tools/summary are now stale.
    // Clear them immediately so we don't accidentally persist outdated tool configs.
    this.detectedTools = [];
    this.unsupportedFeatures = [];
    this.totalCost = 0;
    this.llmCost = 0;
    this.summary = '';
    this.confidence = 0;
    this.detectionStatus = 'none';
    this.errorMessage = '';

    // Compute local LLM cost estimate (pure math, no debounce needed)
    this.recomputeLocalLLMCost();

    this.instructionsChanged$.next(value);
    // Always emit on input so parent builders can persist instructions even when
    // auto-detect is disabled (guided builder uses manual "Detect tools").
    this.emitChanges();
  }

  async detectTools(): Promise<void> {
    if (!this.instructions || this.instructions.length < 20) {
      this.detectionStatus = 'none';
      return;
    }

    this.detecting = true;
    this.detectionStatus = 'none';

    this.toolDetectionService.validateInstructions(this.instructions, this.agentType, this.attachedSkillIds)
      .subscribe({
        next: (response: ValidateInstructionsResponse) => {
          this.detecting = false;
          this.detectionStatus = response.status;
          this.detectedTools = response.tools;
          this.unsupportedFeatures = response.unsupported;
          this.totalCost = response.total_cost;
          this.llmCost = response.llm_cost || 0;
          this.summary = response.summary || '';
          this.confidence = response.confidence || 0;
          this.errorMessage = response.message || '';

          // Emit changes to parent
          this.emitChanges();
        },
        error: (error) => {
          this.detecting = false;
          this.detectionStatus = 'error';
          
          // Better error message extraction
          let errorMsg = 'Detection failed';
          if (error.error) {
            if (typeof error.error === 'string') {
              errorMsg = error.error;
            } else if (error.error.detail) {
              errorMsg = typeof error.error.detail === 'string' 
                ? error.error.detail 
                : JSON.stringify(error.error.detail);
            } else if (error.error.message) {
              errorMsg = error.error.message;
            } else {
              errorMsg = JSON.stringify(error.error);
            }
          } else if (error.message) {
            errorMsg = error.message;
          } else if (error.statusText) {
            errorMsg = `${error.status || ''} ${error.statusText}`.trim();
          }
          
          this.errorMessage = errorMsg;
          console.error('Tool detection failed:', error);
          console.error('Error details:', JSON.stringify(error, null, 2));
        }
      });
  }

  private recomputeLocalLLMCost(): void {
    if (this.selectedModel && this.instructions) {
      this.estimatedLLMCost = this.costEstimationService.estimateLLMCost(
        this.instructions,
        this.selectedModel,
        this.agentType
      );
    } else {
      this.estimatedLLMCost = null;
    }
  }

  /** Total estimated cost per execution (static + tools + LLM) */
  get totalEstimatedCost(): number {
    const toolsCost = this.totalCost;
    const agentCost = this.staticAgentCost || 0;
    const llm = this.estimatedLLMCost?.totalLLMCost || 0;
    return toolsCost + agentCost + llm;
  }

  private emitChanges(): void {
    this.instructionsChange.emit({
      instructions: this.instructions,
      detectedTools: this.detectedTools,
      totalCost: this.totalCost,
      llmCost: this.estimatedLLMCost?.totalLLMCost || this.llmCost
    });
  }

  getCategoryIcon(category: string): string {
    const icons: Record<string, string> = {
      'ict': 'analytics',
      'indicator': 'show_chart',
      'price_action': 'candlestick_chart'
    };
    return icons[category] || 'extension';
  }

  getStatusIcon(): string {
    // Show info icon if status is success but no tools detected (manual attachment required)
    if (this.detectionStatus === 'success' && this.detectedTools.length === 0) {
      return 'info';
    }
    
    switch (this.detectionStatus) {
      case 'success': return 'check_circle';
      case 'partial': return 'warning';
      case 'error': return 'error';
      default: return '';
    }
  }

  getStatusColor(): string {
    // Show primary color for info state (success but no tools)
    if (this.detectionStatus === 'success' && this.detectedTools.length === 0) {
      return 'primary';
    }
    
    switch (this.detectionStatus) {
      case 'success': return 'accent';
      case 'partial': return 'warn';
      case 'error': return 'warn';
      default: return '';
    }
  }

  formatParams(params: Record<string, any>): string {
    if (!params || Object.keys(params).length === 0) {
      return '';
    }
    return Object.entries(params)
      .map(([key, value]) => `${key}: ${value}`)
      .join(', ');
  }
}
