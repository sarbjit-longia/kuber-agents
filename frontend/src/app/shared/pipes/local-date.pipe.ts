import { Pipe, PipeTransform } from '@angular/core';

/**
 * LocalDatePipe - Converts UTC date strings from the backend to local timezone display.
 *
 * The backend stores all dates in UTC. This pipe ensures they are displayed
 * in the user's local timezone consistently across all UI screens.
 *
 * Usage:
 *   {{ dateString | localDate }}              → "Feb 19, 2026, 10:30:45 AM"
 *   {{ dateString | localDate:'short' }}      → "Feb 19, 10:30 AM"
 *   {{ dateString | localDate:'medium' }}     → "Feb 19, 2026, 10:30:45 AM"
 *   {{ dateString | localDate:'long' }}       → "February 19, 2026, 10:30:45 AM PST"
 *   {{ dateString | localDate:'dateOnly' }}   → "Feb 19, 2026"
 *   {{ dateString | localDate:'timeOnly' }}   → "10:30:45 AM"
 *   {{ dateString | localDate:'shortDate' }}  → "2/19/26, 10:30 AM"
 */
@Pipe({
  name: 'localDate',
  standalone: true,
})
export class LocalDatePipe implements PipeTransform {
  transform(
    value: string | Date | null | undefined,
    format: 'short' | 'medium' | 'long' | 'dateOnly' | 'timeOnly' | 'shortDate' = 'medium'
  ): string {
    if (!value) return '-';

    try {
      // Ensure the date is treated as UTC if no timezone info is present
      let dateStr = typeof value === 'string' ? value : value.toISOString();
      if (
        typeof value === 'string' &&
        !value.endsWith('Z') &&
        !value.match(/[+-]\d{2}:\d{2}$/)
      ) {
        // Backend dates are UTC but may not have 'Z' suffix - append it
        dateStr = value + 'Z';
      }

      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return 'Invalid date';

      // Format based on requested format - all using local timezone
      const options = this.getFormatOptions(format);
      return date.toLocaleString('en-US', options);
    } catch {
      return 'Invalid date';
    }
  }

  private getFormatOptions(
    format: string
  ): Intl.DateTimeFormatOptions {
    switch (format) {
      case 'short':
        return {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        };
      case 'medium':
        return {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        };
      case 'long':
        return {
          year: 'numeric',
          month: 'long',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          timeZoneName: 'short',
        };
      case 'dateOnly':
        return {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        };
      case 'timeOnly':
        return {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        };
      case 'shortDate':
        return {
          year: '2-digit',
          month: 'numeric',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        };
      default:
        return {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        };
    }
  }
}

/**
 * Utility function for use in component .ts files where pipe can't be used.
 * Converts a UTC date string from the backend to a local timezone formatted string.
 */
export function formatDateToLocal(
  dateStr: string | null | undefined,
  format: 'short' | 'medium' | 'long' | 'dateOnly' | 'timeOnly' | 'shortDate' = 'medium'
): string {
  const pipe = new LocalDatePipe();
  return pipe.transform(dateStr, format);
}
