import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface ToolMetadata {
  tool_type: string;
  name: string;
  description: string;
  category: string;
  version: string;
  icon?: string;
  requires_credentials: boolean;
  config_schema: any;
}

@Injectable({
  providedIn: 'root'
})
export class ToolService {
  private toolApiUrl = '/api/v1/tools';

  constructor(private apiService: ApiService) { }

  getTools(): Observable<ToolMetadata[]> {
    return this.apiService.get<ToolMetadata[]>(this.toolApiUrl);
  }

  getToolsByCategory(category: string): Observable<ToolMetadata[]> {
    return this.apiService.get<ToolMetadata[]>(`${this.toolApiUrl}/category/${category}`);
  }

  getToolMetadata(toolType: string): Observable<ToolMetadata> {
    return this.apiService.get<ToolMetadata>(`${this.toolApiUrl}/${toolType}`);
  }
}

