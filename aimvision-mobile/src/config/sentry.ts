/**
 * Sentry init — local-dev stub.
 *
 * `@sentry/react-native@5.x` ships a C++ profiler that fails to compile
 * against Xcode 26's stricter libc++. Until the RN modernization (PR #92)
 * upgrades Sentry to ~7.x (Xcode-26-compatible), this stub no-ops and
 * the surrounding try/catch in `App.tsx` keeps the app booting.
 *
 * Public API (initSentry + a Sentry namespace with the calls we make
 * elsewhere) is preserved so call sites don't change.
 */

export function initSentry(): void {
  // No-op stub.
}

export const Sentry = {
  captureException(_err: unknown): void {
    // No-op.
  },
  captureMessage(_msg: string): void {
    // No-op.
  },
  addBreadcrumb(_b: unknown): void {
    // No-op.
  },
  withScope<T>(fn: (scope: { setExtra: (k: string, v: unknown) => void }) => T): T {
    return fn({ setExtra: () => undefined });
  },
} as const;
