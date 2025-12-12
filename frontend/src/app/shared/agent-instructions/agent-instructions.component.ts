import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';
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
import { FileUploadService, FileUploadResponse } from '../../core/services/file-upload.service';

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
export class AgentInstructionsComponent implements OnInit, OnDestroy {
  @Input() agentType: string = 'strategy';
  @Input() initialInstructions: string = '';
  @Input() initialDocumentUrl: string = '';
  
  @Output() instructionsChange = new EventEmitter<{
    instructions: string;
    documentUrl: string;
    detectedTools: DetectedTool[];
    totalCost: number;
  }>();

  instructions: string = '';
  documentUrl: string = '';
  uploadedFileName: string = '';
  
  detecting: boolean = false;
  detectedTools: DetectedTool[] = [];
  unsupportedFeatures: string[] = [];
  totalCost: number = 0;
  llmCost: number = 0;
  summary: string = '';
  confidence: number = 0;
  detectionStatus: 'success' | 'partial' | 'error' | 'none' = 'none';
  errorMessage: string = '';
  
  uploading: boolean = false;
  
  private destroy$ = new Subject<void>();
  private instructionsChanged$ = new Subject<string>();

  constructor(
    private toolDetectionService: ToolDetectionService,
    private fileUploadService: FileUploadService
  ) {}

  ngOnInit(): void {
    // Initialize with existing values
    this.instructions = this.initialInstructions;
    this.documentUrl = this.initialDocumentUrl;

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

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onInstructionsInput(value: string): void {
    this.instructions = value;
    this.instructionsChanged$.next(value);
  }

  async detectTools(): Promise<void> {
    if (!this.instructions || this.instructions.length < 20) {
      this.detectionStatus = 'none';
      return;
    }

    this.detecting = true;
    this.detectionStatus = 'none';

    this.toolDetectionService.validateInstructions(this.instructions, this.agentType)
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

  onFileSelected(event: any): void {
    const file: File = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (file.type !== 'application/pdf') {
      alert('Only PDF files are supported');
      return;
    }

    // Validate file size (max 10MB)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      alert('File too large. Maximum size: 10MB');
      return;
    }

    this.uploading = true;

    this.fileUploadService.uploadFile(file, true).subscribe({
      next: (response: FileUploadResponse) => {
        this.uploading = false;
        this.documentUrl = response.file_url;
        this.uploadedFileName = response.filename;

        // If PDF text was extracted, append to instructions
        if (response.extracted_text) {
          if (this.instructions) {
            this.instructions += '\n\n--- Strategy Document ---\n' + response.extracted_text;
          } else {
            this.instructions = response.extracted_text;
          }

          // Trigger tool detection
          this.instructionsChanged$.next(this.instructions);
        }

        this.emitChanges();
      },
      error: (error) => {
        this.uploading = false;
        console.error('File upload failed:', error);
        alert('File upload failed: ' + (error.error?.detail || 'Unknown error'));
      }
    });
  }

  removeDocument(): void {
    if (this.documentUrl) {
      this.fileUploadService.deleteFile(this.documentUrl).subscribe({
        next: () => {
          this.documentUrl = '';
          this.uploadedFileName = '';
          this.emitChanges();
        },
        error: (error) => {
          console.error('File deletion failed:', error);
        }
      });
    }
  }

  private emitChanges(): void {
    this.instructionsChange.emit({
      instructions: this.instructions,
      documentUrl: this.documentUrl,
      detectedTools: this.detectedTools,
      totalCost: this.totalCost
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
    switch (this.detectionStatus) {
      case 'success': return 'check_circle';
      case 'partial': return 'warning';
      case 'error': return 'error';
      default: return '';
    }
  }

  getStatusColor(): string {
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

