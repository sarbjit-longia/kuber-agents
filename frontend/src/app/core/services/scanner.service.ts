/**
 * Scanner Service
 * 
 * Handles all scanner-related API calls and state management.
 */
import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap } from 'rxjs/operators';
import { ApiService } from './api.service';
import {
  Scanner,
  ScannerCreate,
  ScannerUpdate,
  ScannerTickers,
  ScannerUsage,
  SignalType
} from '../models/scanner.model';

@Injectable({
  providedIn: 'root'
})
export class ScannerService {
  private scannersSubject = new BehaviorSubject<Scanner[]>([]);
  public scanners$ = this.scannersSubject.asObservable();

  private signalTypesSubject = new BehaviorSubject<SignalType[]>([]);
  public signalTypes$ = this.signalTypesSubject.asObservable();

  constructor(private apiService: ApiService) {
    this.loadSignalTypes();
  }

  /**
   * Load available signal types
   */
  private loadSignalTypes(): void {
    this.apiService.get<SignalType[]>('/api/v1/signals/types').subscribe({
      next: (types) => this.signalTypesSubject.next(types),
      error: (error) => console.error('Failed to load signal types:', error)
    });
  }

  /**
   * Get all scanners for the current user
   */
  getScanners(isActive?: boolean): Observable<Scanner[]> {
    const endpoint = isActive !== undefined 
      ? `/api/v1/scanners?is_active=${isActive}`
      : '/api/v1/scanners';

    return this.apiService.get<Scanner[]>(endpoint).pipe(
      tap(scanners => this.scannersSubject.next(scanners))
    );
  }

  /**
   * Get a single scanner by ID
   */
  getScanner(scannerId: string): Observable<Scanner> {
    return this.apiService.get<Scanner>(`/api/v1/scanners/${scannerId}`);
  }

  /**
   * Create a new scanner
   */
  createScanner(scannerData: ScannerCreate): Observable<Scanner> {
    return this.apiService.post<Scanner>('/api/v1/scanners', scannerData).pipe(
      tap(newScanner => {
        const current = this.scannersSubject.value;
        this.scannersSubject.next([newScanner, ...current]);
      })
    );
  }

  /**
   * Update an existing scanner
   */
  updateScanner(scannerId: string, updates: ScannerUpdate): Observable<Scanner> {
    return this.apiService.patch<Scanner>(`/api/v1/scanners/${scannerId}`, updates).pipe(
      tap(updatedScanner => {
        const current = this.scannersSubject.value;
        const index = current.findIndex(s => s.id === scannerId);
        if (index !== -1) {
          current[index] = updatedScanner;
          this.scannersSubject.next([...current]);
        }
      })
    );
  }

  /**
   * Delete a scanner
   */
  deleteScanner(scannerId: string): Observable<void> {
    return this.apiService.delete<void>(`/api/v1/scanners/${scannerId}`).pipe(
      tap(() => {
        const current = this.scannersSubject.value;
        this.scannersSubject.next(current.filter(s => s.id !== scannerId));
      })
    );
  }

  /**
   * Get tickers from a scanner
   */
  getScannerTickers(scannerId: string): Observable<ScannerTickers> {
    return this.apiService.get<ScannerTickers>(`/api/v1/scanners/${scannerId}/tickers`);
  }

  /**
   * Get scanner usage (which pipelines use it)
   */
  getScannerUsage(scannerId: string): Observable<ScannerUsage> {
    return this.apiService.get<ScannerUsage>(`/api/v1/scanners/${scannerId}/usage`);
  }

  /**
   * Refresh the scanners list
   */
  refreshScanners(): void {
    this.getScanners().subscribe();
  }

  /**
   * Get available signal types
   */
  getSignalTypes(): Observable<SignalType[]> {
    return this.signalTypes$;
  }
}

