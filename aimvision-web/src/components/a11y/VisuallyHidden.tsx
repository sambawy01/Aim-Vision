import type { ReactNode } from 'react';

interface VisuallyHiddenProps {
  children: ReactNode;
  as?: 'span' | 'div';
}

/**
 * Hides content visually but keeps it available to assistive tech.
 * Pattern from https://www.tpgi.com/the-anatomy-of-visually-hidden/.
 */
export function VisuallyHidden({ children, as = 'span' }: VisuallyHiddenProps) {
  const Tag = as;
  return (
    <Tag
      style={{
        position: 'absolute',
        width: 1,
        height: 1,
        padding: 0,
        margin: -1,
        overflow: 'hidden',
        clip: 'rect(0, 0, 0, 0)',
        whiteSpace: 'nowrap',
        border: 0,
      }}
    >
      {children}
    </Tag>
  );
}
