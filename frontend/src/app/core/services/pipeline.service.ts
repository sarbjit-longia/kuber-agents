/**
 * Pipeline Service
 * 
 * Service for managing trading pipelines.
 */

import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap, map } from 'rxjs/operators';
import { ApiService } from './api.service';
import { Pipeline, PipelineCreate, PipelineUpdate } from '../models/pipeline.model';

@Injectable({
  providedIn: 'root'
})
export class PipelineService {
  private pipelinesSubject = new BehaviorSubject<Pipeline[]>([]);
  public pipelines$ = this.pipelinesSubject.asObservable();

  private currentPipelineSubject = new BehaviorSubject<Pipeline | null>(null);
  public currentPipeline$ = this.currentPipelineSubject.asObservable();

  constructor(private apiService: ApiService) {}

  /**
   * Load all pipelines for the current user
   */
  loadPipelines(): Observable<Pipeline[]> {
    return this.apiService.get<{ pipelines: Pipeline[], total: number }>('/api/v1/pipelines').pipe(
      tap(response => {
        console.log('📡 API Response:', response);
        const pipelines = response.pipelines || [];
        console.log('📋 Extracted pipelines:', pipelines);
        this.pipelinesSubject.next(pipelines);
      }),
      map(response => response.pipelines || [])
    );
  }

  /**
   * Get a specific pipeline by ID
   */
  getPipeline(id: string): Observable<Pipeline> {
    return this.apiService.get<Pipeline>(`/api/v1/pipelines/${id}`).pipe(
      tap(pipeline => this.currentPipelineSubject.next(pipeline))
    );
  }

  /**
   * Create a new pipeline
   */
  createPipeline(data: PipelineCreate): Observable<Pipeline> {
    return this.apiService.post<Pipeline>('/api/v1/pipelines', data).pipe(
      tap(pipeline => {
        const current = this.pipelinesSubject.value;
        // Defensive check: ensure current is an array
        if (Array.isArray(current)) {
          this.pipelinesSubject.next([...current, pipeline]);
        } else {
          // If not an array, initialize with the new pipeline
          this.pipelinesSubject.next([pipeline]);
        }
        this.currentPipelineSubject.next(pipeline);
      })
    );
  }

  /**
   * Update an existing pipeline
   */
  updatePipeline(id: string, data: PipelineUpdate): Observable<Pipeline> {
    return this.apiService.patch<Pipeline>(`/api/v1/pipelines/${id}`, data).pipe(
      tap(updated => {
        const current = this.pipelinesSubject.value;
        const index = current.findIndex(p => p.id === id);
        if (index !== -1) {
          current[index] = updated;
          this.pipelinesSubject.next([...current]);
        }
        this.currentPipelineSubject.next(updated);
      })
    );
  }

  /**
   * Delete a pipeline
   */
  deletePipeline(id: string): Observable<void> {
    return this.apiService.delete<void>(`/api/v1/pipelines/${id}`).pipe(
      tap(() => {
        const current = this.pipelinesSubject.value;
        this.pipelinesSubject.next(current.filter(p => p.id !== id));
        if (this.currentPipelineSubject.value?.id === id) {
          this.currentPipelineSubject.next(null);
        }
      })
    );
  }

  /**
   * Set current pipeline for editing
   */
  setCurrentPipeline(pipeline: Pipeline | null): void {
    this.currentPipelineSubject.next(pipeline);
  }

  /**
   * Get current pipeline value
   */
  getCurrentPipeline(): Pipeline | null {
    return this.currentPipelineSubject.value;
  }
}

