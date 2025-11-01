import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { AgentConfigSchema } from '../../core/models/pipeline.model';

@Component({
  selector: 'app-json-schema-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatCheckboxModule,
    MatSlideToggleModule,
    MatIconModule,
    MatDatepickerModule,
    MatNativeDateModule
  ],
  templateUrl: './json-schema-form.component.html',
  styleUrls: ['./json-schema-form.component.scss']
})
export class JsonSchemaFormComponent implements OnInit, OnChanges {
  @Input() schema!: AgentConfigSchema;
  @Input() data: any = {};
  @Output() dataChange = new EventEmitter<any>();

  form!: FormGroup;
  properties: any[] = [];

  constructor(private fb: FormBuilder) {}

  ngOnInit(): void {
    this.buildForm();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['schema'] || changes['data']) {
      this.buildForm();
    }
  }

  buildForm(): void {
    if (!this.schema || !this.schema.properties) {
      return;
    }

    const formControls: any = {};
    this.properties = [];

    // Convert schema properties to form controls
    Object.keys(this.schema.properties).forEach(key => {
      const property = this.schema.properties[key];
      const validators = [];

      // Add required validator
      if (this.schema.required && this.schema.required.includes(key)) {
        validators.push(Validators.required);
      }

      // Get initial value
      const initialValue = this.data[key] !== undefined ? this.data[key] : property.default;

      // Create form control
      formControls[key] = [initialValue, validators];

      // Store property info for template
      this.properties.push({
        key,
        ...property,
        isRequired: this.schema.required && this.schema.required.includes(key)
      });
    });

    this.form = this.fb.group(formControls);

    // Emit changes
    this.form.valueChanges.subscribe(value => {
      this.dataChange.emit(value);
    });
  }

  getFieldType(property: any): string {
    // Check for enum first
    if (property.enum) {
      return 'select';
    }
    
    // Check for format hints (date, time, datetime)
    if (property.format === 'date') {
      return 'date';
    }
    if (property.format === 'time') {
      return 'time';
    }
    if (property.format === 'date-time' || property.format === 'datetime') {
      return 'datetime';
    }
    
    // Check type
    switch (property.type) {
      case 'string':
        return 'text';
      case 'number':
      case 'integer':
        return 'number';
      case 'boolean':
        return 'boolean';
      default:
        return 'text';
    }
  }
}
