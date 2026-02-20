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
    path: 'how-it-works',
    loadComponent: () => import('./features/how-it-works/how-it-works.component').then(m => m.HowItWorksComponent)
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
    path: 'pipelines',
    loadComponent: () => import('./features/pipelines/pipelines.component').then(m => m.PipelinesComponent),
    canActivate: [authGuard]
  },
  {
    path: 'pipeline-builder',
    loadComponent: () => import('./features/pipeline-builder-guided/pipeline-builder-guided.component').then(m => m.PipelineBuilderGuidedComponent),
    canActivate: [authGuard]
  },
  {
    path: 'pipeline-builder/:id',
    loadComponent: () => import('./features/pipeline-builder-guided/pipeline-builder-guided.component').then(m => m.PipelineBuilderGuidedComponent),
    canActivate: [authGuard]
  },
  {
    path: 'monitoring',
    loadComponent: () => import('./features/monitoring/monitoring.component').then(m => m.MonitoringComponent),
    canActivate: [authGuard]
  },
  {
    path: 'monitoring/:id',
    loadComponent: () => import('./features/monitoring/execution-detail/execution-detail.component').then(m => m.ExecutionDetailComponent),
    canActivate: [authGuard]
  },
  {
    path: 'scanners',
    loadComponent: () => import('./features/scanner-management/scanner-management.component').then(m => m.ScannerManagementComponent),
    canActivate: [authGuard]
  },
  {
    path: 'settings',
    loadComponent: () => import('./features/user-settings/user-settings.component').then(m => m.UserSettingsComponent),
    canActivate: [authGuard]
  },
  {
    path: '**',
    redirectTo: '/dashboard'
  }
];
