/**
 * Execution Report Modal Component
 * 
 * Displays a comprehensive AI-generated executive report with all agent details,
 * charts, and actionable recommendations
 */

import { Component, Inject, OnInit, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatTabsModule } from '@angular/material/tabs';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

import { TradingChartComponent } from '../../../shared/components/trading-chart/trading-chart.component';
import { ApiService } from '../../../core/services/api.service';

@Component({
  selector: 'app-execution-report-modal',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatExpansionModule,
    MatTabsModule,
    TradingChartComponent,
  ],
  templateUrl: './execution-report-modal.component.html',
  styleUrls: ['./execution-report-modal.component.scss']
})
export class ExecutionReportModalComponent implements OnInit {
  @ViewChild('reportContent', { static: false }) reportContent!: ElementRef;
  
  execution: any;
  executiveReport: any = null;
  loading = true;
  error: string | null = null;
  generatingPdf = false;

  constructor(
    public dialogRef: MatDialogRef<ExecutionReportModalComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
    private apiService: ApiService
  ) {
    this.execution = data.execution;
  }

  ngOnInit(): void {
    this.loadExecutiveReport();
  }

  loadExecutiveReport(): void {
    console.log('Loading executive report for execution:', this.execution.id);
    this.apiService.get(`/api/v1/executions/${this.execution.id}/executive-report`).subscribe({
      next: (report) => {
        console.log('Executive report received:', report);
        this.executiveReport = report;
        this.loading = false;
      },
      error: (error) => {
        console.error('Failed to generate report:', error);
        this.error = error.error?.detail || error.message || 'Failed to generate executive report';
        this.loading = false;
      }
    });
  }

  close(): void {
    this.dialogRef.close();
  }

  async downloadReport(): Promise<void> {
    if (!this.reportContent) {
      console.error('Report content not available');
      return;
    }

    this.generatingPdf = true;

    try {
      // Get the modal content element
      const element = this.reportContent.nativeElement;
      
      // Expand all accordion panels before capturing
      const panels = element.querySelectorAll('mat-expansion-panel');
      panels.forEach((panel: any) => {
        if (!panel.classList.contains('mat-expanded')) {
          panel.click();
        }
      });

      // Wait for animations to complete
      await new Promise(resolve => setTimeout(resolve, 500));

      // Configure html2canvas options for better quality
      const canvas = await html2canvas(element, {
        scale: 2, // Higher quality
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
        width: element.scrollWidth,
        height: element.scrollHeight,
      });

      // Calculate PDF dimensions
      const imgWidth = 210; // A4 width in mm
      const pageHeight = 297; // A4 height in mm
      const imgHeight = (canvas.height * imgWidth) / canvas.width;
      let heightLeft = imgHeight;

      // Create PDF
      const pdf = new jsPDF('p', 'mm', 'a4');
      let position = 0;

      // Add image to PDF (handle multiple pages if needed)
      const imgData = canvas.toDataURL('image/png');
      
      // First page
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight);
      heightLeft -= pageHeight;

      // Add additional pages if content is longer than one page
      while (heightLeft > 0) {
        position = heightLeft - imgHeight;
        pdf.addPage();
        pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight);
        heightLeft -= pageHeight;
      }

      // Generate filename
      const timestamp = new Date().toISOString().split('T')[0];
      const filename = `execution-report-${this.execution.symbol || 'unknown'}-${timestamp}.pdf`;

      // Save the PDF
      pdf.save(filename);

      console.log('PDF generated successfully');
    } catch (error) {
      console.error('Error generating PDF:', error);
      alert('Failed to generate PDF. Please try again.');
    } finally {
      this.generatingPdf = false;
    }
  }


  formatDuration(seconds: number | undefined): string {
    if (!seconds) return '-';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  }

  getStatusClass(): string {
    return `status-${this.execution.status.toLowerCase()}`;
  }

  hasChart(): boolean {
    return this.executiveReport?.execution_artifacts?.strategy_chart;
  }

  getChartData(): any {
    return this.executiveReport?.execution_artifacts?.strategy_chart;
  }

  isArray(value: any): boolean {
    return Array.isArray(value);
  }

  isObject(value: any): boolean {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }
}
