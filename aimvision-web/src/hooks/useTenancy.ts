import { useTenancyStore } from '@/state/tenancyStore';

export function useTenancy() {
  const current = useTenancyStore((s) => s.current);
  const available = useTenancyStore((s) => s.available);
  const switchTo = useTenancyStore((s) => s.switchTo);
  return { current, available, switchTo };
}
