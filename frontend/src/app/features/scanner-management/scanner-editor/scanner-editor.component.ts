import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { FormBuilder, FormControl, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule, MatChipInputEvent } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { COMMA, ENTER, SPACE } from '@angular/cdk/keycodes';
import { NavbarComponent } from '../../../core/components/navbar/navbar.component';
import { FooterComponent } from '../../../shared/components/footer/footer.component';
import { Scanner, ScannerCreate, ScannerType } from '../../../core/models/scanner.model';
import { ScannerService } from '../../../core/services/scanner.service';
import {
  TickerInfo,
  TICKER_PRESETS,
  getSectors,
  getTickersByCategory,
  getTickersBySector,
  searchTickers
} from '../../../core/data/ticker-data';

@Component({
  selector: 'app-scanner-editor',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    ReactiveFormsModule,
    FormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTabsModule,
    MatTooltipModule,
    NavbarComponent,
    FooterComponent
  ],
  templateUrl: './scanner-editor.component.html',
  styleUrls: ['./scanner-editor.component.scss']
})
export class ScannerEditorComponent implements OnInit {
  scannerForm: FormGroup;
  isEditMode = false;
  scanner?: Scanner;
  loading = false;
  saving = false;

  tickers: string[] = [];
  tickerInputControl = new FormControl('');
  readonly separatorKeysCodes = [ENTER, COMMA, SPACE] as const;

  selectedTabIndex = 0;
  sp500Search = '';
  forexSearch = '';
  etfSearch = '';
  selectedSector = '';
  sectors: string[] = [];
  presets = TICKER_PRESETS;
  presetKeys = Object.keys(TICKER_PRESETS);

  constructor(
    private fb: FormBuilder,
    private route: ActivatedRoute,
    private router: Router,
    private scannerService: ScannerService,
    private snackBar: MatSnackBar
  ) {
    this.scannerForm = this.fb.group({
      name: ['', [Validators.required, Validators.maxLength(100)]],
      description: [''],
      scanner_type: [ScannerType.MANUAL],
      is_active: [true]
    });
  }

  ngOnInit(): void {
    this.sectors = getSectors();
    const id = this.route.snapshot.paramMap.get('id');
    this.isEditMode = !!id;

    if (id) {
      this.loadScanner(id);
    }
  }

  get pageTitle(): string {
    return this.isEditMode ? 'Edit Scanner' : 'Create Scanner';
  }

  get pageSubtitle(): string {
    return this.isEditMode
      ? 'Refine the watchlist, ticker universe, and activation state for this scanner.'
      : 'Build a reusable scanner with a curated ticker universe for your signal pipelines.';
  }

  getDisplayedTickers(category: 'sp500' | 'forex' | 'etf'): TickerInfo[] {
    const query = this.getSearchQuery(category);
    if (query) {
      let results = searchTickers(query, category);
      if (category === 'sp500' && this.selectedSector) {
        results = results.filter(t => t.sector === this.selectedSector);
      }
      return results;
    }
    if (category === 'sp500' && this.selectedSector) {
      return getTickersBySector(this.selectedSector);
    }
    return getTickersByCategory(category);
  }

  isTickerSelected(symbol: string): boolean {
    return this.tickers.includes(symbol);
  }

  toggleTicker(symbol: string): void {
    const index = this.tickers.indexOf(symbol);
    if (index >= 0) {
      this.tickers.splice(index, 1);
    } else {
      this.tickers.push(symbol);
    }
  }

  selectAllDisplayed(category: 'sp500' | 'forex' | 'etf'): void {
    for (const ticker of this.getDisplayedTickers(category)) {
      if (!this.tickers.includes(ticker.symbol)) {
        this.tickers.push(ticker.symbol);
      }
    }
  }

  clearAllDisplayed(category: 'sp500' | 'forex' | 'etf'): void {
    const displayed = new Set(this.getDisplayedTickers(category).map(t => t.symbol));
    this.tickers = this.tickers.filter(t => !displayed.has(t));
  }

