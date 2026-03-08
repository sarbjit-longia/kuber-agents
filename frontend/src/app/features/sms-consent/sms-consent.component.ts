import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { SmsConsentService } from '../../core/services/sms-consent.service';

@Component({
  selector: 'app-sms-consent',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatCheckboxModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './sms-consent.component.html',
  styleUrls: ['./sms-consent.component.scss']
})
export class SmsConsentComponent {
  phoneNumber = '';
  consentChecked = false;
  submitting = false;
  submitted = false;
  error: string | null = null;

  constructor(private smsConsentService: SmsConsentService) {}

  get phoneValid(): boolean {
    return /^\+[1-9]\d{6,14}$/.test(this.phoneNumber);
  }

  get canSubmit(): boolean {
    return this.phoneValid && this.consentChecked && !this.submitting;
  }

  submit(): void {
    if (!this.canSubmit) return;
    this.submitting = true;
    this.error = null;

    this.smsConsentService.submitPublicConsent(this.phoneNumber).subscribe({
      next: () => {
        this.submitted = true;
        this.submitting = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to record consent. Please try again.';
        this.submitting = false;
      }
    });
  }
}
