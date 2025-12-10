/**
 * Create/Edit Scanner Dialog Component
 * 
 * Dialog for creating and editing scanners.
 */
import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, Validators, FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule, MatChipInputEvent } from '@angular/material/chips';
import { Scanner, ScannerType } from '../../../core/models/scanner.model';
import { COMMA, ENTER, SPACE } from '@angular/cdk/keycodes';

@Component({
  selector: 'app-create-scanner-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatCheckboxModule,
    MatChipsModule
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
    if (this.isEditMode && this.scanner) {
      this.scannerForm.patchValue({
        name: this.scanner.name,
        description: this.scanner.description || '',
        scanner_type: this.scanner.scanner_type,
        is_active: this.scanner.is_active
      });

      // Load existing tickers
      if (this.scanner.config?.tickers) {
        this.tickers = [...this.scanner.config.tickers];
      }
    }
  }

  addTicker(event: MatChipInputEvent): void {
    const value = (event.value || '').trim().toUpperCase();

    if (value && !this.tickers.includes(value)) {
      this.tickers.push(value);
    }

    // Clear the input
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
    
    // Split by common separators: comma, space, newline, tab
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
}

