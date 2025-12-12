import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface ChartAnnotation {
  shapes: any[];
  lines: any[];
  arrows: any[];
  markers: any[];
  zones: any[];
  text: any[];
}

export interface ChartData {
  meta: {
    symbol: string;
    timeframe: string;
    generated_at: string;
    candle_count: number;
  };
  candles: Array<{
    time: string | number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
  annotations: ChartAnnotation;
  indicators: Record<string, any>;
  decision: {
    action: string;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    confidence: number;
    pattern: string;
    reasoning: string;
    reasoning_steps: string[];
    conditions_met: number;
    conditions_total: number;
    instructions?: string;
    summary: {
      title: string;
      subtitle: string;
      confidence_score: number;
      conditions_met: number;
      conditions_total: number;
    };
  };
}

@Injectable({
  providedIn: 'root'
})
export class StrategyChartService {
  private readonly apiUrl = `${environment.apiUrl}/api/v1`;

  constructor(private http: HttpClient) {}

  /**
   * Get chart data for a specific execution
   */
  getChartData(executionId: string): Observable<ChartData> {
    return this.http.get<ChartData>(
      `${this.apiUrl}/executions/${executionId}/chart-data`
    );
  }
}

