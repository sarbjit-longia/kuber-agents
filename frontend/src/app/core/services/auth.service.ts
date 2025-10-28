/**
 * Authentication Service
 * 
 * Handles user authentication, token management, and auth state.
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import { Router } from '@angular/router';

import { environment } from '../../../environments/environment';
import { User, UserCreate, UserLogin, TokenResponse } from '../models/user.model';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly TOKEN_KEY = 'auth_token';
  private readonly API_URL = `${environment.apiUrl}/api/v1/auth`;
  private readonly USER_URL = `${environment.apiUrl}/api/v1/users`;

  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();

  private isAuthenticatedSubject = new BehaviorSubject<boolean>(this.hasToken());
  public isAuthenticated$ = this.isAuthenticatedSubject.asObservable();

  constructor(
    private http: HttpClient,
    private router: Router
  ) {
    // Load user on service initialization if token exists
    if (this.hasToken()) {
      this.loadCurrentUser().subscribe();
    }
  }

  /**
   * Register a new user
   */
  register(userData: UserCreate): Observable<User> {
    return this.http.post<User>(`${this.API_URL}/register`, userData);
  }

  /**
   * Login with email and password
   */
  login(credentials: UserLogin): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(`${this.API_URL}/login`, credentials).pipe(
      tap(response => {
        this.setToken(response.access_token);
        this.isAuthenticatedSubject.next(true);
        this.loadCurrentUser().subscribe();
      })
    );
  }

  /**
   * Logout the current user
   */
  logout(): void {
    this.removeToken();
    this.currentUserSubject.next(null);
    this.isAuthenticatedSubject.next(false);
    this.router.navigate(['/login']);
  }

  /**
   * Get current user profile
   */
  getCurrentUser(): Observable<User> {
    return this.http.get<User>(`${this.USER_URL}/me`);
  }

  /**
   * Load current user and update subject
   */
  private loadCurrentUser(): Observable<User> {
    return this.http.get<User>(`${this.USER_URL}/me`).pipe(
      tap(user => this.currentUserSubject.next(user))
    );
  }

  /**
   * Get stored auth token
   */
  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  /**
   * Store auth token
   */
  private setToken(token: string): void {
    localStorage.setItem(this.TOKEN_KEY, token);
  }

  /**
   * Remove auth token
   */
  private removeToken(): void {
    localStorage.removeItem(this.TOKEN_KEY);
  }

  /**
   * Check if user has a token
   */
  private hasToken(): boolean {
    return !!this.getToken();
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    return this.hasToken();
  }

  /**
   * Get current user value (synchronous)
   */
  get currentUserValue(): User | null {
    return this.currentUserSubject.value;
  }
}

