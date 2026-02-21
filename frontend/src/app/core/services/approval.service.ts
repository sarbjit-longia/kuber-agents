/**
 * Approval Service (Token-based)
 *
 * Used by the public /approve/:token page (SMS link).
 * Uses raw HttpClient to bypass the JWT auth interceptor.
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class ApprovalService {
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  /**
   * Get approval details by token
   */
  getApprovalByToken(token: string): Observable<any> {
    return this.http.get(`${this.baseUrl}/api/v1/approvals/${token}`);
  }

  /**
   * Approve trade by token
   */
  approveByToken(token: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/api/v1/approvals/${token}/approve`, {});
  }

  /**
   * Reject trade by token
   */
  rejectByToken(token: string, reason?: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/api/v1/approvals/${token}/reject`, {
      decision: 'reject',
      reason
    });
  }
}