  applyPreset(presetName: string): void {
    const presetTickers = TICKER_PRESETS[presetName] || [];
    for (const symbol of presetTickers) {
      if (!this.tickers.includes(symbol)) {
        this.tickers.push(symbol);
      }
    }
  }

  onSectorChange(sector: string): void {
    this.selectedSector = this.selectedSector === sector ? '' : sector;
  }

  getSelectedCount(category: 'sp500' | 'forex' | 'etf'): number {
    return this.getDisplayedTickers(category).filter(t => this.tickers.includes(t.symbol)).length;
  }

  getTotalCount(category: 'sp500' | 'forex' | 'etf'): number {
    return this.getDisplayedTickers(category).length;
  }

  clearTabSearch(category: 'sp500' | 'forex' | 'etf'): void {
    switch (category) {
      case 'sp500':
        this.sp500Search = '';
        break;
      case 'forex':
        this.forexSearch = '';
        break;
      case 'etf':
        this.etfSearch = '';
        break;
    }
  }

  clearAllTickers(): void {
    this.tickers = [];
  }

  addTicker(event: MatChipInputEvent): void {
    const value = (event.value || '').trim().toUpperCase();
    if (value && !this.tickers.includes(value)) {
      this.tickers.push(value);
    }

    event.chipInput?.clear();
    this.tickerInputControl.setValue('');
  }

  removeTicker(ticker: string): void {
    this.tickers = this.tickers.filter(t => t !== ticker);
  }

  onPaste(event: ClipboardEvent): void {
    event.preventDefault();
    const pasteData = event.clipboardData?.getData('text') || '';
    const pastedTickers = pasteData
      .split(/[,\s\n\t]+/)
      .map(t => t.trim().toUpperCase())
      .filter(t => t.length > 0);

    for (const ticker of pastedTickers) {
      if (!this.tickers.includes(ticker)) {
        this.tickers.push(ticker);
      }
    }
  }

  saveScanner(): void {
    if (!this.scannerForm.valid || this.tickers.length === 0 || this.saving) {
      if (this.tickers.length === 0) {
        this.snackBar.open('Add at least one ticker before saving', 'Close', { duration: 3000 });
      }
      return;
    }

    this.saving = true;
    const formValue = this.scannerForm.value;
    const payload: ScannerCreate = {
      name: formValue.name,
      description: formValue.description || undefined,
      scanner_type: formValue.scanner_type,
      config: {
        tickers: this.tickers
      },
      is_active: formValue.is_active
    };

    const request = this.isEditMode && this.scanner
      ? this.scannerService.updateScanner(this.scanner.id, payload)
      : this.scannerService.createScanner(payload);

    request.subscribe({
      next: () => {
        this.saving = false;
        this.snackBar.open(
          this.isEditMode ? 'Scanner updated successfully' : 'Scanner created successfully',
          'Close',
          { duration: 3000 }
        );
        this.router.navigate(['/scanners']);
      },
      error: (error) => {
        this.saving = false;
        const message = error.error?.detail || 'Failed to save scanner';
        this.snackBar.open(message, 'Close', { duration: 5000 });
      }
    });
  }

  goBack(): void {
    this.router.navigate(['/scanners']);
  }

  private loadScanner(id: string): void {
    this.loading = true;
    this.scannerService.getScanner(id).subscribe({
      next: (scanner) => {
        this.scanner = scanner;
        this.scannerForm.patchValue({
          name: scanner.name,
          description: scanner.description || '',
          scanner_type: scanner.scanner_type,
          is_active: scanner.is_active
        });

        this.tickers = [...(scanner.config?.tickers || [])];
        this.selectedTabIndex = 3;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.snackBar.open('Failed to load scanner', 'Close', { duration: 3000 });
        this.router.navigate(['/scanners']);
      }
    });
  }

  private getSearchQuery(category: 'sp500' | 'forex' | 'etf'): string {
    switch (category) {
      case 'sp500':
        return this.sp500Search;
      case 'forex':
        return this.forexSearch;
      case 'etf':
        return this.etfSearch;
    }
  }
}
