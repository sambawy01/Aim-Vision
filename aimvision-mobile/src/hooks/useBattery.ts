/**
 * Battery state hook backed by `expo-battery` (which wraps UIDevice.batteryLevel
 * on iOS and Android BatteryManager). Returns the most recent snapshot and
 * subscribes for level + state + low-power-mode change events.
 *
 * Sprint 3 EPIC 3.3: battery surfaced to Sentry breadcrumbs — see
 * `src/services/telemetry.ts` for the subscriber that emits those.
 */
import { useEffect, useState } from 'react';
import * as Battery from 'expo-battery';

export interface BatteryInfo {
  /** Battery level in [0, 1]. 1 means full. -1 if unknown (e.g. simulator). */
  level: number;
  /** True while a charger is connected or the device is full. */
  charging: boolean;
  /** True when the OS-level low-power / battery-saver mode is on. */
  lowPowerMode: boolean;
}

function batteryStateIsCharging(state: Battery.BatteryState): boolean {
  return state === Battery.BatteryState.CHARGING || state === Battery.BatteryState.FULL;
}

export function useBattery(): BatteryInfo {
  const [info, setInfo] = useState<BatteryInfo>({
    level: -1,
    charging: false,
    lowPowerMode: false,
  });

  useEffect(() => {
    let mounted = true;

    (async () => {
      const [level, state, lowPower] = await Promise.all([
        Battery.getBatteryLevelAsync(),
        Battery.getBatteryStateAsync(),
        Battery.isLowPowerModeEnabledAsync(),
      ]);
      if (!mounted) return;
      setInfo({
        level,
        charging: batteryStateIsCharging(state),
        lowPowerMode: lowPower,
      });
    })();

    const levelSub = Battery.addBatteryLevelListener(({ batteryLevel }) => {
      setInfo((prev) => ({ ...prev, level: batteryLevel }));
    });
    const stateSub = Battery.addBatteryStateListener(({ batteryState }) => {
      setInfo((prev) => ({ ...prev, charging: batteryStateIsCharging(batteryState) }));
    });
    const lowPowerSub = Battery.addLowPowerModeListener(({ lowPowerMode }) => {
      setInfo((prev) => ({ ...prev, lowPowerMode }));
    });

    return () => {
      mounted = false;
      levelSub.remove();
      stateSub.remove();
      lowPowerSub.remove();
    };
  }, []);

  return info;
}
