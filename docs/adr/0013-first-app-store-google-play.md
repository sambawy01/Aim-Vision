# ADR-0013: First App Store = Google Play (Android-First Launch)

**Status:** Accepted · **Date:** 2026-05-24 · **Owner:** Mobile lead

## Context

`aimvision-mobile/` is a single Expo + React Native codebase that
already produces both iOS and Android builds (PR #92 modernized to
SDK 56 / RN 0.85 / React 19). The Egypt National Team pilot (ADR-0016)
will issue range-loaner devices. Athletes' personal phones in the
target geography skew heavily Android, and Apple App Store review
imposes structural constraints — minor-targeted apps require
verifiable consent before submission (ADR-0011 satisfies this in
principle, but App Store Review interpretation adds 1–3 review
cycles), and the camera + recording entitlements require additional
review notes.

Building for both stores in Phase 1 means doubling submission cycles,
two privacy nutrition forms, two App Privacy / Data Safety reviews
within the same sprint, and dual TestFlight/Play-Internal pipelines
under one engineer. The codebase doesn't care; the _operational_
surface roughly doubles.

## Decision

**Phase 1 ships Android first via Google Play. iOS via TestFlight is
internal-only in Phase 1; the App Store submission is a Phase 2
milestone.**

Concretely:

- The Phase-1 release pipeline produces signed AAB → Internal Testing
  → Closed Testing → Production track on Google Play.
- iOS builds continue to be produced via Expo EAS for internal
  TestFlight distribution to the founding team + Egypt pilot coaches
  who use iOS — distribution stays inside the 100-tester limit.
- The Apple Developer Program enrolment proceeds in parallel so the
  Phase-2 App Store submission has no admin lead time.
- The Android Data Safety form, in-app purchases (none in Phase 1),
  and Play-Console privacy policy URL all use the same compliance
  artefacts as the federation procurement pack.

## Consequences

**Positive.**

- One store submission cycle in Phase 1 instead of two.
- Google Play's review for camera + minor-targeted apps is generally
  faster and more predictable than App Store Review for the same
  surface.
- TestFlight covers the iOS pilot users we have (small number of
  founding-team + Egypt coaches) without needing a public iOS
  release.
- Android-first matches the addressable-market device mix in the
  pilot geography.

**Negative.**

- Athletes on personal iPhones cannot install via App Store in
  Phase 1; they're either on TestFlight (limited to 100) or wait for
  Phase 2.
- A second store submission carries non-trivial UX-divergence
  surprises (back-button behaviour, safe-area, push-notification
  permission timing); Phase 2 needs a dedicated iOS-polish sprint.
- The mobile-CI pipeline must still keep iOS green (lint / typecheck
  / jest matrix); only the release-pipeline branch is Android-only.

## Alternatives considered

- **iOS-first** — would unblock Western Solo-tier early adopters but
  loses the Egypt-pilot device-mix advantage and adds App Store
  Review uncertainty to the GA path.
- **Simultaneous iOS + Android** — operationally heavier than the
  Phase-1 team can absorb without slipping the pilot date.
- **Web-only PWA on phones** — rejected; the camera capture path
  needs native frame access (the phone-frame-sink JSI bridge per
  ADR-0009 / PR #87).
