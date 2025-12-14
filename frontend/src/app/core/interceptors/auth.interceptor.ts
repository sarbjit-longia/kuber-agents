/**
 * HTTP Interceptor to add JWT token to requests and handle authentication errors
 */

import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { catchError } from 'rxjs/operators';
import { throwError } from 'rxjs';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const token = authService.getToken();

  if (token) {
    req = req.clone({
      setHeaders: {
        Authorization: `Bearer ${token}`
      }
    });
  }

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      // Handle 401 Unauthorized - token expired or invalid
      if (error.status === 401) {
        console.log('Session expired. Redirecting to login...');
        authService.logout(); // Clear token
        router.navigate(['/login'], { 
          queryParams: { 
            returnUrl: router.url,
            reason: 'session_expired'
          } 
        });
      }
      return throwError(() => error);
    })
  );
};

