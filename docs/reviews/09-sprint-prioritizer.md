# AIMVISION Sprint Plan Critique

**Reviewer:** Sprint Prioritizer · **Date:** 2026-05-06 · **Source:** `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0

The plan is thoughtful but suffers from a classic founder pattern: building the simpler tier first while the design partner needs the harder one, and pushing validation, internationalization, and risk-mitigation rituals to the back of the timeline where they cost the most to fix.

## Top 5 sequencing changes

1. **Pull Egypt continuous-feedback loop forward to Sprint 5.** Sprint 19 is wrong by ~14 sprints. The moment a real session is captured (Sprint 5), establish a weekly feedback rhythm with athletes and coaches — diary studies, structured interviews, "what would you do differently" sessions. Validation is not a phase; it's a heartbeat.
2. **Build coach + federation flows first; derive Solo from simplification.** The design partner is a federation. Building Solo (Sprints 7-12) and bolting on Club at Sprint 13 means every data model, role, permissions, and session-attribution decision is retrofitted. Invert: federation/coach as first-class from Sprint 7, with Solo as a constrained subset. This also fixes the QR check-in scramble at Sprint 16.
3. **RTL and i18n architecture from Sprint 3, not Sprint 18.** Arabic for the design partner means RTL must inform the layout primitives, navigation, and component library *before* any screen is shipped. Move "i18n framework + RTL-safe component library" into Sprint 3 EPIC 3.3. Translations can wait; layout decisions cannot.
4. **Wizard-of-Oz the LLM coaching notes in Sprint 6-7.** Sprint 11 is too late to discover the notes are mediocre. Hand-write coaching notes for 20 real Egypt sessions, A/B test them with athletes against placebo notes, then build the pipeline only if value is confirmed.
5. **Move App Store engagement to Sprint 6.** R3 (firearms-content rejection) is existential. File a TestFlight build with firearm context messaging and request an exploratory call with Apple's app review team in Sprint 6. Discovering policy issues at Sprint 22 is unrecoverable.

## Scope to cut for V1 (5)

1. **On-premises federation deployment validation (17.5)** — V1.5. One design partner does not justify a parallel deployment topology.
2. **Multi-camera sync (17.1, 4.1)** — Ship single-camera V1; add secondary camera in V1.5 once the primary capture pipeline is proven in production.
3. **Spanish localization** — Cut entirely from V1. English + Arabic only. Spanish adds QA surface for zero design-partner value.
4. **Whoop / Oura / sport-science integration stubs (17.3)** — V1.5. Stubs are technical debt that imply a roadmap commitment.
5. **30-drill library minimum (15.1)** — Start with 10 high-quality drills authored by Franco. Library breadth is a vanity metric until retention data tells you what's actually used.

## Scope to add to V1 (5)

1. **Crash/error reporting (Sentry) and feature flags from Sprint 3.** Currently buried in Sprint 22. You cannot debug Egypt validation without telemetry.
2. **Privacy Nutrition Label data flow audit at Sprint 6** (concurrent with first real data capture), not Sprint 22.
3. **DPIA before Sprint 5 Egypt session.** Capturing minor athletes' biometric video without a Data Protection Impact Assessment is a legal landmine — especially for an EU-incorporated entity working with a federation.
4. **Continuous internal alpha from Sprint 5.** Team dogfooding is implied at Sprint 12; make it a hard rule that every engineer runs the app weekly starting at Sprint 5.
5. **"Stop the line" quality bar.** Define explicit triggers for phase rollback (e.g., diagnostic accuracy <60% at Sprint 9 = halt feature work, return to data).

## Critical-path corrections (3)

1. **Franco's annotation throughput is the true critical-path constraint**, not the camera core. Every ML sprint depends on labeled data, and Franco is one human. The plan acknowledges this as R9 (medium) but it is actually P0. Hire a second annotator-coach by Sprint 6 and build active-learning queues from Sprint 8.
2. **Claimed-parallel but actually coupled:** TRACK-WEB starts at Sprint 7 while TRACK-BACKEND defines the Org/Coach/Athlete schema at Sprint 13. The web track will rebuild against schema changes. Move org/role schema to Sprint 4.
3. **Genuinely parallelizable but treated serially:** Marketing site, App Store metadata, and support content (Sprint 22) can be built from Sprint 15 onward by the fractional designer + a contractor, freeing engineering capacity at the launch crunch.

## Team-scaling concerns (3)

1. **Onboarding tax is invisible in the plan.** Every engineer added in Phase 2/3 costs ~6 weeks of net-negative output (one mentor + one ramp). Adding 3 engineers around Sprint 7-10 means losing roughly 1.5 engineer-sprints right when Phase 2 needs maximum velocity. Stagger hires; finish hiring before Sprint 7.
2. **No DevOps/SRE.** Egypt daily training requires 24/7 uptime in a region with patchy connectivity. Hire a part-time SRE by Sprint 10, not "implied infrastructure maintainer."
3. **Fractional designer will bottleneck Phase 2.** Live feed, post-session report, onboarding, and coach dashboard all converge in Sprints 8-13. Convert designer to full-time by Sprint 6 or hire a second.

## Phase-gate rewrites (3 examples)

- **Phase 2 gate, "Live coaching feed feels polished and responsive"** → "P95 shot-to-feed-entry latency <2.5s across 5 consecutive Egypt sessions; <1% feed-entry render frame drops; zero crashes in 50 dogfood sessions."
- **Phase 3 gate, "Longitudinal analytics surface meaningful patterns"** → "For 3 athletes with 10+ sessions, longitudinal pipeline produces ≥1 trend insight per athlete that Franco rates 4/5 or higher for coaching utility (blind review)."
- **Phase 1 gate, "Pose estimation produces usable keypoints on shooting footage"** → "MediaPipe Pose achieves ≥0.8 PCK@0.2 on 200 manually-annotated shooting frames spanning 3 lighting conditions; failures categorized for next-sprint targeting."
