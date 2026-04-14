import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

export interface ClonePipelineDialogData {
  pipelineName: string;
}

@Component({
  selector: 'app-clone-pipeline-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  templateUrl: './clone-pipeline-dialog.component.html',
  styleUrls: ['./clone-pipeline-dialog.component.scss'],
})
export class ClonePipelineDialogComponent {
  readonly nameControl: FormControl<string | null>;

  constructor(
    private readonly dialogRef: MatDialogRef<ClonePipelineDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public readonly data: ClonePipelineDialogData
  ) {
    this.nameControl = new FormControl(`${data.pipelineName} Copy`, {
      nonNullable: false,
      validators: [Validators.required, Validators.maxLength(255)],
    });
  }

  get canSubmit(): boolean {
    return this.nameControl.valid && !!this.nameControl.value?.trim();
  }

  submit(): void {
    const value = this.nameControl.value?.trim();
    if (!value) {
      this.nameControl.markAsTouched();
      return;
    }
    this.dialogRef.close(value);
  }

  cancel(): void {
    this.dialogRef.close();
  }
}
