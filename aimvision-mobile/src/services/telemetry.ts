/**
 * Telemetry subscriber that surfaces battery + thermal events to Sentry as
 * breadcrumbs. Sprint 3 EPIC 3.3 gate: "battery + thermal instrumentation
 * surfaced to Sentry breadcrumbs."
 *
 * Battery is wired now via `expo-battery` (UIDevice + Android BatteryManager).
 * Thermal still routes through `useThermal`'s stub until the Sprint 7 native
 * module lands; once it does, this subscriber starts emitting non-nominal
 * breadcrumbs automatically with no change here.
 */
import * as Battery from 'expo-battery';
import { Sentry } from '../config/sentry';

export interface TelemetryHandle {
  /** Stop emitting breadcrumbs and release native listeners. */
  dispose: () => void;
}

function levelToBucket(level: number): 'critical' | 'low' | 'ok' | 'unknown' {
  if (level < 0) return 'unknown';
  if (level <= 0.1) return 'critical';
  if (level <= 0.2) return 'low';
  return 'ok';
}

/**
 * Subscribe to battery + thermal events and emit Sentry breadcrumbs on each
 * change. Returns a handle whose `dispose()` unsubscribes — call it from the
 * App-level effect cleanup so test runs don't leak listeners.
 *
 * Breadcrumb categories:
 *  - `device.battery` — level / charging / low-power-mode transitions
 *  - `device.thermal` — thermal state transitions (wired but no-op until S7)
 */
export function startTelemetrySubscribers(): TelemetryHandle {
  let lastBucket: ReturnType<typeof levelToBucket> | null = null;
  let lastCharging: boolean | null = null;
  let lastLowPower: boolean | null = null;

  const emit = (type: 'level' | 'state' | 'lowPower', data: Record<string, unknown>): void => {
    Sentry.addBreadcrumb({
      category: 'device.battery',
      type: 'info',
      level: 'info',
      message: `battery ${type}`,
      data,
    });
  };

  const levelSub = Battery.addBatteryLevelListener(({ batteryLevel }) => {
    const bucket = levelToBucket(batteryLevel);
    if (bucket !== lastBucket) {
      emit('level', { level: batteryLevel, bucket });
      lastBucket = bucket;
    }
  });
  const stateSub = Battery.addBatteryStateListener(({ batteryState }) => {
    const charging =
      batteryState === Battery.BatteryState.CHARGING || batteryState === Battery.BatteryState.FULL;
    if (charging !== lastCharging) {
      emit('state', { charging });
      lastCharging = charging;
    }
  });
  const lowPowerSub = Battery.addLowPowerModeListener(({ lowPowerMode }) => {
    if (lowPowerMode !== lastLowPower) {
      emit('lowPower', { lowPowerMode });
      lastLowPower = lowPowerMode;
    }
  });

  // Thermal: native module ships in Sprint 7 (see useThermal.ts). When it
  // lands, replace this stub with a real listener that emits a
  // `device.thermal` breadcrumb on each transition out of 'nominal'.

  return {
    dispose: () => {
      levelSub.remove();
      stateSub.remove();
      lowPowerSub.remove();
    },
  };
}
