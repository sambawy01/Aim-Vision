import { forwardRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-brand-accent text-brand-fg hover:opacity-90',
  secondary: 'bg-surface-muted text-text border border-border hover:border-border-strong',
  ghost: 'bg-transparent text-text hover:bg-surface-muted',
  danger: 'bg-danger text-brand-fg hover:opacity-90',
};

/**
 * Accessible button primitive.
 * - Minimum 44x44 touch target (WCAG 2.5.5).
 * - Visible focus ring driven by `:focus-visible`.
 * - Forwards `aria-*` attributes (aria-label, aria-pressed, aria-expanded, etc.).
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', className = '', type = 'button', children, ...rest },
  ref,
) {
  const base =
    'inline-flex items-center justify-center min-h-touch min-w-touch px-4 py-2 ' +
    'rounded-md font-medium transition-colors ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 ' +
    'disabled:opacity-50 disabled:cursor-not-allowed';
  return (
    <button
      ref={ref}
      type={type}
      className={`${base} ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
});
