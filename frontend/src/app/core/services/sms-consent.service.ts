import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class SmsConsentService {
  private apiUrl = `${environment.apiUrl}/api/v1/sms-consent`;

  constructor(private http: HttpClient) {}

  submitPublicConsent(phoneNumber: string): Observable<{ status: string; message: string }> {
    return this.http.post<{ status: string; message: string }>(`${this.apiUrl}/public`, {
      phone_number: phoneNumber,
      consent: true
    });
  }
}
