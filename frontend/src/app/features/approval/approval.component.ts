/**
 * Approval Component (Public, Token-based)
 *
 * Lightweight page opened from SMS link at /approve/:token.
 * No authentication required — the token itself is the auth.
 */
import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { ApprovalService } from '../../core/services/approval.service';

@Component({
  selector: 'app-approval',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './approval.component.html',
  styleUrls: ['./approval.component.scss']
})
export class ApprovalComponent implements OnInit, OnDestroy {
  token = '';
  loading = true;
  approvalData: any = null;
  error: string | null = null;

  actionTaken: 'approved' | 'rejected' | null = null;
  submitting = false;

  private countdownInterval: any;
  timeRemaining = '';

  constructor(
    private route: ActivatedRoute,
    private approvalService: ApprovalService
  ) {}

  ngOnInit(): void {
    this.token = this.route.snapshot.paramMap.get('token') || '';
    if (!this.token) {
      this.error = 'No approval token provided';
      this.loading = false;
      return;
    }
    this.loadApproval();

    this.countdownInterval = setInterval(() => {
      this.updateCountdown();
    }, 1000);
  }

  ngOnDestroy(): void {
    if (this.countdownInterval) {
      clearInterval(this.countdownInterval);
    }
  }

  loadApproval(): void {
    this.approvalService.getApprovalByToken(this.token).subscribe({
      next: (data) => {
        this.approvalData = data;
        this.loading = false;
        this.updateCountdown();
      },
      error: (err) => {
        this.error = err.error?.detail || 'Invalid or expired approval link';
        this.loading = false;
      }
    });
  }

  updateCountdown(): void {
    if (!this.approvalData?.expires_at) {
      this.timeRemaining = '';
      return;
    }
    const expiresAt = this.approvalData.expires_at;
    let isoString = expiresAt;
    if (!expiresAt.endsWith('Z') && !expiresAt.match(/[+-]\d{2}:\d{2}$/)) {
      isoString = expiresAt + 'Z';
    }
    const diff = new Date(isoString).getTime() - Date.now();
    if (diff <= 0) {
      this.timeRemaining = 'Expired';
      return;
    }
    const minutes = Math.floor(diff / 60000);
    const seconds = Math.floor((diff % 60000) / 1000);
    this.timeRemaining = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
  }

  approve(): void {
    this.submitting = true;
    this.approvalService.approveByToken(this.token).subscribe({
      next: () => {
        this.actionTaken = 'approved';
        this.submitting = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to approve — it may have expired';
        this.submitting = false;
      }
    });
  }

  reject(): void {
    this.submitting = true;
    this.approvalService.rejectByToken(this.token).subscribe({
      next: () => {
        this.actionTaken = 'rejected';
        this.submitting = false;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to reject — it may have expired';
        this.submitting = false;
      }
    });
  }
}
