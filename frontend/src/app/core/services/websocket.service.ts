/**
 * WebSocket Service
 * 
 * Service for real-time execution updates via WebSocket.
 */

import { Injectable } from '@angular/core';
import { Subject, Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { WebSocketMessage } from '../models/pipeline.model';
import { AuthService } from './auth.service';

@Injectable({
  providedIn: 'root'
})
export class WebSocketService {
  private ws: WebSocket | null = null;
  private messagesSubject = new Subject<WebSocketMessage>();
  public messages$: Observable<WebSocketMessage> = this.messagesSubject.asObservable();
  
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private connected = false;

  constructor(private authService: AuthService) {}

  /**
   * Connect to WebSocket server
   */
  connect(): void {
    const token = this.authService.getToken();
    if (!token) {
      console.error('No authentication token available for WebSocket');
      return;
    }

    // Convert HTTP URL to WebSocket URL
    const wsUrl = environment.apiUrl
      .replace('http://', 'ws://')
      .replace('https://', 'wss://');

    const url = `${wsUrl}/api/v1/ws/executions?token=${token}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.connected = true;
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        this.messagesSubject.next(message);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.connected = false;
      this.reconnect();
    };
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.connected = false;
    }
  }

  /**
   * Subscribe to execution updates
   */
  subscribeToExecution(executionId: string): void {
    if (!this.connected || !this.ws) {
      console.warn('WebSocket not connected');
      return;
    }

    this.send({
      action: 'subscribe',
      execution_id: executionId
    });
  }

  /**
   * Unsubscribe from execution updates
   */
  unsubscribeFromExecution(executionId: string): void {
    if (!this.connected || !this.ws) {
      return;
    }

    this.send({
      action: 'unsubscribe',
      execution_id: executionId
    });
  }

  /**
   * Send ping to keep connection alive
   */
  ping(): void {
    if (this.connected && this.ws) {
      this.send({ action: 'ping' });
    }
  }

  /**
   * Send message to WebSocket server
   */
  private send(data: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  /**
   * Reconnect with exponential backoff
   */
  private reconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;

    console.log(`Reconnecting in ${delay}ms... (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * Check if WebSocket is connected
   */
  isConnected(): boolean {
    return this.connected;
  }
}

