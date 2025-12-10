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
import { Scanner, ScannerCreate } from '../../core/models/scanner.model';
import { ScannerService } from '../../core/services/scanner.service';
import { CreateScannerDialogComponent } from './create-scanner-dialog/create-scanner-dialog.component';
import { NavbarComponent } from '../../core/components/navbar/navbar.component';

@Component({
  selector: 'app-scanner-management',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatSnackBarModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatChipsModule,
    MatMenuModule,
    MatProgressSpinnerModule,
    MatButtonToggleModule,
    NavbarComponent,
    CreateScannerDialogComponent
  ],
  templateUrl: './scanner-management.component.html',
  styleUrls: ['./scanner-management.component.scss']
})
export class ScannerManagementComponent implements OnInit {
  scanners: Scanner[] = [];
  loading = false;
  filterActive: boolean | undefined = undefined;

  constructor(
    private scannerService: ScannerService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.loadScanners();
  }

  loadScanners(): void {
    this.loading = true;
    this.scannerService.getScanners(this.filterActive).subscribe({
      next: (scanners) => {
        this.scanners = scanners;
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
      width: '600px',
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
      width: '600px',
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
    if (!confirm(`Are you sure you want to delete "${scanner.name}"?`)) {
      return;
    }

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
    this.loadScanners();
  }

  getTickerCount(scanner: Scanner): number {
    return scanner.config?.tickers?.length || 0;
  }

  getTickers(scanner: Scanner): string[] {
    return scanner.config?.tickers || [];
  }
}

