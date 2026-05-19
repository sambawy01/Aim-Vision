/**
 * Frame-stats helper unit tests — ADR-0009 slice 3a.
 *
 * Pure-TS, no Vision Camera, no worklets-core. The `useFrameStats` hook
 * (which DOES depend on those) isn't unit-tested directly; the math
 * it relies on lives here.
 */
import {
  EMPTY_FRAME_STATS,
  estimateFps,
  formatFps,
  formatResolution,
  isPipelineStalled,
} from '../capture/frameStats';

describe('estimateFps', () => {
  it('returns frames-per-second over the sample window', () => {
    // 30 frames in 1000 ms = 30 fps exactly.
    expect(estimateFps(30, 1000)).toBe(30);
    // 60 frames in 500 ms = 120 fps.
    expect(estimateFps(60, 500)).toBe(120);
  });

  it('returns 0 for a one-sample window (defensive against jest fake timers)', () => {
    expect(estimateFps(0, 1000)).toBe(0);
    expect(estimateFps(-1, 1000)).toBe(0);
  });

  it('returns 0 for non-positive elapsed time (avoids divide-by-zero on first frame)', () => {
    expect(estimateFps(30, 0)).toBe(0);
    expect(estimateFps(30, -5)).toBe(0);
  });
});

describe('formatFps', () => {
  it('pads to one decimal so the label width is stable', () => {
    expect(formatFps(30)).toBe('30.0');
    expect(formatFps(29.345)).toBe('29.3');
    expect(formatFps(0)).toBe('0.0');
  });

  it('renders an em dash for non-finite or negative', () => {
    expect(formatFps(Number.NaN)).toBe('—');
    expect(formatFps(Number.POSITIVE_INFINITY)).toBe('—');
    expect(formatFps(-1)).toBe('—');
  });
});

describe('formatResolution', () => {
  it('renders "W×H" when present', () => {
    expect(formatResolution({ width: 1920, height: 1080 })).toBe('1920×1080');
  });

  it('renders an em dash when null', () => {
    expect(formatResolution(null)).toBe('—');
  });
});

describe('isPipelineStalled', () => {
  it('is false until the first frame is observed (no baseline to stall from)', () => {
    expect(isPipelineStalled(EMPTY_FRAME_STATS, 999_999, 100)).toBe(false);
  });

  it('is true once the gap exceeds the threshold', () => {
    const stats = { ...EMPTY_FRAME_STATS, lastFrameWallMs: 1_000, frameCount: 1 };
    expect(isPipelineStalled(stats, 1_500, 250)).toBe(true);
    expect(isPipelineStalled(stats, 1_500, 1_000)).toBe(false);
  });
});
