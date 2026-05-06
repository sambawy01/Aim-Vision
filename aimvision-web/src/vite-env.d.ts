/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AV_API_BASE_URL?: string;
  readonly VITE_AV_SENTRY_DSN?: string;
  readonly VITE_AV_APP_ENV?: 'development' | 'staging' | 'production' | 'test';
  readonly VITE_AV_BUILD_VERSION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
