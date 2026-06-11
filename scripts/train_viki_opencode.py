"""
VIKI Training via opencode (deepseek-v4-flash-free).

Imports curated lessons into VIKI's SQLite knowledge DB,
then exports a comprehensive training dataset.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from viki.core.knowledge_ingestion import LearningModule


DATA_DIR = REPO_ROOT / "data"
CONFIG_DIR = REPO_ROOT / "config"
KNOWLEDGE_SEED = CONFIG_DIR / "knowledge_seed.jsonl"
TRAINING_OUTPUT = DATA_DIR / "training_dataset_opencode.jsonl"


def import_knowledge_seed(learning: LearningModule) -> str:
    return learning.import_lessons_from_jsonl(
        str(KNOWLEDGE_SEED),
        reinforce=True,
        source_task="opencode_training",
    )


def export_comprehensive_dataset(learning: LearningModule) -> str:
    return learning.export_training_dataset(
        str(TRAINING_OUTPUT),
        format="jsonl",
        min_access_count=1,
        include_failures=True,
    )


def generate_enhanced_dataset() -> str:
    """Generate additional training rows that go beyond lesson format."""
    rows = [
        {
            "text": (
                "### Instruction:\n"
                "Help me debug this Angular component issue.\n"
                "### Input:\n"
                "My component uses OnPush change detection but the view doesn't "
                "update when an @Input() changes from the parent.\n"
                "### Response:\n"
                "With OnPush, change detection only runs when:\n"
                "1. An @Input() reference changes (new object reference, not mutation)\n"
                "2. An event originates from the component or its children\n"
                "3. You manually call ChangeDetectorRef.markForCheck()\n"
                "4. An async pipe receives a new value\n\n"
                "If you're mutating an object passed via @Input(), the reference "
                "stays the same and OnPush won't detect it. Solutions:\n"
                "- Create a new object reference instead of mutating\n"
                "- Use ChangeDetectorRef.markForCheck() after the mutation\n"
                "- Switch the @Input() to use a signal\n"
                "- Use an observable with the async pipe"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "What's the best way to structure an Angular project?\n"
                "### Input:\n"
                "Feature modules vs standalone components in a large enterprise app\n"
                "### Response:\n"
                "For Angular 17+ projects, use standalone components as the default. "
                "Organize by feature domains:\n\n"
                "src/app/\n"
                "  core/          # Singleton services, guards, interceptors\n"
                "  shared/        # Reusable components, directives, pipes\n"
                "  features/\n"
                "    auth/        # Login, register, forgot-password\n"
                "    dashboard/   # Dashboard with lazy-loaded route\n"
                "    settings/    # User settings\n"
                "  layouts/       # Layout components (auth layout, app layout)\n\n"
                "Each feature is a route with loadComponent for lazy loading. "
                "Shared module exports common UI components. "
                "Core module (with providedIn: 'root') handles app-wide state. "
                "Use barrel (index.ts) exports for clean public APIs."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How do I optimize Angular bundle size?\n"
                "### Input:\n"
                "My production bundle is too large\n"
                "### Response:\n"
                "Bundle optimization strategies by impact:\n\n"
                "1. Enable Angular's optimization flags in angular.json:\n"
                "   - optimization: true (enables scripts/css/fonts inlining)\n"
                "   - buildOptimizer: true\n"
                "   - aot: true\n\n"
                "2. Tree-shake third-party libraries:\n"
                "   - Import only what you need: import { debounceTime } from 'rxjs/operators'\n"
                "   - Use date-fns over moment.js (tree-shakeable)\n"
                "   - Use lodash-es instead of lodash\n\n"
                "3. Lazy-load routes with loadComponent:\n"
                "   { path: 'admin', loadComponent: () => import('./admin/admin.component') }\n\n"
                "4. Analyze with source-map-explorer or webpack-bundle-analyzer\n"
                "5. Use Angular's NgOptimizedImage for responsive images\n"
                "6. Set budgets in angular.json to catch regressions in CI"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How should I implement state management in Angular?\n"
                "### Input:\n"
                "NgRx vs Signals vs service-based state\n"
                "### Response:\n"
                "Choose based on app complexity:\n\n"
                "Small apps (< 5 features): Use Angular services with signals.\n"
                "  @Injectable({ providedIn: 'root' })\n"
                "  export class AuthService {\n"
                "    private user = signal<User | null>(null);\n"
                "    readonly user$ = this.user.asReadonly();\n"
                "    setUser(u: User) { this.user.set(u); }\n"
                "  }\n\n"
                "Medium apps (5-15 features): Add NgRx Component Store or "
                "simple service with BehaviorSubject.\n\n"
                "Large apps (15+ features): NgRx with Store DevTools for "
                "time-travel debugging, action logging, and middleware. "
                "Use createActionGroup, createReducer, createEffect for "
                "type-safe boilerplate. Consider NgRx SignalStore for "
                "newer code that doesn't need the classic reducer pattern.\n\n"
                "Key principle: colocate state close to where it's consumed. "
                "Not everything needs to be in a central store."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "What TypeScript patterns make code more maintainable?\n"
                "### Input:\n"
                "Best practices for TypeScript in Angular\n"
                "### Response:\n"
                "1. Enable strict mode: strict: true in tsconfig.json\n"
                "2. Use explicit return types on public methods\n"
                "3. Prefer readonly arrays and properties\n"
                "4. Use discriminated unions over optional fields:\n"
                "   type Result<T> = \n"
                "     | { status: 'loading' }\n"
                "     | { status: 'success'; data: T }\n"
                "     | { status: 'error'; error: string }\n"
                "5. Use satisfies operator (TS 4.9+) to validate types "
                "without widening\n"
                "6. Prefer interfaces for public APIs, types for unions\n"
                "7. Use branded types for IDs:\n"
                "   type UserId = string & { __brand: 'UserId' }\n"
                "8. Avoid any: use unknown and narrow with type guards"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How do I set up Angular SSR with Angular 18+?\n"
                "### Input:\n"
                "Server-side rendering setup steps\n"
                "### Response:\n"
                "Angular 18+ uses @angular/ssr package (replaced Universal):\n\n"
                "1. Add SSR to existing project:\n"
                "   ng add @angular/ssr\n\n"
                "2. Or create new with SSR:\n"
                "   ng new my-app --ssr\n\n"
                "3. Key files generated:\n"
                "   - server.ts: Express server with Angular engine\n"
                "   - src/app/app.config.server.ts: Server-specific config\n"
                "   - src/main.server.ts: Server bootstrap\n\n"
                "4. Build and serve:\n"
                "   npm run build  # Builds both client and server bundles\n"
                "   npm run serve  # Starts Node.js server with SSR\n\n"
                "5. Hydration is automatic. Add provideClientHydration() "
                "to app config for full event replay.\n\n"
                "6. Avoid using browser-specific APIs (window, document) "
                "in constructors. Use afterNextRender or isPlatformBrowser.\n\n"
                "7. For dynamic content that shouldn't be server-rendered, "
                "use ngSkipHydration attribute."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How do I create a custom Angular form control?\n"
                "### Input:\n"
                "Implement ControlValueAccessor for a custom input\n"
                "### Response:\n"
                "Implement ControlValueAccessor interface:\n\n"
                "@Component({\n"
                "  selector: 'app-custom-input',\n"
                "  template: `...`,\n"
                "  providers: [{\n"
                "    provide: NG_VALUE_ACCESSOR,\n"
                "    useExisting: CustomInputComponent,\n"
                "    multi: true,\n"
                "  }]\n"
                "})\n"
                "export class CustomInputComponent implements ControlValueAccessor {\n"
                "  private onChange: (val: any) => void = () => {};\n"
                "  private onTouched: () => void = () => {};\n"
                "  disabled = false;\n"
                "  value: any;\n\n"
                "  writeValue(val: any): void {\n"
                "    this.value = val;\n"
                "  }\n"
                "  registerOnChange(fn: any): void {\n"
                "    this.onChange = fn;\n"
                "  }\n"
                "  registerOnTouched(fn: any): void {\n"
                "    this.onTouched = fn;\n"
                "  }\n"
                "  setDisabledState(isDisabled: boolean): void {\n"
                "    this.disabled = isDisabled;\n"
                "  }\n\n"
                "  onInputChange(val: any) {\n"
                "    this.value = val;\n"
                "    this.onChange(val);\n"
                "    this.onTouched();\n"
                "  }\n"
                "}"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "What's the best approach for testing Angular components?\n"
                "### Input:\n"
                "Component testing strategy\n"
                "### Response:\n"
                "Layer your tests by granularity:\n\n"
                "1. UNIT TESTS (Jest/Karma + TestBed):\n"
                "   - Test component logic in isolation\n"
                "   - Mock all dependencies (services, child components)\n"
                "   - Test all states: loading, empty, error, success\n\n"
                "2. INTEGRATION TESTS (Jest + TestBed):\n"
                "   - Test a component with its immediate children\n"
                "   - Use real services with mocked HTTP (HttpClientTesting)"
                "   - Verify component interaction and data flow\n\n"
                "3. E2E TESTS (Playwright/Cypress):\n"
                "   - Test full user journeys\n"
                "   - Verify against real API (or mocked via MSW)\n"
                "   - Cover critical paths: login, search, checkout\n\n"
                "Angular Testing Library (@testing-library/angular) "
                "encourages testing behavior rather than implementation. "
                "Query by role, label, and text rather than CSS selectors."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How do I implement i18n in Angular?\n"
                "### Input:\n"
                "Internationalization setup\n"
                "### Response:\n"
                "Angular has built-in i18n:\n\n"
                "1. Add localization in template:\n"
                "   <h1 i18n=\"@@welcomeHeader\">Welcome</h1>\n"
                "   <p i18n=\"@@description\">\n"
                "     Hello {name, plural, one {friend} other {friends}}!\n"
                "   </p>\n\n"
                "2. Extract translation template:\n"
                "   ng extract-i18n --output-path src/locale\n"
                "   Generates messages.xlf\n\n"
                "3. Create translations per language:\n"
                "   - src/locale/messages.si.xlf (Sinhala)\n"
                "   - src/locale/messages.ta.xlf (Tamil)\n\n"
                "4. Configure in angular.json:\n"
                "   \"i18n\": {\n"
                "     \"sourceLocale\": \"en-US\",\n"
                "     \"locales\": {\n"
                "       \"si\": \"src/locale/messages.si.xlf\"\n"
                "     }\n"
                "   }\n\n"
                "5. Build per locale:\n"
                "   ng build --localize\n\n"
                "6. For runtime language switching (Angular 18+):\n"
                "   Use $localize tag and @angular/localize init"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "What should I know about Angular signals?\n"
                "### Input:\n"
                "Angular signals deep dive\n"
                "### Response:\n"
                "Angular signals (v16+): reactive primitives for state management.\n\n"
                "Types:\n"
                "  - signal<T>(value): Writable signal\n"
                "  - computed<T>(() => expr): Read-only derived signal\n"
                "  - effect(() => {...}): Side effect (runs on signal changes)\n\n"
                "Key benefits:\n"
                "  - Zone.js independent: signals can work without zone\n"
                "  - Fine-grained reactivity: only re-render what changed\n"
                "  - Type-safe: full TypeScript integration\n"
                "  - Composable: combine signals with computed()\n\n"
                "Best practices:\n"
                "  - Use signal() for component-local state\n"
                "  - Use computed() for derived values (cached, lazy)\n"
                "  - Use effect() sparingly (mostly for interop with RxJS)\n"
                "  - Expose signals as readonly$ = this.state.asReadonly()\n"
                "  - Use .update() for mutation-based changes\n"
                "  - Use .set() for replacement\n\n"
                "Signal vs RxJS:\n"
                "  - Signals: synchronous, simple, local state\n"
                "  - RxJS: async, streams, complex compositions\n"
                "  - toObservable() and toSignal() bridge both worlds"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How do I handle Angular error handling globally?\n"
                "### Input:\n"
                "Global error handling strategy\n"
                "### Response:\n"
                "Implement multiple layers:\n\n"
                "1. HTTP Interceptor:\n"
                "   @Injectable()\n"
                "   export class ErrorInterceptor implements HttpInterceptor {\n"
                "     intercept(req: HttpRequest<any>, next: HttpHandler) {\n"
                "       return next.handle(req).pipe(\n"
                "         catchError((err) => {\n"
                "           if (err.status === 401) { /* redirect login */ }\n"
                "           if (err.status === 500) { /* show toast */ }\n"
                "           return throwError(() => err);\n"
                "         })\n"
                "       );\n"
                "     }\n"
                "   }\n\n"
                "2. Global Error Handler:\n"
                "   @Injectable()\n"
                "   export class GlobalErrorHandler implements ErrorHandler {\n"
                "     handleError(error: any) {\n"
                "       // Log to monitoring (Sentry, Datadog)\n"
                "       // Show user-friendly notification\n"
                "     }\n"
                "   }\n"
                "   providers: [{ provide: ErrorHandler, useClass: GlobalErrorHandler }]\n\n"
                "3. Try-catch in async operations\n"
                "4. ErrorComponent for critical failures\n"
                "5. Router error handling for lazy-load failures\n\n"
                "Always distinguish between:\n"
                "  - Expected errors (validation, 404): handle gracefully\n"
                "  - Unexpected errors (network, server crash): notify user + log"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How do I set up ESLint with Angular?\n"
                "### Input:\n"
                "Linting configuration for Angular projects\n"
                "### Response:\n"
                "Use angular-eslint (v18+):\n\n"
                "1. Install: ng add @angular-eslint/schematics\n\n"
                "2. Key config in .eslintrc.json:\n"
                "   {\n"
                "     \"rules\": {\n"
                "       \"@angular-eslint/component-selector\": [\"error\", {\n"
                "         \"type\": \"element\",\n"
                "         \"prefix\": \"app\",\n"
                "         \"style\": \"kebab-case\"\n"
                "       }],\n"
                "       \"@angular-eslint/directive-selector\": [\"error\", {\n"
                "         \"type\": \"attribute\",\n"
                "         \"prefix\": \"app\",\n"
                "         \"style\": \"camelCase\"\n"
                "       }],\n"
                "       \"@typescript-eslint/explicit-function-return-type\": \"warn\",\n"
                "       \"@typescript-eslint/no-unused-vars\": [\"error\", {\n"
                "         \"argsIgnorePattern\": \"^_\"\n"
                "       }]\n"
                "     }\n"
                "   }\n\n"
                "3. Recommended rule sets:\n"
                "   - @angular-eslint/recommended\n"
                "   - @typescript-eslint/recommended\n"
                "   - @angular-eslint/template/recommended (for HTML)\n\n"
                "4. Add lint-staged + husky for pre-commit linting\n"
                "5. Use override blocks for spec and config files"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "What's the best way to manage Angular environments?\n"
                "### Input:\n"
                "Environment configuration across dev/staging/prod\n"
                "### Response:\n"
                "Angular file replacement system:\n\n"
                "1. Base type definition:\n"
                "   // src/environments/environment.ts\n"
                "   export const environment = {\n"
                "     production: false,\n"
                "     apiUrl: 'http://localhost:3000/api',\n"
                "   };\n\n"
                "2. Production override:\n"
                "   // src/environments/environment.prod.ts\n"
                "   export const environment = {\n"
                "     production: true,\n"
                "     apiUrl: 'https://api.example.com',\n"
                "   };\n\n"
                "3. angular.json fileReplacement:\n"
                "   \"configurations\": {\n"
                "     \"production\": {\n"
                "       \"fileReplacements\": [{\n"
                "         \"replace\": \"src/environments/environment.ts\",\n"
                "         \"with\": \"src/environments/environment.prod.ts\"\n"
                "       }]\n"
                "     }\n"
                "   }\n\n"
                "4. For Docker/CI: use runtime config via window.__env\n"
                "   - Create env.js served by your web server\n"
                "   - Load it before Angular bootstraps\n"
                "   - Merge into environment during APP_INITIALIZER"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How do I migrate from NgModules to standalone?\n"
                "### Input:\n"
                "Migration strategy for large Angular apps\n"
                "### Response:\n"
                "Incremental migration approach:\n\n"
                "Phase 1: Preparation\n"
                "  - Upgrade to Angular 16+ (standalone compatible)\n"
                "  - Add standalone: true to existing components one by one\n"
                "  - Components with standalone: true can still be declared\n"
                "    in NgModules during migration\n\n"
                "Phase 2: Low-hanging fruit\n"
                "  - Convert pure pipes and directives first (no deps)\n"
                "  - Convert leaf components (no child component deps)\n"
                "  - Use imports array instead of NgModule imports\n\n"
                "Phase 3: Feature modules\n"
                "  - Convert feature modules with routing\n"
                "  - Replace loadChildren: () => import(..., 'module')\n"
                "    with loadComponent: () => import(...)\n"
                "  - Remove the feature NgModule after converting all parts\n\n"
                "Phase 4: Shared modules\n"
                "  - Convert shared module components to standalone\n"
                "  - Replace NgModule exports with direct imports\n\n"
                "Phase 5: App module\n"
                "  - Convert AppModule to bootstrapApplication + app.config.ts\n"
                "  - Move providers to appConfig\n\n"
                "Key: Both approaches coexist. Do one component at a time."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "How should I handle Angular route guards?\n"
                "### Input:\n"
                "Auth guards and route protection\n"
                "### Response:\n"
                "Angular 15+ uses functional route guards:\n\n"
                "export const authGuard: CanActivateFn = (route, state) => {\n"
                "  const auth = inject(AuthService);\n"
                "  const router = inject(Router);\n"
                "  \n"
                "  if (auth.isAuthenticated()) {\n"
                "    return true;\n"
                "  }\n"
                "  \n"
                "  // Store attempted URL for redirect after login\n"
                "  router.navigate(['/login'], {\n"
                "    queryParams: { returnUrl: state.url }\n"
                "  });\n"
                "  return false;\n"
                "};\n\n"
                "Route definition:\n"
                "{\n"
                "  path: 'dashboard',\n"
                "  loadComponent: () => import('./dashboard/dashboard.component'),\n"
                "  canActivate: [authGuard],\n"
                "  canActivateChild: [childGuard],\n"
                "  canDeactivate: [unsavedChangesGuard],\n"
                "  resolve: { user: userResolver }\n"
                "}\n\n"
                "Use canMatch (v15+) instead of canLoad for lazy modules. "
                "canActivate runs after the module is loaded; canMatch "
                "prevents loading entirely."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "VIKI behavioral rule\n"
                "### Input:\n"
                "How to handle concurrent requests and task switching\n"
                "### Response:\n"
                "VIKI should maintain clear state boundaries between concurrent tasks. "
                "When switching contexts, briefly acknowledge the switch and maintain "
                "separate mental models for each ongoing task. If a task is partially "
                "complete, preserve intermediate state and offer to resume when the "
                "user returns to it. Never drop context silently."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "VIKI behavioral rule\n"
                "### Input:\n"
                "Knowledge validation threshold\n"
                "### Response:\n"
                "VIKI should only commit lessons to long-term memory when confidence "
                "exceeds 0.8. Lower-confidence observations should be noted but not "
                "reinforced for training export. This prevents noise from polluting "
                "the forge pipeline. Lessons can be reinforced through repeated "
                "confirmation (access_count increments increase reliability)."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "VIKI knowledge\n"
                "### Input:\n"
                "Frontend performance metrics to track\n"
                "### Response:\n"
                "Core Web Vitals: LCP (< 2.5s), INP (< 200ms), CLS (< 0.1). "
                "Additional metrics: TTFB (< 800ms), FCP (< 1.8s), TBT (< 200ms). "
                "Bundle size budgets: initial JS < 200KB (gzipped), total < 500KB. "
                "Use Lighthouse CI to track regressions. Set performance budgets "
                "as CI gates to prevent regressions from reaching production."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "VIKI knowledge\n"
                "### Input:\n"
                "Monorepo structure best practices\n"
                "### Response:\n"
                "Use Nx or Turborepo for monorepo management. Benefits: shared "
                "tooling config, dependency graph awareness, incremental builds, "
                "cached task execution. Structure: apps/ (multiple applications), "
                "libs/ (shared libraries), tools/ (custom scripts/plugins). "
                "Each lib should have a clear public API via barrel exports. "
                "Enforce boundaries with ESLint rules (import/no-restricted-paths)."
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "VIKI knowledge\n"
                "### Input:\n"
                "Docker best practices for Angular apps\n"
                "### Response:\n"
                "Multi-stage Docker build:\n"
                "1. Stage 1 (builder): FROM node:20-alpine, npm ci, npm run build\n"
                "2. Stage 2 (server): FROM nginx:alpine\n"
                "   - COPY dist/ /usr/share/nginx/html\n"
                "   - Use custom nginx.conf with proper cache headers\n"
                "   - Serve index.html for SPA fallback (try_files $uri /index.html)\n\n"
                "Optimizations:\n"
                "  - Use .dockerignore to exclude node_modules, .git\n"
                "  - Use build args for environment config\n"
                "  - Compress with gzip/brotli at nginx level\n"
                "  - Set immutable cache for hashed assets (max-age=1y)\n"
                "  - Set no-cache for index.html"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "VIKI knowledge\n"
                "### Input:\n"
                "Accessibility (a11y) checklist for Angular apps\n"
                "### Response:\n"
                "WCAG 2.1 AA minimum checklist:\n"
                "1. Semantic HTML: use <nav>, <main>, <aside>, <button> correctly\n"
                "2. ARIA: role, aria-label, aria-describedby on custom interactive elements\n"
                "3. Keyboard: all interactive elements reachable and operable via keyboard\n"
                "4. Focus: visible focus indicators (minimum 2:1 contrast ratio)\n"
                "5. Color: minimum 4.5:1 contrast for text, 3:1 for large text\n"
                "6. Forms: labels associated with inputs, clear error messages\n"
                "7. Images: alt text on all meaningful images, aria-hidden on decorative\n"
                "8. Screen readers: announce dynamic content changes with aria-live\n"
                "9. Motion: respect prefers-reduced-motion, avoid auto-playing content\n"
                "10. Testing: axe DevTools, Lighthouse a11y audit, screen reader testing"
            )
        },
        {
            "text": (
                "### Instruction:\n"
                "VIKI knowledge\n"
                "### Input:\n"
                "CI/CD pipeline for Angular apps\n"
                "### Response:\n"
                "Recommended CI pipeline stages:\n"
                "1. lint: eslint + prettier check\n"
                "2. type-check: npx tsc --noEmit (incremental for speed)\n"
                "3. test: jest --coverage (unit + integration)\n"
                "4. build: ng build --configuration production\n"
                "5. e2e: playwright test --project=chromium\n"
                "6. bundle-analysis: source-map-explorer or bundlesize\n"
                "7. deploy: to staging/prod via CD (GitHub Actions, GitLab CI)\n\n"
                "Cache: node_modules, .angular/cache, playwright browsers. "
                "Use nx affected commands to only test/build changed projects. "
                "Fail the pipeline on bundle size budget violations."
            )
        },
    ]
    out_path = REPO_ROOT / "data" / "training_enhanced.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    return str(out_path)


def main():
    print("=== VIKI Training via opencode (deepseek-v4-flash-free) ===\n")
    learning = LearningModule(str(DATA_DIR))

    # Step 1: Import knowledge seed
    print("[1/3] Importing knowledge seed...")
    msg = import_knowledge_seed(learning)
    print(f"  {msg}")

    # Step 2: Export comprehensive dataset
    print("\n[2/3] Exporting comprehensive training dataset...")
    msg = export_comprehensive_dataset(learning)
    print(f"  {msg}")

    # Step 3: Generate enhanced training dataset
    print("\n[3/3] Generating enhanced training dataset...")
    path = generate_enhanced_dataset()
    total_lessons = learning.get_total_lesson_count()
    stable = learning.get_stable_lesson_count()
    print(f"  Generated -> {path}")
    print(f"\n  Knowledge DB: {total_lessons} total lessons, {stable} reinforced (count > 1)")


if __name__ == "__main__":
    main()
