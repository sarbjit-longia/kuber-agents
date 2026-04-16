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
    path: 'terms',
    loadComponent: () => import('./features/legal/terms/terms.component').then(m => m.TermsComponent)
  },
  {
    path: 'privacy',
    loadComponent: () => import('./features/legal/privacy/privacy.component').then(m => m.PrivacyComponent)
  },
  {
    path: 'disclaimer',
    loadComponent: () => import('./features/legal/disclaimer/disclaimer.component').then(m => m.DisclaimerComponent)
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
    path: 'backtests',
    loadComponent: () => import('./features/backtests/home/backtests-home.component').then(m => m.BacktestsHomeComponent),
    canActivate: [authGuard]
  },
  {
    path: 'backtests/workspace',
    loadComponent: () => import('./features/backtests/backtests-page.component').then(m => m.BacktestsPageComponent),
    canActivate: [authGuard]
  },
  {
    path: 'backtests/workspace/:id',
    loadComponent: () => import('./features/backtests/backtests-page.component').then(m => m.BacktestsPageComponent),
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
    path: 'marketplace',
    loadComponent: () => import('./features/strategies/strategies-marketplace.component').then(m => m.StrategiesMarketplaceComponent),
    canActivate: [authGuard]
  },
  {
    path: 'strategies',
    loadComponent: () => import('./features/strategies/my-strategies.component').then(m => m.MyStrategiesComponent),
    canActivate: [authGuard]
  },
  {
    path: 'strategies/:id',
    loadComponent: () => import('./features/strategies/strategy-detail.component').then(m => m.StrategyDetailComponent),
    canActivate: [authGuard]
  },
  {
    path: 'monitoring',
    loadComponent: () => import('./features/monitoring/monitoring.component').then(m => m.MonitoringComponent),
    canActivate: [authGuard]
  },
  {
    path: 'monitoring/:id/report',
    loadComponent: () => import('./features/monitoring/execution-report/execution-report.component').then(m => m.ExecutionReportComponent),
    canActivate: [authGuard]
  },
  {
    path: 'monitoring/:id',
    loadComponent: () => import('./features/monitoring/execution-detail/execution-detail.component').then(m => m.ExecutionDetailComponent),
    canActivate: [authGuard]
  },
  {
    path: 'scanners/new',
    loadComponent: () => import('./features/scanner-management/scanner-editor/scanner-editor.component').then(m => m.ScannerEditorComponent),
    canActivate: [authGuard]
  },
  {
    path: 'scanners/:id/edit',
    loadComponent: () => import('./features/scanner-management/scanner-editor/scanner-editor.component').then(m => m.ScannerEditorComponent),
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
    path: 'sms-consent',
    loadComponent: () => import('./features/sms-consent/sms-consent.component').then(m => m.SmsConsentComponent)
  },
  {
    path: 'approve/:token',
    loadComponent: () => import('./features/approval/approval.component').then(m => m.ApprovalComponent)
  },
  {
    path: '**',
    redirectTo: '/dashboard'
  }
];
