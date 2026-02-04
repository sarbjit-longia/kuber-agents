/**
 * Pipeline Settings Dialog Component
 * 
 * Dialog for configuring pipeline settings including trigger mode, scanner, and signal subscriptions.
 */
import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, Validators, FormArray, FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatRadioModule } from '@angular/material/radio';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatChipsModule } from '@angular/material/chips';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { Observable } from 'rxjs';
import { map, startWith } from 'rxjs/operators';
import { TriggerMode, SignalSubscription, Pipeline } from '../../../core/models/pipeline.model';
import { Scanner, SignalType } from '../../../core/models/scanner.model';
import { ScannerService } from '../../../core/services/scanner.service';

@Component({
  selector: 'app-pipeline-settings-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatRadioModule,
    MatSelectModule,
    MatFormFieldModule,
    MatInputModule,
    MatChipsModule,
    MatAutocompleteModule
  ],
  templateUrl: './pipeline-settings-dialog.component.html',
  styleUrls: ['./pipeline-settings-dialog.component.scss']
})
export class PipelineSettingsDialogComponent implements OnInit {
  settingsForm: FormGroup;
  TriggerMode = TriggerMode;
  scanners: Scanner[] = [];
  signalTypes: SignalType[] = [];
  loading = false;

  // Quick multi-select for signal filters
  signalTypeSearchCtrl = new FormControl<string>('');
  filteredSignalTypes$!: Observable<SignalType[]>;
  selectedSignalTypes: SignalType[] = [];
  bulkTimeframeCtrl = new FormControl<string | null>(null);
  bulkMinConfidenceCtrl = new FormControl<number | null>(null);

  constructor(
    private fb: FormBuilder,
    private scannerService: ScannerService,
    private dialogRef: MatDialogRef<PipelineSettingsDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { pipeline: Pipeline }
  ) {
    this.settingsForm = this.fb.group({
      trigger_mode: [data.pipeline.trigger_mode || TriggerMode.PERIODIC, Validators.required],
      scanner_id: [data.pipeline.scanner_id || null],
      signal_subscriptions: this.fb.array([])
    });
  }

  ngOnInit(): void {
    this.loadScanners();
    this.loadSignalTypes();

    // Load existing signal subscriptions
    if (this.data.pipeline.signal_subscriptions && this.data.pipeline.signal_subscriptions.length > 0) {
      for (const sub of this.data.pipeline.signal_subscriptions) {
        this.addSignalSubscription(sub);
      }
    }

    // Watch trigger mode changes
    this.settingsForm.get('trigger_mode')?.valueChanges.subscribe(mode => {
      if (mode === TriggerMode.SIGNAL) {
        this.settingsForm.get('scanner_id')?.setValidators([Validators.required]);
      } else {
        this.settingsForm.get('scanner_id')?.clearValidators();
      }
      this.settingsForm.get('scanner_id')?.updateValueAndValidity();
    });

    this.filteredSignalTypes$ = this.signalTypeSearchCtrl.valueChanges.pipe(
      startWith(''),
      map(value => (value || '').toLowerCase().trim()),
      map(query => {
        if (!query) return this.signalTypes;
        return this.signalTypes.filter(st => {
          const hay = `${st.name} ${st.signal_type} ${st.description || ''}`.toLowerCase();
          return hay.includes(query);
        });
      })
    );
  }

  loadScanners(): void {
    this.loading = true;
    this.scannerService.getScanners(true).subscribe({
      next: (scanners) => {
        this.scanners = scanners;
        this.loading = false;
      },
      error: (error) => {
        console.error('Failed to load scanners:', error);
        this.loading = false;
      }
    });
  }

  loadSignalTypes(): void {
    this.scannerService.getSignalTypes().subscribe({
      next: (types) => {
        this.signalTypes = types;
      },
      error: (error) => {
        console.error('Failed to load signal types:', error);
      }
    });
  }

  get signalSubscriptions(): FormArray {
    return this.settingsForm.get('signal_subscriptions') as FormArray;
  }

  addSignalSubscription(subscription?: SignalSubscription): void {
    const subGroup = this.fb.group({
      signal_type: [subscription?.signal_type || '', Validators.required],
      timeframe: [subscription?.timeframe || null],
      min_confidence: [subscription?.min_confidence || null, [Validators.min(0), Validators.max(100)]]
    });
    this.signalSubscriptions.push(subGroup);
  }

  addBulkSignalType(signalType: SignalType): void {
    if (this.selectedSignalTypes.some(st => st.signal_type === signalType.signal_type)) return;
    this.selectedSignalTypes = [...this.selectedSignalTypes, signalType];
  }

  removeBulkSignalType(signalType: SignalType): void {
    this.selectedSignalTypes = this.selectedSignalTypes.filter(st => st.signal_type !== signalType.signal_type);
  }

  applyBulkSelection(): void {
    const timeframe = this.bulkTimeframeCtrl.value ?? null;
    const minConfidence = this.bulkMinConfidenceCtrl.value ?? null;

    for (const st of this.selectedSignalTypes) {
      const exists = this.signalSubscriptions.controls.some(ctrl => {
        const t = ctrl.get('signal_type')?.value;
        const tf = ctrl.get('timeframe')?.value ?? null;
        return t === st.signal_type && tf === timeframe;
      });
      if (exists) continue;
      this.addSignalSubscription({
        signal_type: st.signal_type,
        timeframe: timeframe ?? undefined,
        min_confidence: minConfidence ?? undefined
      });
    }

    // Clear selection after adding
    this.selectedSignalTypes = [];
    this.signalTypeSearchCtrl.setValue('');
  }

  removeSignalSubscription(index: number): void {
    this.signalSubscriptions.removeAt(index);
  }

  getSignalTypeInfo(signalType: string): SignalType | undefined {
    return this.signalTypes.find(st => st.signal_type === signalType);
  }

  isSignalMode(): boolean {
    return this.settingsForm.get('trigger_mode')?.value === TriggerMode.SIGNAL;
  }

  getSelectedScanner(): Scanner | undefined {
    const scannerId = this.settingsForm.get('scanner_id')?.value;
    return this.scanners.find(s => s.id === scannerId);
  }

  getTickerCount(scanner: Scanner): number {
    return scanner.config?.tickers?.length || 0;
  }

  onSubmit(): void {
    if (this.settingsForm.valid) {
      const formValue = this.settingsForm.value;
      
      // Clean up signal subscriptions
      const cleanedSubscriptions = formValue.signal_subscriptions
        .filter((sub: any) => sub.signal_type)
        .map((sub: any) => {
          const subscription: any = {
            signal_type: sub.signal_type
          };
          
          // Only include timeframe if it's set
          if (sub.timeframe) {
            subscription.timeframe = sub.timeframe;
          }
          
          // Only include min_confidence if it's set
          if (sub.min_confidence != null) {
            subscription.min_confidence = sub.min_confidence;
          }
          
          return subscription;
        });

      const result = {
        trigger_mode: formValue.trigger_mode,
        scanner_id: formValue.trigger_mode === TriggerMode.SIGNAL ? formValue.scanner_id : null,
        signal_subscriptions: formValue.trigger_mode === TriggerMode.SIGNAL && cleanedSubscriptions.length > 0 
          ? cleanedSubscriptions 
          : null
      };

      this.dialogRef.close(result);
    }
  }

  onCancel(): void {
    this.dialogRef.close();
  }
}

