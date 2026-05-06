import type { ReactNode } from 'react';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center text-center py-16 px-6 border border-dashed border-border rounded-lg bg-surface-muted"
    >
      <h2 className="text-lg font-semibold text-text">{title}</h2>
      {description ? <p className="mt-2 text-text-muted max-w-md">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
