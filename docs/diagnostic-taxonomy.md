# AIMVISION Diagnostic Taxonomy

**Owner:** AI Engineer (vocabulary + signals) · UX Researcher (canonical naming card-sort)
**Date:** 2026-05-06
**Status:** v0.9 DRAFT — **NOT LOCKED**. Vocabulary requires card-sort validation with **20 coaches + 20 athletes across US / UK / Italy / Egypt** before the **Sprint 9 lock**, per `docs/reviews/08-ux-researcher.md` ("Stopped gun, swing arrest, deceleration, checked swing — same diagnostic to four communities. Run terminology card-sorts before locking copy.").
**Sibling specs:** `docs/ml-architecture.md` §8 (the multi-task hierarchical head this taxonomy parametrizes), `docs/llm-coaching-notes-schema.md` (the `category` enum is sourced from this file).

> **Card-sort requirement (do not skip).** Each atom below has a `working_canonical` and `aliases` field. `working_canonical` is a placeholder. Sprint 9 lock-in pins the canonical token after card-sort with the panel above. Localization (Italian, French, Portuguese, Arabic) follows lock — string-only translations per UX review's Sprint 18 expansion. Until lock, the model trains on the working_canonical; after lock, label files are migrated by a one-shot rename script and the registry version is bumped.

---

## Branch structure

The diagnostic head is **multi-task hierarchical and multi-label**. Four branch experts plus a Meta layer:

1. **Head/Eye** — what the head and eyes do.
2. **Mount/Stance** — how the body and gun-to-body assembly is organized.
3. **Swing/Lead** — what the gun does in space relative to the clay.
4. **Follow-through** — what happens after break.
5. **Meta** — confidence, multi-factor, and pattern flags. Not a fault per se; orchestration over the four branches.

Atoms within a branch are not mutually exclusive. Across branches they co-occur regularly (e.g., `head_lift` + `stopped_gun`). Each atom emits an independent calibrated probability with a per-atom abstention threshold (per-class, not global, per `docs/reviews/01-ai-engineer.md` and `docs/ml-architecture.md` §8).

---

## Head/Eye branch

### `head_lift`
- **Working canonical:** `head_lift`
- **Aliases for card-sort:** *peeking*, *looking up*, *coming off the gun*, *eye-up*
- **Definition:** Eye leaves the bead/rib pre-trigger; the head rotates upward or off the stock during the final 100–300 ms before muzzle blast.
- **Observable signals:**
  - Pose (face landmarks): rising vertical angle of nose/chin relative to torso in the 300 ms before shot.
  - Pose (eye landmark, post-session only — Wholebody topology): gaze vector deviates upward from rib line.
  - IMU: not directly visible; head-lift is a body event, not a gun event.
  - Gun-mount video: bead rises in frame relative to stationary chequering reference.
- **Model branch:** Head/Eye expert.
- **Signal source priority:** pose face landmarks (post-session) > gun-mount-video bead-rise (live) > pose nose-to-shoulder angle (live, lower precision).
- **Confidence threshold (default):** 0.55 (lower than other atoms because pose-only signal is noisy live; tightened to 0.65 post-session when face landmarks are available).
- **Abstention rule:** abstain if face landmarks confidence < 0.7 AND IMU did not register a clean tap (cannot anchor the 300 ms window).
- **Coach-mode tone:** "Head came off at break — shot 12, 19, 31. Cheek-weld first."
- **Athlete-mode tone:** "You peeked at three shots. Stay on the gun until the clay breaks."

### `head_off_stock`
- **Working canonical:** `head_off_stock`
- **Aliases:** *cheek not on stock*, *broken cheek-weld*, *floating head*
- **Definition:** Cheek-weld is broken or never established; the head is not in contact with the stock at trigger pull.
- **Observable signals:**
  - Pose Wholebody (post-session): cheek landmark distance from stock landmark > threshold.
  - Gun-mount video (live): visible gap between cheek and stock; this is observable live with a side-mount camera but not a forward-mount one.
