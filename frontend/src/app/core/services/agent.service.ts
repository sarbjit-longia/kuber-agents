/**
 * Agent Service
 * 
 * Service for fetching and managing AI agents.
 */

import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject } from 'rxjs';
import { tap } from 'rxjs/operators';
import { ApiService } from './api.service';
import { Agent } from '../models/pipeline.model';

@Injectable({
  providedIn: 'root'
})
export class AgentService {
  private agentsSubject = new BehaviorSubject<Agent[]>([]);
  public agents$ = this.agentsSubject.asObservable();

  constructor(private apiService: ApiService) {}

  /**
   * Load all available agents
   */
  loadAgents(): Observable<Agent[]> {
    return this.apiService.get<Agent[]>('/api/v1/agents').pipe(
      tap(agents => this.agentsSubject.next(agents))
    );
  }

  /**
   * Get agents by category
   */
  getAgentsByCategory(category: string): Observable<Agent[]> {
    return this.apiService.get<Agent[]>(`/api/v1/agents/category/${category}`);
  }

  /**
   * Get specific agent metadata
   */
  getAgentMetadata(agentType: string): Observable<Agent> {
    return this.apiService.get<Agent>(`/api/v1/agents/${agentType}`);
  }

  /**
   * Get current agents from subject
   */
  getCurrentAgents(): Agent[] {
    return this.agentsSubject.value;
  }

  /**
   * Get agent by type from current list
   */
  getAgentByType(agentType: string): Agent | undefined {
    return this.agentsSubject.value.find(a => a.agent_type === agentType);
  }
}

