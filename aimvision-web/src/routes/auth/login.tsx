import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/a11y/Button';
import { LocaleSwitcher } from '@/components/LocaleSwitcher';
import { login } from '@/services/auth';

export function LoginRoute() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsPending(true);
    try {
      await login(email, password);
      nav('/app/athletes', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'));
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface text-text">
      <header className="flex justify-end p-4">
        <LocaleSwitcher />
      </header>
      <main className="flex-1 flex items-center justify-center px-4">
        <form
          onSubmit={onSubmit}
          aria-labelledby="login-heading"
          className="w-full max-w-sm space-y-4 bg-surface p-6 rounded-lg border border-border"
        >
          <h1 id="login-heading" className="text-xl font-semibold">
            {t('auth.login.title')}
          </h1>

          <div className="flex flex-col gap-1">
            <label htmlFor="email" className="text-sm font-medium">
              {t('auth.login.email')}
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="min-h-touch px-3 py-2 rounded-md border border-border bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="password" className="text-sm font-medium">
              {t('auth.login.password')}
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="min-h-touch px-3 py-2 rounded-md border border-border bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            />
          </div>

          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          ) : null}

          <Button type="submit" disabled={isPending} className="w-full">
            {isPending ? t('common.loading') : t('auth.login.submit')}
          </Button>
        </form>
      </main>
    </div>
  );
}
