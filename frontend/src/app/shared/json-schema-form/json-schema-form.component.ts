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
  userTimezone: string;

  constructor(private fb: FormBuilder) {
    this.userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  }

  ngOnInit(): void {
    this.buildForm();
  }

  ngOnChanges(changes: SimpleChanges): void {
    // Rebuild form only if:
    // 1. Schema changes (different agent/tool selected)
    // 2. Data reference changes significantly (different node selected)
    //    but NOT on every keystroke update
    
    const schemaChanged = changes['schema'] && !changes['schema'].firstChange;
    const dataChanged = changes['data'] && !changes['data'].firstChange;
    
    if (schemaChanged) {
      // Schema changed - completely rebuild form
      this.buildForm();
    } else if (dataChanged && this.form) {
      // Data changed but schema didn't - just update form values without rebuilding
      // This handles switching between nodes with the same schema
      const newData = changes['data'].currentValue;
      if (newData && typeof newData === 'object') {
        // Only update if the form exists and values are different
        Object.keys(this.form.controls).forEach(key => {
          const currentValue = this.form.get(key)?.value;
          const newValue = newData[key] !== undefined ? newData[key] : null;
          if (JSON.stringify(currentValue) !== JSON.stringify(newValue)) {
            this.form.get(key)?.setValue(newValue, { emitEvent: false });
          }
        });
      }
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

      // Get initial value - convert UTC to local time if needed
      let initialValue = this.data[key] !== undefined ? this.data[key] : property.default;
      
      // If this is a time field with UTC timezone, convert to local
      if (property.format === 'time' && property['x-timezone'] === 'local' && initialValue) {
        initialValue = this.convertUTCTimeToLocal(initialValue);
      }

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

    // Emit changes WITHOUT timezone conversion (conversion happens on save)
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

  getUserTimezone(): string {
    return this.userTimezone;
  }

  /**
   * Convert local time (HH:MM) to UTC time (HH:MM)
   */
  convertLocalTimeToUTC(localTime: string): string {
    if (!localTime || !localTime.includes(':')) {
      return localTime;
    }

    const [hours, minutes] = localTime.split(':').map(Number);
    const today = new Date();
    today.setHours(hours, minutes, 0, 0);

    // Get UTC hours and minutes
    const utcHours = today.getUTCHours();
    const utcMinutes = today.getUTCMinutes();

    return `${String(utcHours).padStart(2, '0')}:${String(utcMinutes).padStart(2, '0')}`;
  }

  /**
   * Convert UTC time (HH:MM) to local time (HH:MM)
   */
  convertUTCTimeToLocal(utcTime: string): string {
    if (!utcTime || !utcTime.includes(':')) {
      return utcTime;
    }

    const [hours, minutes] = utcTime.split(':').map(Number);
    const today = new Date();
    
    // Set as UTC time
    const utcDate = new Date(Date.UTC(
      today.getUTCFullYear(),
      today.getUTCMonth(),
      today.getUTCDate(),
      hours,
      minutes,
      0
    ));

    // Get local hours and minutes
    const localHours = utcDate.getHours();
    const localMinutes = utcDate.getMinutes();

    return `${String(localHours).padStart(2, '0')}:${String(localMinutes).padStart(2, '0')}`;
  }

  /**
   * Convert time fields marked with x-timezone: local to UTC
   * This should be called by parent component when saving
   */
  convertTimesToUTC(formValue: any): any {
    if (!this.schema || !this.schema.properties) {
      return formValue;
    }

    const converted = { ...formValue };

    Object.keys(this.schema.properties).forEach(key => {
      const property = this.schema.properties[key];
      
      // If this is a time field with local timezone, convert to UTC
      if (property.format === 'time' && property['x-timezone'] === 'local' && converted[key]) {
        converted[key] = this.convertLocalTimeToUTC(converted[key]);
      }
    });

    return converted;
  }

  /**
   * Get current form value with timezone conversion applied
   */
  getConvertedValue(): any {
    return this.convertTimesToUTC(this.form.value);
  }
}
