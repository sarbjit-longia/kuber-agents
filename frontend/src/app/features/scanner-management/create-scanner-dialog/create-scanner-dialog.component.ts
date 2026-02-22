/**
 * Create/Edit Scanner Dialog Component
 *
 * Dialog for creating and editing scanners with tabbed ticker selection.
 */
import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, Validators, FormControl, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule, MatChipInputEvent } from '@angular/material/chips';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Scanner, ScannerType } from '../../../core/models/scanner.model';
import { COMMA, ENTER, SPACE } from '@angular/cdk/keycodes';
import {
  TickerInfo, TICKER_PRESETS,
  getTickersByCategory, searchTickers, getSectors, getTickersBySector
} from '../../../core/data/ticker-data';

@Component({
  selector: 'app-create-scanner-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatCheckboxModule,
    MatChipsModule,
    MatTabsModule,
    MatTooltipModule
  ],
  templateUrl: './create-scanner-dialog.component.html',
  styleUrls: ['./create-scanner-dialog.component.scss']
})
export class CreateScannerDialogComponent implements OnInit {
  scannerForm: FormGroup;
  isEditMode = false;
  scanner?: Scanner;
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
    private dialogRef: MatDialogRef<CreateScannerDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { scanner?: Scanner }
  ) {
    this.isEditMode = !!data.scanner;
    this.scanner = data.scanner;

    this.scannerForm = this.fb.group({
      name: ['', [Validators.required, Validators.maxLength(100)]],
      description: [''],
      scanner_type: [ScannerType.MANUAL],
      is_active: [true]
    });
  }

  ngOnInit(): void {
    this.sectors = getSectors();

    if (this.isEditMode && this.scanner) {
      this.scannerForm.patchValue({
        name: this.scanner.name,
        description: this.scanner.description || '',
        scanner_type: this.scanner.scanner_type,
        is_active: this.scanner.is_active
      });

      if (this.scanner.config?.tickers) {
        this.tickers = [...this.scanner.config.tickers];
      }

      // Default to Custom tab in edit mode
      this.selectedTabIndex = 3;
    }
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
    const displayed = this.getDisplayedTickers(category);
    for (const ticker of displayed) {
      if (!this.tickers.includes(ticker.symbol)) {
        this.tickers.push(ticker.symbol);
      }
    }
  }

  clearAllDisplayed(category: 'sp500' | 'forex' | 'etf'): void {
    const displayed = this.getDisplayedTickers(category);
    const symbols = new Set(displayed.map(t => t.symbol));
    this.tickers = this.tickers.filter(t => !symbols.has(t));
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
    const displayed = this.getDisplayedTickers(category);
    return displayed.filter(t => this.tickers.includes(t.symbol)).length;
  }

  getTotalCount(category: 'sp500' | 'forex' | 'etf'): number {
    return this.getDisplayedTickers(category).length;
  }

  clearTabSearch(category: 'sp500' | 'forex' | 'etf'): void {
    switch (category) {
      case 'sp500': this.sp500Search = ''; break;
      case 'forex': this.forexSearch = ''; break;
      case 'etf': this.etfSearch = ''; break;
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

    event.chipInput!.clear();
    this.tickerInputControl.setValue('');
  }

  removeTicker(ticker: string): void {
    const index = this.tickers.indexOf(ticker);
    if (index >= 0) {
      this.tickers.splice(index, 1);
    }
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

  onSubmit(): void {
    if (this.scannerForm.valid) {
      if (this.tickers.length === 0) {
        alert('Please add at least one ticker');
        return;
      }

      const formValue = this.scannerForm.value;
      const result = {
        name: formValue.name,
        description: formValue.description || undefined,
        scanner_type: formValue.scanner_type,
        config: {
          tickers: this.tickers
        },
        is_active: formValue.is_active
      };

      this.dialogRef.close(result);
    }
  }

  onCancel(): void {
    this.dialogRef.close();
  }

  private getSearchQuery(category: 'sp500' | 'forex' | 'etf'): string {
    switch (category) {
      case 'sp500': return this.sp500Search;
      case 'forex': return this.forexSearch;
      case 'etf': return this.etfSearch;
    }
  }
}
