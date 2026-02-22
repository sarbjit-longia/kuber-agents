/**
 * Scanner Management Component
 *
 * Main page for managing scanners (ticker lists).
 */
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { FormsModule } from '@angular/forms';
import { Scanner, ScannerCreate } from '../../core/models/scanner.model';
import { ScannerService } from '../../core/services/scanner.service';
import { CreateScannerDialogComponent } from './create-scanner-dialog/create-scanner-dialog.component';
import { ConfirmDialogComponent, ConfirmDialogData } from '../../shared/confirm-dialog/confirm-dialog.component';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../shared/components/footer/footer.component';
import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';

@Component({
  selector: 'app-scanner-management',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatSnackBarModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatChipsModule,
    MatMenuModule,
    MatProgressSpinnerModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    NavbarComponent,
    FooterComponent,
    CreateScannerDialogComponent,
    LocalDatePipe
  ],
  templateUrl: './scanner-management.component.html',
  styleUrls: ['./scanner-management.component.scss']
})
export class ScannerManagementComponent implements OnInit {
  allScanners: Scanner[] = [];
  scanners: Scanner[] = [];
  loading = false;
  filterActive: boolean | undefined = undefined;
  searchQuery = '';

  constructor(
    private scannerService: ScannerService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.loadScanners();
  }

  get activeCount(): number {
    return this.allScanners.filter(s => s.is_active).length;
  }

  get inactiveCount(): number {
    return this.allScanners.filter(s => !s.is_active).length;
  }

  get filteredScanners(): Scanner[] {
    if (!this.searchQuery) {
      return this.scanners;
    }
    const query = this.searchQuery.toLowerCase();
    return this.scanners.filter(s =>
      s.name.toLowerCase().includes(query) ||
      (s.description && s.description.toLowerCase().includes(query)) ||
      (s.config?.tickers && s.config.tickers.some(t => t.toLowerCase().includes(query)))
    );
  }

  loadScanners(): void {
    this.loading = true;
    this.scannerService.getScanners().subscribe({
      next: (scanners) => {
        this.allScanners = scanners;
        this.applyClientFilter();
        this.loading = false;
      },
      error: (error) => {
        console.error('Failed to load scanners:', error);
        this.snackBar.open('Failed to load scanners', 'Close', { duration: 3000 });
        this.loading = false;
      }
    });
  }

  openCreateDialog(): void {
    const dialogRef = this.dialog.open(CreateScannerDialogComponent, {
      width: '720px',
      data: {}
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        this.createScanner(result);
      }
    });
  }

  openEditDialog(scanner: Scanner): void {
    const dialogRef = this.dialog.open(CreateScannerDialogComponent, {
      width: '720px',
      data: { scanner }
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        this.updateScanner(scanner.id, result);
      }
    });
  }

  createScanner(scannerData: ScannerCreate): void {
    this.scannerService.createScanner(scannerData).subscribe({
      next: () => {
        this.snackBar.open('Scanner created successfully', 'Close', { duration: 3000 });
        this.loadScanners();
      },
      error: (error) => {
        console.error('Failed to create scanner:', error);
        const message = error.error?.detail || 'Failed to create scanner';
        this.snackBar.open(message, 'Close', { duration: 5000 });
      }
    });
  }

  updateScanner(scannerId: string, updates: any): void {
    this.scannerService.updateScanner(scannerId, updates).subscribe({
      next: () => {
        this.snackBar.open('Scanner updated successfully', 'Close', { duration: 3000 });
        this.loadScanners();
      },
      error: (error) => {
        console.error('Failed to update scanner:', error);
        const message = error.error?.detail || 'Failed to update scanner';
        this.snackBar.open(message, 'Close', { duration: 5000 });
      }
    });
  }

  deleteScanner(scanner: Scanner): void {
    this.scannerService.getScannerUsage(scanner.id).subscribe({
      next: (usage) => {
        let message = `Are you sure you want to delete "${scanner.name}"?`;
        if (usage.pipeline_count > 0) {
          const pipelineNames = usage.pipelines.map(p => p.name).join(', ');
          message += `\n\nThis scanner is used by ${usage.pipeline_count} pipeline${usage.pipeline_count > 1 ? 's' : ''}: ${pipelineNames}`;
        }

        const dialogRef = this.dialog.open(ConfirmDialogComponent, {
          width: '440px',
          data: {
            title: 'Delete Scanner',
            message,
            confirmText: 'Delete',
            cancelText: 'Cancel'
          } as ConfirmDialogData
        });

        dialogRef.afterClosed().subscribe(confirmed => {
          if (confirmed) {
            this.performDelete(scanner);
          }
        });
      },
      error: () => {
        // If usage check fails, still allow delete with basic confirm
        const dialogRef = this.dialog.open(ConfirmDialogComponent, {
          width: '440px',
          data: {
            title: 'Delete Scanner',
            message: `Are you sure you want to delete "${scanner.name}"?`,
            confirmText: 'Delete',
            cancelText: 'Cancel'
          } as ConfirmDialogData
        });

        dialogRef.afterClosed().subscribe(confirmed => {
          if (confirmed) {
            this.performDelete(scanner);
          }
        });
      }
    });
  }

  private performDelete(scanner: Scanner): void {
    this.scannerService.deleteScanner(scanner.id).subscribe({
      next: () => {
        this.snackBar.open('Scanner deleted successfully', 'Close', { duration: 3000 });
        this.loadScanners();
      },
      error: (error) => {
        console.error('Failed to delete scanner:', error);
        const message = error.error?.detail || 'Failed to delete scanner';
        this.snackBar.open(message, 'Close', { duration: 5000 });
      }
    });
  }

  toggleScannerStatus(scanner: Scanner): void {
    this.scannerService.updateScanner(scanner.id, { is_active: !scanner.is_active }).subscribe({
      next: () => {
        const status = !scanner.is_active ? 'activated' : 'deactivated';
        this.snackBar.open(`Scanner ${status}`, 'Close', { duration: 2000 });
        this.loadScanners();
      },
      error: (error) => {
        console.error('Failed to toggle scanner status:', error);
        this.snackBar.open('Failed to update scanner', 'Close', { duration: 3000 });
      }
    });
  }

  applyFilter(filter: 'all' | 'active' | 'inactive'): void {
    this.filterActive = filter === 'all' ? undefined : filter === 'active';
    this.applyClientFilter();
  }

  onSearchChange(event: Event): void {
    this.searchQuery = (event.target as HTMLInputElement).value;
  }

  clearSearch(): void {
    this.searchQuery = '';
  }

  getTickerCount(scanner: Scanner): number {
    return scanner.config?.tickers?.length || 0;
  }

  getTickers(scanner: Scanner): string[] {
    return scanner.config?.tickers || [];
  }

  private applyClientFilter(): void {
    if (this.filterActive === undefined) {
      this.scanners = [...this.allScanners];
    } else {
      this.scanners = this.allScanners.filter(s => s.is_active === this.filterActive);
    }
  }
}
