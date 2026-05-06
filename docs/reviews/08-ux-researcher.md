# AIMVISION UX Critique

**Reviewer:** UX Researcher · **Date:** 2026-05-06 · **Source:** `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0

## Top 5 User-Journey Gaps

**1. First-session-ever (Solo).** The plan splits unboxing across Sprints 12 and 22 but never rehearses the chained journey: Hero 13 unboxing → SD card formatting → BLE pairing on a phone with 14 other Bluetooth devices nearby → Wi-Fi handoff (the documented Open GoPro pain point) → calibration marker placement on a real range with no flat surface → first recording with sun on the screen. Realistic clay-shooter behavior: they'll arrive 20 minutes before a squad, fight pairing in a parking lot, and abandon if it takes more than two attempts. The plan needs an explicit "T-minus 20 minutes to first shot" target and a single Sprint 12 deliverable that runs the whole chain with a real elderly recreational shooter.

**2. Coach running 6 back-to-back 30-min sessions.** Sprint 13 mentions "athlete switching" without a target. In real club operations on Saturday morning, a coach has 4-8 athletes on overlapping 30-minute slots, often arriving late, often with one dropping in unannounced. The app needs <10s switch time, a persistent "next up" queue, and crucially a "running late / extend by 10 min" gesture. Coaches abandon to paper when annotation requires more than two taps per shot.

**3. Bus-ride report review.** A 100-shot report has 7+ sections. On a phone with one hand, holding a rifle case, the layout in Sprint 11 (tab navigation between sections) buries the headline. Default mobile view should be a vertical "story" — headline + top 3 patterns + 1 notable shot — with "see full report" disclosure. Slow-motion playback over a tethered 4G connection during commute is a known killer; pre-cache the notable-shots playlist on session-end.

**4. "I forgot to pause."** Not addressed. Athletes set the camera, take a coaching break, then return. The post-session pipeline must auto-detect dead time (no shots for >5 min, idle pose) and offer "Trim 14:32 of inactivity?" before generating the report. Without this, half of solo reports will be polluted.

**5. "GoPro died at shot 47."** Sprint 10 has reconnection but not a graceful narrative. Athletes need an explicit "Session continued without video, audio shots still captured (47 of ~100 with full diagnostics, 53 audio-only)" — not a broken report. Also: low-battery warning at 20% with audible alert, because the phone is in a pocket.

## Coach Workflow Recommendations

1. **Build for sun, gloves, and shouting.** iPad in direct Egyptian sun at 12pm is unreadable below 1000 nits. Mandate a high-contrast "Range Mode" with 24pt minimum, reduced color palette, and large two-finger gestures. Test with thin nitrile gloves (coaches handle gun parts). Add a tablet sleeve recommendation in onboarding.
2. **Voice-first annotation during live; stylus after.** Coaches won't type while an athlete is on the line. Push-to-talk voice notes attached to the most recent shot is the live primitive. Stylus and typed annotation belong in the post-session review screen, not the live feed.
3. **Athlete switch target: 8 seconds, 3 taps.** Add a "Queue" panel persistently visible. QR check-in should auto-add to the queue. "End and start next" should be a single labeled action, not two.
4. **Override = signal, not failure.** When a coach overrides a model diagnostic, capture it as labeled training data with one-tap "wrong cause / right call / cause was X." Show coaches that their overrides improve the model — visible loop builds trust.

## Athlete UX Recommendations

1. **Default to "Do Not Distract."** The live feed should be visually hidden during the 3-second pre-shot window detected by pose (gun mount). Animations only resolve in the gap between shots. Vibration over visual when athlete is in stance.
2. **Older-shooter defaults.** Clay/skeet skews 50+. Default font 18pt, primary touch targets 56pt minimum, no hover states, no swipe-only actions. Test with 65-year-old recreational shooters in Sprint 12.
3. **Outdoor display profile.** Auto-trigger high-brightness, anti-glare palette when ambient light sensor reads >50,000 lux. Avoid pure white backgrounds in outdoor surfaces — use #F5F0E8 or similar.
4. **Add French, Italian, Portuguese to the Sprint 18 plan.** Italy alone has ~5x the Olympic clay medals of Spain. French covers North Africa beyond Egypt and Belgium/Switzerland. Portuguese covers Brazil's strong clay community. Even string-only translations (no RTL work needed) double addressable users.

## Live-Feed Information Design

1. **Notify on patterns, not shots.** Default mode shows a quiet shot counter; the feed only "speaks" when 3+ same-diagnostic appears or station performance drops 20%. Per-shot detail is on-demand via tap.
2. **"Cause unclear" budget.** If >15% of shots show "cause unclear," the feed reads as broken. Model owners should treat 15% as a hard ceiling and force "low-confidence + best guess + dimmed treatment" instead of the honest-but-empty alternative.
3. **Validate vocabulary.** "Stopped gun," "swing arrest," "deceleration," "checked swing" are the same diagnostic to four communities. Run terminology card-sorts with 20 coaches and 20 athletes across US/UK/Italy/Egypt before locking copy in Sprint 9.

## Accessibility for Shooting-Sport Demographics

1. **Hearing-aid-friendly.** Audio diagnostics must have a synced visual+haptic equivalent; never audio-only. Many older shooters wear electronic ear-pro that compresses voice frequencies.
2. **One-handed pose baseline.** Pose model needs a calibration mode for paralympic/wrist-injured shooters. Solution: per-athlete "stance template" captured in onboarding, used as that athlete's mechanical baseline.
3. **Color-blind diagnostics.** ~8% of male shooters are red-green deficient. Hit/miss must use shape and position too, not red/green.
4. **Voice control for hands-busy.** "Hey AIM, mark shot" / "pause session" / "next athlete" — built on the existing voice-note primitive.
5. **Sun-readable mode + reduced motion.** Sub-setting under "Range Mode" with no animations, no parallax, max contrast.

## Research-Method Additions

1. **Diary studies from Sprint 5.** Recruit 8 Egypt athletes and 4 international recreational shooters for a 4-week shot-of-the-day diary (voice memo + photo). Surfaces real coaching language and pain ahead of the diagnostic taxonomy lock.
2. **Wizard-of-Oz coaching notes in Sprint 9.** Before building the LLM pipeline, have Franco hand-write coaching notes from 30 sample sessions in three formats. A/B test which format athletes act on. Saves an entire sprint of LLM prompt engineering aimed at the wrong target.
3. **First-time-use studies in Sprints 12-14, not 19.** Recruit 10 net-new Solo users, ship them an unboxing kit, observe remotely. Catch the calibration-failure and pairing-abandonment cliffs before Egypt validation, which is too late to redesign onboarding.
