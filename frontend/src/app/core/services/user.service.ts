import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface TelegramConfig {
  enabled: boolean;
  chat_id: string | null;
  is_configured: boolean;
}

export interface TelegramConfigUpdate {
  bot_token: string;
  chat_id: string;
  enabled: boolean;
}

export interface TelegramTestRequest {
  bot_token: string;
  chat_id: string;
}

export interface TelegramTestResponse {
  status: string;
  message: string;
  message_id?: number;
}

@Injectable({
  providedIn: 'root'
})
export class UserService {
  private apiUrl = `${environment.apiUrl}/api/v1/users`;

  constructor(private http: HttpClient) {}

  /**
   * Get current user's Telegram configuration
   */
  getTelegramConfig(): Observable<TelegramConfig> {
    return this.http.get<TelegramConfig>(`${this.apiUrl}/me/telegram`);
  }

  /**
   * Update Telegram configuration
   */
  updateTelegramConfig(botToken: string, chatId: string, enabled: boolean = true): Observable<TelegramConfig> {
    const config: TelegramConfigUpdate = {
      bot_token: botToken,
      chat_id: chatId,
      enabled
    };
    return this.http.put<TelegramConfig>(`${this.apiUrl}/me/telegram`, config);
  }

  /**
   * Test Telegram connection without saving
   */
  testTelegramConnection(botToken: string, chatId: string): Observable<TelegramTestResponse> {
    const testRequest: TelegramTestRequest = {
      bot_token: botToken,
      chat_id: chatId
    };
    return this.http.post<TelegramTestResponse>(`${this.apiUrl}/me/telegram/test`, testRequest);
  }

  /**
   * Delete Telegram configuration
   */
  deleteTelegramConfig(): Observable<any> {
    return this.http.delete(`${this.apiUrl}/me/telegram`);
  }
}
