import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCheckboxModule } from '@angular/material/checkbox';

export interface LiquidationDialogResult {
  confirmed: boolean;
  liquidate: boolean;
}

@Component({
  selector: 'app-liquidation-confirm-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatCheckboxModule,
  ],
  template: `
    <h2 mat-dialog-title>
      <mat-icon>power_settings_new</mat-icon>
      Deactivate Pipeline
    </h2>
    <mat-dialog-content>
      <p>This will stop the pipeline from running automatically.</p>
      <div class="liquidate-option">
        <mat-checkbox [(ngModel)]="liquidate" color="warn">
          Also close all open positions (market order)
        </mat-checkbox>
        <p class="liquidate-warning" *ngIf="liquidate">
          <mat-icon>warning</mat-icon>
          All monitoring positions will be closed immediately via market orders. This may result in slippage.
        </p>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="onCancel()">Cancel</button>
      <button mat-raised-button color="warn" (click)="onConfirm()">
        <mat-icon>power_settings_new</mat-icon>
        Deactivate
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    h2[mat-dialog-title] {
      display: flex;
      align-items: center;
      gap: 8px;
      mat-icon { color: #f44336; }
    }
    .liquidate-option {
      margin-top: 12px;
    }
    .liquidate-warning {
      display: flex;
      align-items: flex-start;
      gap: 6px;
      margin-top: 8px;
      padding: 8px 12px;
      border-radius: 6px;
      background: rgba(244, 67, 54, 0.08);
      border: 1px solid rgba(244, 67, 54, 0.25);
      font-size: 13px;
      color: #f44336;
      mat-icon {
        font-size: 18px;
        width: 18px;
        height: 18px;
        flex-shrink: 0;
        margin-top: 1px;
      }
    }
  `]
})
export class LiquidationConfirmDialogComponent {
  liquidate = false;

  constructor(private dialogRef: MatDialogRef<LiquidationConfirmDialogComponent>) {}

  onCancel(): void {
    this.dialogRef.close({ confirmed: false, liquidate: false } as LiquidationDialogResult);
  }

  onConfirm(): void {
    this.dialogRef.close({ confirmed: true, liquidate: this.liquidate } as LiquidationDialogResult);
  }
}
