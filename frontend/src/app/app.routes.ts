/**
 * Application Routes
 */

import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/landing/landing.component').then(m => m.LandingComponent)
  },
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login/login.component').then(m => m.LoginComponent)
  },
  {
    path: 'register',
    loadComponent: () => import('./features/auth/register/register.component').then(m => m.RegisterComponent)
  },
  {
    path: 'dashboard',
    loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent),
    canActivate: [authGuard]
  },
  {
    path: 'pipeline-builder',
    loadComponent: () => import('./features/pipeline-builder/pipeline-builder.component').then(m => m.PipelineBuilderComponent),
    canActivate: [authGuard]
  },
  {
    path: 'pipeline-builder/:id',
    loadComponent: () => import('./features/pipeline-builder/pipeline-builder.component').then(m => m.PipelineBuilderComponent),
    canActivate: [authGuard]
  },
  {
    path: '**',
    redirectTo: '/dashboard'
  }
];
