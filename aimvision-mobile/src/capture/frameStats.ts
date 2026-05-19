/**
 * Frame-stats helpers — ADR-0009 slice 3a (real-time RN frame processor).
 *
 * Pure-TS, no imports from Vision Camera / worklets-core / Reanimated, so
 * the math is unit-testable without any native modules mocked.
 *
 * The `useFrameStats` hook (in `useFrameStats.ts`) wraps these helpers in
 * a worklet-shared-value boundary and a setInterval poll that fans the
 * worklet thread state out to a JS-thread render-friendly object.
 */

/** What the screen reads about the live frame pipeline. */
export interface FrameStats {
  /** Total frames received since the camera became active. */
  frameCount: number;
  /** Estimated frames per second over the most recent window
   * (`FrameStats.fps == 0` until the second frame arrives — a single
   * sample is not a rate). */
  fps: number;
  /** Last frame's reported width × height in pixels, or null before any
   * frame arrives. */
  resolution: { width: number; height: number } | null;
  /** Vision Camera's `frame.pixelFormat` (e.g. `'yuv'`, `'rgb'`) on the
   * most recent frame, or null. */
  pixelFormat: string | null;
  /** Wall-clock ms at which the last frame was observed. Useful for
   * detecting a stalled pipeline ("haven't seen a frame in N seconds"). */
  lastFrameWallMs: number | null;
}

export const EMPTY_FRAME_STATS: FrameStats = {
  frameCount: 0,
  fps: 0,
  resolution: null,
  pixelFormat: null,
  lastFrameWallMs: null,
};

/** Rolling-window FPS estimator from a delta between two cumulative
 * frame counts and the wall-clock time elapsed between the samples.
 *
 * Returns 0 if either input is non-positive — a one-sample window can't
 * estimate a rate, and Vision Camera occasionally drops a frame timestamp
 * to 0 during init (callers shouldn't get a divide-by-zero NaN flowing
 * into the UI).
 */
export function estimateFps(framesDelta: number, elapsedMs: number): number {
  if (framesDelta <= 0 || elapsedMs <= 0) return 0;
  return (framesDelta * 1000) / elapsedMs;
}

/** Format an FPS value for the status banner. Pads to one decimal so the
 * label width doesn't jump on every refresh. Returns `'—'` for non-finite
 * values (defensive against any divide-by-zero leaking past `estimateFps`). */
export function formatFps(fps: number): string {
  if (!Number.isFinite(fps) || fps < 0) return '—';
  return fps.toFixed(1);
}

/** Format the resolution as "1920×1080" or "—" when unknown. */
export function formatResolution(r: FrameStats['resolution']): string {
  if (!r) return '—';
  return `${r.width}×${r.height}`;
}

/** True if no frame has arrived recently — heuristic the screen uses to
 * surface a "pipeline stalled" banner. Caller decides the threshold;
 * a typical value is 1500 ms at 30 fps (≈ 45 frames missed). */
export function isPipelineStalled(stats: FrameStats, nowMs: number, thresholdMs: number): boolean {
  if (stats.lastFrameWallMs === null) return false;
  return nowMs - stats.lastFrameWallMs > thresholdMs;
}
