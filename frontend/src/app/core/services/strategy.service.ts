import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from './api.service';
import {
  Strategy,
  StrategyListResponse,
  StrategyUpdate,
  StrategyVisibility,
  StrategyVoteResponse,
} from '../models/strategy.model';

@Injectable({
  providedIn: 'root'
})
export class StrategyService {
  constructor(private apiService: ApiService) {}

  getMarketplace(sort: 'most_voted' | 'most_used' | 'newest' = 'most_voted', q?: string): Observable<StrategyListResponse> {
    const params = new URLSearchParams({ sort });
    if (q?.trim()) {
      params.set('q', q.trim());
    }
    return this.apiService.get<StrategyListResponse>(`/api/v1/strategies/marketplace?${params.toString()}`);
  }

  getMyStrategies(): Observable<StrategyListResponse> {
    return this.apiService.get<StrategyListResponse>('/api/v1/strategies/my');
  }

  getAdminPendingStrategies(): Observable<StrategyListResponse> {
    return this.apiService.get<StrategyListResponse>('/api/v1/strategies/admin/pending');
  }

  getStrategy(id: string): Observable<Strategy> {
    return this.apiService.get<Strategy>(`/api/v1/strategies/${id}`);
  }

  updateStrategy(id: string, payload: StrategyUpdate): Observable<Strategy> {
    return this.apiService.patch<Strategy>(`/api/v1/strategies/${id}`, payload);
  }

  deleteStrategy(id: string): Observable<void> {
    return this.apiService.delete<void>(`/api/v1/strategies/${id}`);
  }

  submitStrategy(id: string): Observable<Strategy> {
    return this.apiService.post<Strategy>(`/api/v1/strategies/${id}/submit`, {});
  }

  reviewStrategy(id: string, approved: boolean, reviewNotes?: string): Observable<Strategy> {
    return this.apiService.post<Strategy>(`/api/v1/strategies/${id}/publish-review`, {
      approved,
      review_notes: reviewNotes,
    });
  }

  voteForStrategy(id: string): Observable<StrategyVoteResponse> {
    return this.apiService.post<StrategyVoteResponse>(`/api/v1/strategies/${id}/vote`, {});
  }

  createPipelineFromStrategy(id: string): Observable<{ pipeline_id: string }> {
    return this.apiService.post<{ pipeline_id: string }>(`/api/v1/strategies/${id}/create-pipeline`, {});
  }

  exportPipelineAsStrategy(pipelineId: string): Observable<Strategy> {
    return this.apiService.post<Strategy>(`/api/v1/pipelines/${pipelineId}/export-strategy`, {});
  }
}
