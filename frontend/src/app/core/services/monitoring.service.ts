/**
 * Monitoring Service
 * 
 * Service for fetching and managing execution monitoring data
 */

import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject, interval, switchMap, tap } from 'rxjs';
import { ApiService } from './api.service';
import { Execution, ExecutionSummary, ExecutionStats, ExecutionLog } from '../models/execution.model';

@Injectable({
  providedIn: 'root'
})
export class MonitoringService {
  private executionsSubject = new BehaviorSubject<ExecutionSummary[]>([]);
  public executions$ = this.executionsSubject.asObservable();

  private currentExecutionSubject = new BehaviorSubject<Execution | null>(null);
  public currentExecution$ = this.currentExecutionSubject.asObservable();

  private pollingInterval: any;

  constructor(private apiService: ApiService) {}

  /**
   * Load all executions for current user
   */
  loadExecutions(): Observable<ExecutionSummary[]> {
    return this.apiService.get<ExecutionSummary[]>('/api/v1/executions').pipe(
      tap(executions => this.executionsSubject.next(executions))
    );
  }

  /**
   * Get execution by ID
   */
  getExecution(id: string): Observable<Execution> {
    return this.apiService.get<Execution>(`/api/v1/executions/${id}`).pipe(
      tap(execution => this.currentExecutionSubject.next(execution))
    );
  }

  /**
   * Get detailed execution data (alias for getExecution)
   */
  getExecutionDetail(id: string): Observable<any> {
    return this.getExecution(id);
  }

  /**
   * Get execution logs
   */
  getExecutionLogs(executionId: string, limit?: number): Observable<ExecutionLog[]> {
    const params = limit ? `?limit=${limit}` : '';
    return this.apiService.get<ExecutionLog[]>(`/api/v1/executions/${executionId}/logs${params}`);
  }

  /**
   * Get execution statistics
   */
  getExecutionStats(): Observable<ExecutionStats> {
    return this.apiService.get<ExecutionStats>('/api/v1/executions/stats');
  }

  /**
   * Stop execution
   */
  stopExecution(executionId: string): Observable<Execution> {
    return this.apiService.post<Execution>(`/api/v1/executions/${executionId}/stop`, {});
  }

  /**
   * Pause execution
   */
  pauseExecution(executionId: string): Observable<Execution> {
    return this.apiService.post<Execution>(`/api/v1/executions/${executionId}/pause`, {});
  }

  /**
   * Resume execution
   */
  resumeExecution(executionId: string): Observable<Execution> {
    return this.apiService.post<Execution>(`/api/v1/executions/${executionId}/resume`, {});
  }

  /**
   * Cancel execution
   */
  cancelExecution(executionId: string): Observable<Execution> {
    return this.apiService.post<Execution>(`/api/v1/executions/${executionId}/cancel`, {});
  }

  /**
   * Start polling for updates (every 3 seconds)
   */
  startPolling(executionId: string): void {
    this.stopPolling(); // Stop any existing polling
    
    this.pollingInterval = interval(3000).pipe(
      switchMap(() => this.getExecution(executionId))
    ).subscribe({
      next: (execution) => {
        console.log('Polling update:', execution.status);
        // Stop polling if execution is completed, failed, or cancelled
        if (['completed', 'failed', 'cancelled'].includes(execution.status)) {
          this.stopPolling();
        }
      },
      error: (error) => {
        console.error('Polling error:', error);
        this.stopPolling();
      }
    });
  }

  /**
   * Stop polling
   */
  stopPolling(): void {
    if (this.pollingInterval) {
      this.pollingInterval.unsubscribe();
      this.pollingInterval = null;
    }
  }

  /**
   * Get current executions from subject
   */
  getCurrentExecutions(): ExecutionSummary[] {
    return this.executionsSubject.value;
  }

  /**
   * Clear current execution
   */
  clearCurrentExecution(): void {
    this.currentExecutionSubject.next(null);
  }
}