- **Model branch:** Head/Eye expert.
- **Confidence threshold:** 0.6 post-session; **abstain in live tier** when only forward-camera is available (the signal isn't visible).
- **Abstention rule:** abstain in live unless side-cam present.
- **Coach-mode tone:** "Cheek-weld breaking before mount completes."
- **Athlete-mode tone:** "Press your cheek to the stock before you swing."

### `eye_dominance_failure`
- **Working canonical:** `eye_dominance_failure`
- **Aliases:** *cross-firing*, *wrong eye*, *eye switch*
- **Definition:** Athlete sights with non-dominant eye; common in cross-dominant shooters under fatigue.
- **Observable signals:**
  - Pose Wholebody face landmarks (post-session only): eye-aim vector inconsistent with stated dominance profile.
  - Per-athlete profile: stored dominant-eye declared at onboarding.
- **Model branch:** Head/Eye expert.
- **Confidence threshold:** 0.7 (high, because mis-flagging this is annoying — most shots are correct).
- **Abstention rule:** **post-session only**; not surfaced in live tier in V1 (signal too noisy on phone-grade pose). V1.5 with phone front-cam gaze upgrades this to live.
- **Coach-mode tone:** "Cross-dominance creeping back on station 4."
- **Athlete-mode tone:** "Check your dominant-eye discipline; you switched on a few shots."

---

## Mount/Stance branch

### `low_mount_break`
- **Working canonical:** `low_mount_break`
- **Aliases:** *shooting from low mount*, *gun not up*, *incomplete mount at break*
- **Definition:** Gun mount is incomplete (stock not fully into shoulder pocket, cheek not on stock) at the moment the shot breaks. Distinct from `head_off_stock` — this is about the whole gun, not just the head.
- **Observable signals:**
  - Pose: shoulder-to-stock distance still decreasing at trigger time.
  - IMU: mount jerk profile not yet completed (mount jerk peak normally 200–400 ms before shot; if peak is < 100 ms before shot, mount is late).
  - Gun-mount video: stock visible above shoulder pocket at break frame.
- **Model branch:** Mount/Stance expert.
- **Confidence threshold:** 0.6 — **IMU mount jerk timing is the cleanest single signal** (see `docs/ml-architecture.md` §9). With IMU, threshold tightens to 0.7.
- **Abstention rule:** abstain if neither IMU jerk trace nor pose mount-trajectory has confidence > 0.6.
- **Coach-mode tone:** "Mount finishing at the shot — gun's still moving up. Shot 7, 22, 38."
- **Athlete-mode tone:** "Get the gun up earlier. Mount before you call."

### `foot_position`
- **Working canonical:** `foot_position`
- **Aliases:** *stance*, *feet wrong*, *crossover*, *closed/open stance*
- **Definition:** Foot placement inappropriate for station — typically too closed (limits swing past 90°) or too open (compromises stability).
- **Observable signals:**
  - Pose (full-body, both live and post-session): foot landmarks relative to torso direction and station orientation.
  - Per-station expected stance template, derived from a reference dataset of professional shooters at each skeet/trap station.
- **Model branch:** Mount/Stance expert.
- **Confidence threshold:** 0.65.
- **Abstention rule:** abstain on station 8 (high-house and low-house from center; stance is shooter preference, not standardized) and on sporting-clays presentations where the stance template doesn't apply.
- **Coach-mode tone:** "Stance is closing too early on stations 5 and 6."
- **Athlete-mode tone:** "Open your front foot a touch on the high stations."

### `body_alignment_off`
- **Working canonical:** `body_alignment_off`
- **Aliases:** *poor address*, *wrong gun-up direction*, *over-rotated address*
- **Definition:** Initial body alignment (hip and shoulder line) does not bisect the expected break point; athlete will run out of swing before reaching the bird.
- **Observable signals:**
  - Pose hip-line and shoulder-line vectors at gun-up time.
  - Station + discipline → expected break-point bearing.
- **Model branch:** Mount/Stance expert.
- **Confidence threshold:** 0.6.
- **Abstention rule:** abstain if station ID is unknown (sporting clays without station tagging) or if discipline is `unknown`.
- **Coach-mode tone:** "Address bearing 12° short of break point on stations 1 and 7."
- **Athlete-mode tone:** "Set up so you finish where the bird breaks, not where you call."

---

## Swing/Lead branch

### `stopped_gun` *(canonical TBD — see card-sort)*
- **Working canonical:** `stopped_gun`
- **Aliases:** *swing arrest*, *deceleration*, *checked swing*, *gun stopped*, *measuring*, *aiming the swing*
- **Card-sort note:** Highest-priority disambiguation in the Sprint 9 panel. UX review explicitly calls this one out: "four communities use four words for the same diagnostic." We will pick the canonical that scores highest cross-cohort recognition — likely `stopped_gun` (US/UK) or `swing_arrest` (technical/coaching literature).
- **Definition:** Swing angular velocity drops below a threshold within the final 100 ms before shot; gun is decelerating or stationary at break.
- **Observable signals:**
  - **IMU gyro-Z (primary, ground-truth).** Angular velocity of the gun directly. This is the single-best signal in the entire taxonomy and the reason IMU is V1 P1.
  - Pose-derived barrel angular velocity (live fallback, ~3–5× noisier than IMU).
  - Barrel YOLO + tracker derivative (post-session fallback).
- **Model branch:** Swing/Lead expert.
- **Confidence threshold:** 0.55 with IMU; 0.7 without IMU (signal is unreliable from pose alone — that's the head-lift/stopped-gun confusability the AI review names).
- **Abstention rule:** abstain if neither IMU nor barrel tracker has high-confidence trace through the 100 ms pre-shot window.
- **Coach-mode tone:** "Gun's stopping at break — shots 14, 21, 33. Through the bird, not at it."
- **Athlete-mode tone:** "Keep swinging through the clay. Don't aim — swing."

### `under_lead`
- **Working canonical:** `under_lead`
- **Aliases:** *behind the bird*, *short lead*, *trailing*
- **Definition:** Barrel is behind the clay's leading edge at trigger time, by more than the discipline-appropriate lead margin.
- **Observable signals:**
  - Barrel tracker + clay tracker; pixel-space lead distance.
  - **Federation tier (3D):** real lead distance via triangulation (`docs/ml-architecture.md` §6).
- **Model branch:** Swing/Lead expert.
- **Confidence threshold:** 0.6 in 2D (pixel-space, biased by camera angle); 0.75 in 3D.
- **Abstention rule:** abstain if camera angle to clay path is < 30° (the foreshortening kills lead estimation).
- **Coach-mode tone:** "Behind on crossers from station 4. Build more lead."
- **Athlete-mode tone:** "More lead on the crossers."

### `over_lead`
- **Working canonical:** `over_lead`
- **Aliases:** *too much lead*, *swinging too fast*, *leading the bird off*
- **Definition:** Barrel is ahead of the clay by more than the discipline-appropriate margin.
- **Observable signals:** mirrored from `under_lead`.
- **Model branch:** Swing/Lead expert.
- **Confidence threshold:** 0.6 in 2D; 0.75 in 3D.
- **Abstention rule:** same camera-angle constraint as `under_lead`.
- **Coach-mode tone:** "Pushing past the clay on outgoers. Slow the swing."
- **Athlete-mode tone:** "Less lead on the outgoers."

### `off_line`
- **Working canonical:** `off_line`
- **Aliases:** *off the line*, *high/low*, *under/over the bird*, *not on plane*
- **Definition:** Barrel is on a different line than the clay's trajectory — typically high or low rather than ahead or behind.
- **Observable signals:**
  - Barrel + clay trackers, perpendicular distance to clay path.
  - 3D swing-plane geometry (federation tier).
- **Model branch:** Swing/Lead expert.
- **Confidence threshold:** 0.6.
- **Abstention rule:** none beyond clay-track-confidence floor.
- **Coach-mode tone:** "Shooting under the high-house bird at 1."
- **Athlete-mode tone:** "Get on the line of the bird, not under it."

---

## Follow-through branch

### `short_follow_through`
- **Working canonical:** `short_follow_through`
- **Aliases:** *no follow-through*, *short swing*, *cut-off*
- **Definition:** Gun stops or decelerates significantly within 200 ms after shot. Different from `stopped_gun`: this is post-shot.
- **Observable signals:**
  - **IMU gyro-Z post-shot trace** (primary). Gun velocity should sustain through follow-through, then decay smoothly.
  - Barrel tracker post-shot velocity (fallback).
- **Model branch:** Follow-through expert.
- **Confidence threshold:** 0.6 with IMU.
- **Abstention rule:** abstain if shot is the last in the string (athlete may legitimately decelerate; not a fault).
- **Coach-mode tone:** "Swing's dying right at the shot."
- **Athlete-mode tone:** "Keep swinging after the shot."

### `dropped_gun_post_shot`
- **Working canonical:** `dropped_gun_post_shot`
- **Aliases:** *dropping the gun*, *coming off the gun early*, *unmounting*
- **Definition:** Gun comes out of the shoulder pocket within 500 ms after shot. Indicates the athlete is mentally finishing before the gun does.
- **Observable signals:**
  - IMU accel-X reversal post-shot.
  - Pose: shoulder-to-stock distance increasing.
- **Model branch:** Follow-through expert.
- **Confidence threshold:** 0.65.
- **Abstention rule:** abstain on doubles when the second shot is within 500 ms (the "drop" is intentional re-mount).
- **Coach-mode tone:** "Gun's coming out of the pocket at the shot."
- **Athlete-mode tone:** "Stay in the gun a beat longer."

---

## Meta layer

### `cause_unclear`
- **Working canonical:** `cause_unclear`
- **Aliases:** *low confidence*, *we don't know*, *not enough signal*
- **Definition:** All branch expert maximum probabilities are below their abstention thresholds; no single fault attribution is defensible.
- **Observable signals:** N/A (it's a confidence state, not an observable).
- **Model branch:** Meta.
- **Surfacing rule (UX-critical):** **`cause_unclear` rate ≤ 15% of shots over a session** (per `docs/reviews/08-ux-researcher.md` cause-unclear budget). If session rate exceeds 15%, the UI substitutes the highest-probability low-confidence guess presented as **"likely: <atom> (low confidence)"** with a dimmed treatment, rather than the empty `cause_unclear` label. The model still records `cause_unclear=true` in the database; the UI rewrites the presentation.
- **Coach-mode tone:** "Couldn't tell on shots 5, 17, 28 — review video together."
- **Athlete-mode tone:** "We're not sure on a few shots; check the replay."

### `multi_factor`
- **Working canonical:** `multi_factor`
- **Aliases:** *multiple causes*, *compound fault*
- **Definition:** Two or more branch experts each report an above-threshold atom for the same shot.
- **Observable signals:** orchestration over branches.
- **Model branch:** Meta.
- **Surfacing rule:** ranked by causal prior (DAG: stance → mount → swing → break → outcome). Earlier-in-chain faults are surfaced as the *primary* cause; later faults as secondary. E.g., `body_alignment_off` + `stopped_gun` → primary is alignment; "you're stopping the gun because you ran out of swing."
- **Coach-mode tone:** "Three things on shot 12: address, then mount, then stopped gun. Address fixes the chain."
- **Athlete-mode tone:** "Fix your set-up first; the rest will follow."

### `in_session_pattern_flag`
- **Working canonical:** `in_session_pattern_flag`
- **Aliases:** *pattern detected*, *streak*, *trend*
- **Definition:** Three-or-more consecutive shots with the same primary atom, OR station performance dropping > 20% from the athlete's baseline.
- **Observable signals:** rolling-window over predictions.
- **Model branch:** Meta.
- **Surfacing rule (UX-critical):** **the live feed only "speaks" on patterns, not on every shot** (UX review: "Notify on patterns, not shots"). Default mode shows a quiet shot counter; pattern flags trigger the audible/haptic notification. Per-shot detail remains on-demand via tap.
- **Coach-mode tone:** "Three head-lifts in a row on station 4."
- **Athlete-mode tone:** "Pattern: head coming up on station 4."

---

## Cross-cutting requirements

**Localization.** After Sprint 9 lock, every atom's canonical token gets translations in: en-US, en-GB, it-IT, fr-FR, es-ES, pt-BR, ar-EG. Coach-mode and athlete-mode tones are translated with native-speaker coach review per locale, not machine-translated.

**Accessibility.** Per UX review: every diagnostic surfaced via audio also surfaces via synced visual + haptic (hearing-aid-friendly). Color-blind-safe palette: hit/miss indicator uses shape + position + color, not color alone.

**Override surface.** Coach taps a diagnostic → "wrong cause / right call / cause was X". Captured as labeled training data. UX review: "Override = signal, not failure." Show coaches the loop: "your override moved this model from 0.74 to 0.78 macro-F1."

**Versioning.** This file is `taxonomy_version`. Every prediction stored with `(taxonomy_version, model_version)`. Migrations on lock are scripted, idempotent, and tested.

**Open issues for Sprint 9 lock-in.**
- Canonical for `stopped_gun` vs `swing_arrest` (highest-priority card-sort question).
- Whether `eye_dominance_failure` ships in V1 athlete-mode or stays coach-mode-only until V1.5 gaze.
- Whether `multi_factor` is a label or only a presentation rule.
- Italian and Egyptian Arabic shooting vocabulary panels confirmed (recruitment open, Sprint 7).
