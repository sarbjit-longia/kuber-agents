import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface DetectedTool {
  tool: string;
  params: Record<string, any>;
  reasoning: string;
  cost: number;
  category: string;
}

export interface ValidateInstructionsResponse {
  status: 'success' | 'partial' | 'error';
  message?: string;
  tools: DetectedTool[];
  unsupported: string[];
  total_cost: number;
  llm_cost?: number;
  summary?: string;
  confidence?: number;
  suggestions?: string;
}

export interface ValidateInstructionsRequest {
  instructions: string;
  agent_type: string;
}

@Injectable({
  providedIn: 'root'
})
export class ToolDetectionService {
  private readonly apiUrl = `${environment.apiUrl}/api/v1/agents`;

  constructor(private http: HttpClient) {}

  /**
   * Validate agent instructions and detect required tools
   */
  validateInstructions(
    instructions: string,
    agentType: string = 'strategy'
  ): Observable<ValidateInstructionsResponse> {
    const request: ValidateInstructionsRequest = {
      instructions,
      agent_type: agentType
    };

    return this.http.post<ValidateInstructionsResponse>(
      `${this.apiUrl}/validate-instructions`,
      request
    );
  }

  /**
   * Get list of all available strategy tools
   */
  getAvailableTools(): Observable<any> {
    return this.http.get(`${this.apiUrl}/tools/available`);
  }
}

