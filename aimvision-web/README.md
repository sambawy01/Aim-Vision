# aimvision-web

Federation + club coach dashboard for AIMVISION. Single-page React + TypeScript app, thin client over the FastAPI backend.

See:

- [`docs/architecture-overview.md`](../docs/architecture-overview.md) — system context, trust boundaries, and the place this app holds in the stack (component §3.4).
- [`docs/security/multi-tenant-isolation.md`](../docs/security/multi-tenant-isolation.md) — every request carries `X-Tenant-Scope`; the tenancy switcher in the AppShell is the user-facing handle on §1.1's principal model.
- [`docs/security/qr-checkin-token-spec.md`](../docs/security/qr-checkin-token-spec.md) — the QR check-in flow surfaced at `/app/checkin`. The current scaffold ships a manual-entry placeholder; Sprint 16 swaps in `html5-qrcode`.

## Stack

- Vite 5 + React 18 + TypeScript (strict)
- React Router v6 data routers (`createBrowserRouter`)
- TanStack Query v5
- Zustand (auth + tenancy stores)
- i18next + react-i18next, EN + AR, RTL toggled on `<html dir>`
- Tailwind v3.4 with WCAG-AA token set in `src/theme`
- Vitest + Testing Library + jsdom
- ESLint (with `jsx-a11y`) + Prettier

## Getting started

```bash
pnpm install
pnpm dev          # http://localhost:5173
pnpm test         # vitest watch
pnpm test --run   # one-shot
pnpm typecheck
pnpm lint
pnpm build        # production bundle in dist/
pnpm preview      # serve the built bundle
```

## Environment

All Vite envs are prefixed `VITE_AV_`:

| var                     | default                 | meaning                                        |
| ----------------------- | ----------------------- | ---------------------------------------------- |
| `VITE_AV_API_BASE_URL`  | `http://localhost:8000` | FastAPI gateway origin                         |
| `VITE_AV_SENTRY_DSN`    | _(unset)_               | optional Sentry browser DSN                    |
| `VITE_AV_APP_ENV`       | `development`           | `development \| staging \| production \| test` |
| `VITE_AV_BUILD_VERSION` | `0.0.0-dev`             | release tag for Sentry                         |

## Project layout

```
src/
  main.tsx              # bootstrap: Sentry, i18n, QueryClient, RouterProvider
  App.tsx               # ErrorBoundary + <Outlet />
  config/               # env, i18n, sentry, query
  routes/               # data router + per-route components
  state/                # zustand stores (auth, tenancy)
  services/             # fetchAuth wrapper + per-domain clients
  components/           # AppShell, LocaleSwitcher, QrScanner placeholder, a11y/
  hooks/                # useAuth, useTenancy
  theme/                # tokens (mirrored in tailwind.config.ts)
  locales/{en,ar}/      # i18next resources
  __tests__/            # vitest specs
```

## Auth model (skeleton)

- Access token (PASETO v4.public from the backend) lives in memory via `useAuthStore`.
- Refresh token is an httpOnly cookie set by the backend; it is never read from JS.
- `services/api.ts::fetchAuth` attaches `Authorization: Bearer <token>` and `X-Tenant-Scope: <tenant_id>`. On 401 it calls `/auth/refresh` once with `credentials: include`, retries the original request, otherwise clears the auth store.

## Accessibility baseline

- 44×44 px minimum touch target on interactive primitives (`components/a11y/Button.tsx`).
- Visible focus ring via `:focus-visible`.
- Tested locale switch flips `<html dir="rtl">` for Arabic (and back).
- ESLint runs `jsx-a11y/recommended` so missing `alt`, click handlers without keyboard equivalents, and label-less inputs all fail lint.
