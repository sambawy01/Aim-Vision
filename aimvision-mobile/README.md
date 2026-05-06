# aimvision-mobile

React Native client for AIMVISION. Pre-camera scaffold (Sprint 3 deliverable).
The native-module bridge to `aimvision-camera-core` is a Sprint 4 deliverable; this
scaffold establishes the New Architecture toolchain, age gate + parental consent
flows, granular consent matrix, i18n + RTL, accessibility primitives, Sentry,
Statsig, EAS Update, and the iOS privacy manifest.

## Architectural authorities

- `docs/adr/0002-mobile-rn-new-architecture.md` — RN 0.76 + New Architecture
  (Hermes, Fabric, JSI, TurboModules) is mandatory.
- `docs/mobile-architecture.md` — canonical spec; bindings, sync, performance,
  privacy, accessibility, i18n.
- `docs/compliance/parental-consent-flow.md` — age gate, verifiable consent,
  consent matrix, audit trail.

## Quickstart

```bash
pnpm install                # or npm install / yarn
npx expo prebuild           # generates ios/ and android/ projects
npx expo run:ios            # boots iOS simulator (requires Xcode 15+ + macOS)
npx expo run:android        # boots Android emulator (requires Android SDK 34)
pnpm test                   # Jest
pnpm lint                   # ESLint
pnpm typecheck              # tsc --noEmit
pnpm format                 # Prettier write
```

The CI workflow at `.github/workflows/mobile-ci.yml` runs `typecheck`, `lint`,
and `test` only — native builds need a macOS runner with Xcode and a matching
Android SDK and are deferred to Sprint 4.

## Stack

- **React Native 0.76** with the **New Architecture** enabled in `app.json`
  (`expo.newArchEnabled: true`).
- **Hermes**, **Fabric**, **JSI**, **TurboModules** — required by ADR-0002.
- **Expo SDK 51** for tooling: `expo-updates` (EAS Update), `expo-localization`,
  `expo-secure-store`, `expo-build-properties`, `expo-constants`.
- **TypeScript strict** — see `tsconfig.json`.
- **Navigation:** React Navigation v7 native stack.
- **State:** Zustand.
- **Animations:** Reanimated v3 (`react-native-reanimated@~3.15`).
- **i18n:** i18next + react-i18next, EN + AR catalogues, RTL bootstrap via
  `I18nManager.forceRTL` + `Updates.reloadAsync()`.
- **Crash + perf:** `@sentry/react-native` with PII scrubbing in `beforeSend`.
- **Feature flags:** `statsig-react-native-expo`.
- **Overlay (declared, not yet used):** `@shopify/react-native-skia`.

## Notable structure

- `ios/PrivacyInfo.xcprivacy` — required API reasons (`CA92.1`, `C617.1`,
  `35F9.1`, `E174.1`); `NSPrivacyCollectedDataTypes` is a TODO stub awaiting
  compliance counsel sign-off.
- `src/screens/onboarding/` — age gate, parental consent, child setup, consent
  matrix, welcome.
- `src/components/RangeMode/` — high-contrast outdoor variant; activates above
  50,000 lux per UX review.
- `src/components/a11y/` — Dynamic Type-aware Text + 44/56 pt tap targets.
- `src/state/consentStore.ts` — per-category × per-purpose grid with off-by-default.
- `src/services/consent.ts` — `grant`/`revoke` wired to backend stubs.

## Sprint posture

- Sprint 3 (this scaffold): RN/Expo bootstrap, age gate, consent flow, i18n,
  a11y primitives, Sentry/Statsig/EAS infra, PrivacyInfo manifest.
- Sprint 4: native bridge to `aimvision-camera-core` (UniFFI control plane,
  hand-written C ABI for frames), TurboModule specs, BLE pairing UI.
- Sprint 5: WatermelonDB + sync engine.
- Sprint 7: thermal/battery telemetry stream, debug overlay.
- Sprint 8+: Egypt validation prep (AR-EG translations, in-region processing).

## Native bring-up notes

`npx expo prebuild` generates `ios/` and `android/`. The committed
`ios/PrivacyInfo.xcprivacy` is referenced from `app.json` and gets folded into
the generated Xcode project; verify it is added to the app target's "Copy Bundle
Resources" build phase before TestFlight upload.

For New Architecture verification post-prebuild:

- iOS: `ios/Podfile.properties.json` should contain `"newArchEnabled": "true"`.
- Android: `android/gradle.properties` should contain `newArchEnabled=true`
  and `hermesEnabled=true`.

These are seeded by the `expo-build-properties` plugin in `app.json`.
