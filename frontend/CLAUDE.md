# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- **Dev server:** `npm start` (runs on http://localhost:4200, proxies to backend at localhost:8000)
- **Production build:** `npm run build` (output in `dist/frontend/`)
- **Watch mode:** `npm run watch`
- **Tests:** `npm test` (Karma + Jasmine, launches Chrome)
- **Generate component:** `npx ng generate component features/<name> --standalone`

## Architecture

Angular 17 standalone application (no NgModules) for a trading pipeline platform. Dark theme with Angular Material.

### Project Layout

```
src/app/
├── core/                  # Singletons: services, guards, interceptors, models, navbar
│   ├── services/          # Domain services (ApiService, AuthService, PipelineService, etc.)
│   ├── guards/            # Functional authGuard (CanActivateFn)
│   ├── interceptors/      # Functional authInterceptor (JWT Bearer + 401 handling)
│   ├── models/            # TypeScript interfaces (user, pipeline, execution, scanner)
│   └── components/        # NavbarComponent
├── features/              # Lazy-loaded pages via loadComponent() in app.routes.ts
│   ├── landing/           # Public landing page
│   ├── how-it-works/      # Public info page
│   ├── auth/              # login, register
│   ├── dashboard/         # Main dashboard (protected)
│   ├── pipelines/         # Pipeline CRUD
│   ├── pipeline-builder-guided/  # Guided pipeline builder with drag-and-drop
│   ├── monitoring/        # Execution monitoring + detail views
│   ├── scanner-management/
│   └── user-settings/
├── shared/                # Reusable components, pipes, dialogs
│   ├── pipes/             # local-date, markdown-to-html
│   └── components/        # trading-chart, json-schema-form, confirm-dialog, etc.
└── app.routes.ts          # All route definitions (standalone lazy loading)
```

### Key Patterns

- **All components are standalone** — use `standalone: true` and import dependencies directly in the component's `imports` array. No shared modules.
- **Routes use `loadComponent()`** for lazy loading, not `loadChildren()` with modules.
- **State management is service-based** — RxJS `BehaviorSubject`/`Observable` in services, no NgRx. Components subscribe in `ngOnInit` and unsubscribe via `takeUntil(destroy$)` in `ngOnDestroy`.
- **API calls** go through `ApiService` (`core/services/api.service.ts`) which prepends `environment.apiUrl` to all endpoints. Backend API is at `/api/v1/*`.
- **Auth flow:** JWT stored in localStorage. `authInterceptor` attaches Bearer token to requests and redirects to `/login` on 401. `authGuard` protects routes.
- **WebSocket** for real-time execution updates via `WebSocketService` with auto-reconnect.
- **Functional guards/interceptors** (Angular 17 style, not class-based).

### Styling

- SCSS with CSS custom properties defined in `src/styles.scss` under `:root`.
- Angular Material dark theme (indigo primary, pink accent).
- Use existing CSS variables (`--bg-primary`, `--bg-card`, `--text-primary`, `--accent-primary`, `--accent-gradient`, etc.) rather than hardcoding colors.
- Component styles are in co-located `.scss` files.
- Landing page uses `max-width: 1400px` for content grids; match this in public pages.

### Environment

- Dev: `src/environments/environment.ts` — `apiUrl: http://localhost:8000`
- Prod: `src/environments/environment.prod.ts`

### TypeScript

Strict mode is enabled (`strict: true` in tsconfig.json) along with `strictTemplates`, `strictInjectionParameters`, and `noImplicitReturns`. Target is ES2022.
