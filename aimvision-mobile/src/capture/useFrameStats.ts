import { useEffect, useRef, useState } from 'react';
import { useSharedValue, type ISharedValue } from 'react-native-worklets-core';
import { EMPTY_FRAME_STATS, estimateFps, type FrameStats } from './frameStats';

/**
 * React-side adapter around the Vision Camera worklet shared values.
 *
 * The frame processor runs on the camera worklet thread. To get its state
 * to React for rendering we use `useSharedValue` from worklets-core (which
 * bridges threads) plus a `setInterval` poll that snapshots into JS state
 * every `pollMs` (default 500 ms — fast enough for a visible counter,
 * slow enough that we don't re-render the tree on every frame).
 *
 * Caller pattern (in `CapturePhoneScreen`):
 *
 *   const { stats, sharedValues } = useFrameStats();
 *   const fp = useFrameProcessor((frame) => {
 *     'worklet';
 *     sharedValues.frameCount.value = sharedValues.frameCount.value + 1;
 *     sharedValues.lastTimestampNs.value = frame.timestamp;
 *     sharedValues.lastWidth.value = frame.width;
 *     sharedValues.lastHeight.value = frame.height;
 *     sharedValues.lastPixelFormat.value = frame.pixelFormat;
 *   }, [sharedValues]);
 *
 * `stats` is what the screen reads; the worklet writes through
 * `sharedValues`. Polling in one direction keeps the worklet thread
 * lock-free and the render thread quiet.
 */

export interface FrameSharedValues {
  frameCount: ISharedValue<number>;
  lastTimestampNs: ISharedValue<number>;
  lastWidth: ISharedValue<number>;
  lastHeight: ISharedValue<number>;
  /** Vision Camera reports `pixelFormat` as a string union; we widen it
   * to `string` for storage so the worklet doesn't carry the type
   * dependency. */
  lastPixelFormat: ISharedValue<string>;
  /** Where the most recent frame metadata came from. The worklet writes
   * `"native-ios"` / `"native-android"` (slice 3b native plugin) or
   * `"js-worklet"` (slice 3a fallback). Empty string = no frame yet. */
  lastSourceTag: ISharedValue<string>;
}

export interface UseFrameStatsResult {
  stats: FrameStats;
  sharedValues: FrameSharedValues;
}

export function useFrameStats(pollMs = 500): UseFrameStatsResult {
  const frameCount = useSharedValue(0);
  const lastTimestampNs = useSharedValue(0);
  const lastWidth = useSharedValue(0);
  const lastHeight = useSharedValue(0);
  const lastPixelFormat = useSharedValue('');
  const lastSourceTag = useSharedValue('');

  const [stats, setStats] = useState<FrameStats>(EMPTY_FRAME_STATS);
  // Track the previous sample so we can compute fps over the poll window.
  const prevCountRef = useRef<number>(0);
  const prevSampleWallMsRef = useRef<number>(Date.now());

  useEffect(() => {
    const id = setInterval(() => {
      const nowMs = Date.now();
      const count = frameCount.value;
      const elapsed = nowMs - prevSampleWallMsRef.current;
      const delta = count - prevCountRef.current;
      const fps = estimateFps(delta, elapsed);

      const width = lastWidth.value;
      const height = lastHeight.value;
      const format = lastPixelFormat.value;
      const source = lastSourceTag.value;

      setStats({
        frameCount: count,
        fps,
        resolution: width > 0 && height > 0 ? { width, height } : null,
        pixelFormat: format !== '' ? format : null,
        lastFrameWallMs: count > 0 ? nowMs : null,
        sourceTag: source !== '' ? source : null,
      });

      prevCountRef.current = count;
      prevSampleWallMsRef.current = nowMs;
    }, pollMs);
    return () => clearInterval(id);
  }, [pollMs, frameCount, lastWidth, lastHeight, lastPixelFormat, lastSourceTag]);

  return {
    stats,
    sharedValues: {
      frameCount,
      lastTimestampNs,
      lastWidth,
      lastHeight,
      lastPixelFormat,
      lastSourceTag,
    },
  };
}
