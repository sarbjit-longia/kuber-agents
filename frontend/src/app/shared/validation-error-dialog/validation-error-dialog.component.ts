import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';

export interface ValidationErrorData {
  errors: string[];
}

@Component({
  selector: 'app-validation-error-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatListModule
  ],
  templateUrl: './validation-error-dialog.component.html',
  styleUrls: ['./validation-error-dialog.component.scss']
})
export class ValidationErrorDialogComponent {
  constructor(
    public dialogRef: MatDialogRef<ValidationErrorDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: ValidationErrorData
  ) {}

  close(): void {
    this.dialogRef.close();
  }
}

