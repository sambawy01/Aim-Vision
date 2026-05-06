import { useEffect, useState } from 'react';
import { Statsig, isInitialized } from '../config/statsig';

export function useFlag(name: string, defaultValue = false): boolean {
  const [value, setValue] = useState<boolean>(defaultValue);

  useEffect(() => {
    if (!isInitialized()) return;
    try {
      setValue(Statsig.checkGate(name));
    } catch {
      setValue(defaultValue);
    }
  }, [name, defaultValue]);

  return value;
}
