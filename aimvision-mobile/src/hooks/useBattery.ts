import { useEffect, useState } from 'react';

export interface BatteryInfo {
  level: number; // 0..1
  charging: boolean;
  lowPowerMode: boolean;
}

export function useBattery(): BatteryInfo {
  const [info, setInfo] = useState<BatteryInfo>({
    level: 1,
    charging: false,
    lowPowerMode: false,
  });

  useEffect(() => {
    // Native module ships in Sprint 7 with the thermal stream.
    return () => undefined;
  }, []);

  return info;
}
