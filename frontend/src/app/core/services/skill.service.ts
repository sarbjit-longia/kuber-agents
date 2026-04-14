import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from './api.service';

export interface AgentSkillAttachment {
  skill_id: string;
  version?: string | null;
  enabled: boolean;
  overrides: Record<string, any>;
}

export interface SkillSummary {
  skill_id: string;
  name: string;
  slug: string;
  version: string;
  description: string;
  agent_types: string[];
  source_type: 'system' | 'user_copy' | 'marketplace';
  status: 'active' | 'deprecated' | 'draft';
  tags: string[];
  category: string;
  recommended_tools: string[];
}

export interface SkillDetail extends SkillSummary {
  instruction_fragment: string;
  guardrails: string[];
  tool_overrides: Record<string, Record<string, any>>;
  publisher: string;
  visibility: 'private' | 'curated' | 'public';
}

@Injectable({
  providedIn: 'root'
})
export class SkillService {
  private readonly apiUrl = '/api/v1/skills';

  constructor(private apiService: ApiService) {}

  listSkills(agentType?: string): Observable<SkillSummary[]> {
    const endpoint = agentType
      ? `${this.apiUrl}?agent_type=${encodeURIComponent(agentType)}`
      : this.apiUrl;
    return this.apiService.get<SkillSummary[]>(endpoint);
  }

  getSkill(skillId: string): Observable<SkillDetail> {
    return this.apiService.get<SkillDetail>(`${this.apiUrl}/${skillId}`);
  }
}
