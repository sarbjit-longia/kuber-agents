/**
 * Execution Service
 * 
 * Service for managing pipeline executions.
 */

import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap } from 'rxjs/operators';
import { ApiService } from './api.service';
import { Execution, ExecutionCreate, ExecutionLog, ExecutionStatus } from '../models/pipeline.model';

@Injectable({
  providedIn: 'root'
})
export class ExecutionService {
  private executionsSubject = new BehaviorSubject<Execution[]>([]);
  public executions$ = this.executionsSubject.asObservable();

  private currentExecutionSubject = new BehaviorSubject<Execution | null>(null);
  public currentExecution$ = this.currentExecutionSubject.asObservable();

  constructor(private apiService: ApiService) {}

  /**
   * Start a new pipeline execution
   */
  startExecution(data: ExecutionCreate): Observable<Execution> {
    return this.apiService.post<Execution>('/api/v1/executions', data).pipe(
      tap(execution => {
        const current = this.executionsSubject.value;
        this.executionsSubject.next([execution, ...current]);
        this.currentExecutionSubject.next(execution);
      })
    );
  }

  /**
   * Get execution by ID
   */
  getExecution(id: string): Observable<Execution> {
    return this.apiService.get<Execution>(`/api/v1/executions/${id}`).pipe(
      tap(execution => {
        this.updateExecutionInList(execution);
        this.currentExecutionSubject.next(execution);
      })
    );
  }

  /**
   * List executions with optional filters
   */
  listExecutions(pipelineId?: string, status?: ExecutionStatus, limit = 50, offset = 0): Observable<Execution[]> {
    let endpoint = `/api/v1/executions?limit=${limit}&offset=${offset}`;
    if (pipelineId) {
      endpoint += `&pipeline_id=${pipelineId}`;
    }
    if (status) {
      endpoint += `&status=${status}`;
    }

    return this.apiService.get<Execution[]>(endpoint).pipe(
      tap(executions => this.executionsSubject.next(executions))
    );
  }

  /**
   * Stop a running execution
   */
  stopExecution(id: string): Observable<{ message: string; execution_id: string }> {
    return this.apiService.post<{ message: string; execution_id: string }>(
      `/api/v1/executions/${id}/stop`,
      {}
    );
  }

  /**
   * Get execution logs
   */
  getExecutionLogs(id: string): Observable<ExecutionLog[]> {
    return this.apiService.get<ExecutionLog[]>(`/api/v1/executions/${id}/logs`);
  }

  /**
   * Update an execution in the list (called from WebSocket updates)
   */
  updateExecution(execution: Execution): void {
    this.updateExecutionInList(execution);
    
    if (this.currentExecutionSubject.value?.id === execution.id) {
      this.currentExecutionSubject.next(execution);
    }
  }

  /**
   * Set current execution
   */
  setCurrentExecution(execution: Execution | null): void {
    this.currentExecutionSubject.next(execution);
  }

  /**
   * Helper to update execution in list
   */
  private updateExecutionInList(execution: Execution): void {
    const current = this.executionsSubject.value;
    const index = current.findIndex(e => e.id === execution.id);
    
    if (index !== -1) {
      current[index] = execution;
      this.executionsSubject.next([...current]);
    }
  }
}

