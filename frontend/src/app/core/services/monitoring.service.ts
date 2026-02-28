/**
 * Monitoring Service
 * 
 * Service for fetching and managing execution monitoring data
 */

import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject, interval, switchMap, tap, map } from 'rxjs';
import { ApiService } from './api.service';
import { Execution, ExecutionSummary, ExecutionStats, ExecutionLog } from '../models/execution.model';

/** Paginated response from the executions list endpoint */
export interface ExecutionListResponse {
  executions: ExecutionSummary[];
  total: number;
  active_count: number;
  historical_total: number;
  limit: number;
  offset: number;
}

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
   * Load executions with server-side pagination.
   * Active executions (MONITORING, RUNNING, etc.) are always included
   * regardless of limit/offset — they are prepended by the backend.
   */
  loadExecutions(limit = 50, offset = 0): Observable<ExecutionListResponse> {
    return this.apiService
      .get<ExecutionListResponse>(`/api/v1/executions?limit=${limit}&offset=${offset}&include_active=true`)
      .pipe(
        tap(resp => this.executionsSubject.next(resp.executions))
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
   * Close position for monitoring execution
   */
  closePosition(executionId: string): Observable<any> {
    return this.apiService.post<any>(`/api/v1/executions/${executionId}/close-position`, {});
  }

  /**
   * Manually reconcile a NEEDS_RECONCILIATION execution with P&L data
   */
  reconcileExecution(executionId: string, reconciliationData: any): Observable<any> {
    return this.apiService.post<any>(`/api/v1/executions/${executionId}/reconcile`, reconciliationData);
  }

  /**
   * Resume monitoring for a NEEDS_RECONCILIATION execution
   */
  resumeMonitoring(executionId: string): Observable<any> {
    return this.apiService.post<any>(`/api/v1/executions/${executionId}/resume-monitoring`, {});
  }

  /**
   * Approve a trade execution awaiting approval
   */
  approveExecution(executionId: string): Observable<any> {
    return this.apiService.post<any>(`/api/v1/executions/${executionId}/approve`, { decision: 'approve' });
  }

  /**
   * Reject a trade execution awaiting approval
   */
  rejectExecution(executionId: string, reason?: string): Observable<any> {
    return this.apiService.post<any>(`/api/v1/executions/${executionId}/reject`, { decision: 'reject', reason });
  }

  /**
   * Get pre-trade report for an execution awaiting approval
   */
  getPreTradeReport(executionId: string): Observable<any> {
    return this.apiService.get<any>(`/api/v1/executions/${executionId}/pre-trade-report`);
  }

  /**
   * Get AI-powered executive report for a completed execution
   */
  getExecutiveReport(executionId: string): Observable<any> {
    return this.apiService.get<any>(`/api/v1/executions/${executionId}/executive-report`);
  }

  /**
   * Get AI-powered post-trade analysis for a completed execution
   */
  getTradeAnalysis(executionId: string): Observable<any> {
    return this.apiService.get<any>(`/api/v1/executions/${executionId}/trade-analysis`);
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

