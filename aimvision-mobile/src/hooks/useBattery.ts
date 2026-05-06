import { useEffect, useState } from 'react';

export interface BatteryInfo {
  level: number; // 0..1
  charging: boolean;
  lowPowerMode: boolean;
}

export function useBattery(): BatteryInfo {
  // Native module ships in Sprint 7; setter is exported in the dispose hook
  // once that lands. Keep the state pair so consumers can rely on the API.
  const [info, setInfo] = useState<BatteryInfo>({
    level: 1,
    charging: false,
    lowPowerMode: false,
  });

  useEffect(() => {
    // Native bridge subscribes here in Sprint 7 (uses `setInfo`).
    void setInfo;
    return () => undefined;
  }, []);

  return info;
}
