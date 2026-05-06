import { Link } from 'react-router-dom';
import type { Athlete } from '@/services/athletes';

interface AthleteListItemProps {
  athlete: Athlete;
}

export function AthleteListItem({ athlete }: AthleteListItemProps) {
  return (
    <li className="border-b border-border last:border-b-0">
      <Link
        to={`/app/athletes/${athlete.id}`}
        className="flex items-center justify-between px-4 py-3 hover:bg-surface-muted focus-visible:bg-surface-muted"
      >
        <span className="font-medium text-text">{athlete.displayName}</span>
        <span className="text-sm text-text-muted">{athlete.email ?? '—'}</span>
      </Link>
    </li>
  );
}
