import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  BacktestCreateRequest,
  BacktestExecutionListResponse,
  BacktestReportResponse,
  BacktestRunListResponse,
  BacktestRunResult,
  BacktestRunSummary,
  BacktestStartResponse,
  BacktestTimelineResponse,
} from '../models/backtest.model';

@Injectable({
  providedIn: 'root'
})
export class BacktestService {
  private readonly apiUrl = `${environment.apiUrl}/api/v1/backtests`;

  constructor(private http: HttpClient) {}

  startBacktest(payload: BacktestCreateRequest): Observable<BacktestStartResponse> {
    return this.http.post<BacktestStartResponse>(this.apiUrl, payload);
  }

  listBacktests(skip = 0, limit = 50): Observable<BacktestRunListResponse> {
    const params = new HttpParams()
      .set('skip', skip)
      .set('limit', limit);
    return this.http.get<BacktestRunListResponse>(this.apiUrl, { params });
  }

  getBacktest(runId: string): Observable<BacktestRunSummary> {
    return this.http.get<BacktestRunSummary>(`${this.apiUrl}/${runId}`);
  }

  getBacktestResults(runId: string): Observable<BacktestRunResult> {
    return this.http.get<BacktestRunResult>(`${this.apiUrl}/${runId}/results`);
  }

  getBacktestExecutions(runId: string): Observable<BacktestExecutionListResponse> {
    return this.http.get<BacktestExecutionListResponse>(`${this.apiUrl}/${runId}/executions`);
  }

  getBacktestTimeline(runId: string): Observable<BacktestTimelineResponse> {
    return this.http.get<BacktestTimelineResponse>(`${this.apiUrl}/${runId}/timeline`);
  }

  getBacktestReport(runId: string): Observable<BacktestReportResponse> {
    return this.http.get<BacktestReportResponse>(`${this.apiUrl}/${runId}/report`);
  }

  cancelBacktest(runId: string): Observable<BacktestRunSummary> {
    return this.http.post<BacktestRunSummary>(`${this.apiUrl}/${runId}/cancel`, {});
  }
}
