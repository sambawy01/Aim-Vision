# Launching the mobile app locally

The mobile app (`aimvision-mobile/`) is a React Native 0.76 + Expo SDK 51 project
with the New Architecture (Hermes + Fabric + JSI). It is the on-the-range
surface: athlete-facing onboarding + (dev-mode) phone capture. Code-signed
deployment to the Egypt federation lands later; this doc is for **internal
testing** on a Mac.

There is no "open in a browser" path. Vision Camera + the custom Rust frame
pipeline are native-only, so the app runs in either:

- **iOS Simulator** — full UI, the camera screen renders but no live frames
  (simulators have no camera). Fastest to see the app.
- **Physical iPhone or Android device** — full app including live camera.
  Adds Apple-ID code-signing setup the first time.

Both paths share the same first 90% of the recipe.

## Prerequisites

- macOS with **Xcode** (already verified: 26.3 on dev machines).
- **Node 20+** (Node 22 also works for the build; jest tests need Node 20).
- **CocoaPods** (`gem install cocoapods` if missing).
- The backend running and reachable from the simulator/device — see
  [running the backend](#running-the-backend-from-the-mobile-app) below.

## 1. Install dependencies

```bash
cd aimvision-mobile
pnpm install --frozen-lockfile
```

This installs everything the build needs, including
`@react-native-community/cli` (CocoaPods autolinking) and
`expo-build-properties` (sets the iOS deployment target the New Architecture
requires).

## 2. Generate the native projects

```bash
npx expo prebuild --platform ios --clean
```

What this does:

- Materializes `ios/` from the Expo config (`app.json`).
- Runs the in-repo config plugin `plugins/phone-frame-sink/withPhoneFrameSink.js`
  to copy the Swift/Kotlin sources and the Rust-FFI bridges into the native
  project (ADR-0009 slices 3b + 3c).
- Sets the iOS deployment target to **15.1** via `expo-build-properties`
  (required by RN 0.76 + Hermes).

> The config plugin is authored in plain CommonJS JS rather than TS so a fresh
> clone does not need a compile step before `expo prebuild`. The native sources
> it copies (Swift / Kotlin / Rust bridges) are still typed in their own
> languages and unit-tested under `plugins/phone-frame-sink/__tests__/`.

For Android, swap `--platform ios` for `--platform android` (and use
`./gradlew` instead of CocoaPods/Xcode).

## 3. Install CocoaPods

```bash
cd ios && pod install && cd ..
```

You will see two harmless warnings — `[!] <PBXGroup ...> attempted to
initialize an object with an unknown UUID ...` — these are CocoaPods commenting
on the project edits the phone-frame-sink plugin makes; they do not block the
build.

## 4. Build and launch

### iOS Simulator (no camera, full UI)

```bash
# Optional: boot a specific simulator first
xcrun simctl boot 'iPhone 15' 2>/dev/null && open -a Simulator

# First build is 5–15 min; subsequent builds are much faster.
npx expo run:ios
```

The app installs on the booted simulator and opens to the **Login** screen.
Sign in as the seeded coach (see [the seed script](#sign-in-credentials)).

### Physical iPhone (full camera)

```bash
# Plug in iPhone → unlock → tap "Trust This Computer"
xcrun devicectl list devices | grep -i connected   # confirm visible

npx expo run:ios --device   # picks the connected device
```

Code signing the first time:

1. The build will fail on signing.
2. Open `ios/AIMVISION.xcworkspace` in Xcode.
3. Select the **AIMVISION** target → **Signing & Capabilities**.
4. Tick **Automatically manage signing** and choose your personal team
   (your Apple ID).
5. A free Apple ID may need a unique bundle id — change
   `com.aimvision.app` to e.g. `com.<you>.aimvision` in `app.json` and
   re-prebuild.
6. On the iPhone the first launch: **Settings → General → VPN & Device
   Management → Trust the developer cert**.

Then re-run `npx expo run:ios --device`.

## Running the backend from the mobile app

The mobile app reads `API_BASE_URL` at build time (via `app.config.ts` →
`expo-constants`). Set it before `expo prebuild` / `expo run:ios`:

```bash
export API_BASE_URL=http://<your-Mac-LAN-IP>:8000   # e.g. http://192.168.0.105:8000
```

The backend must bind to `0.0.0.0` (not `127.0.0.1`) and CORS must allow the
mobile origin (not strictly required for native fetches, but worth checking):

```bash
cd aimvision-backend
AIMVISION_DATABASE_URL="sqlite+aiosqlite:///./_aimvision_dev.db" \
AIMVISION_AUDIT_DATABASE_URL="sqlite+aiosqlite:///./_aimvision_dev.db" \
  .venv/bin/python -m scripts.seed_dev
AIMVISION_DATABASE_URL="sqlite+aiosqlite:///./_aimvision_dev.db" \
AIMVISION_AUDIT_DATABASE_URL="sqlite+aiosqlite:///./_aimvision_dev.db" \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The Mac and the device/simulator must be on the same Wi-Fi.

## Sign-in credentials

`scripts/seed_dev.py` in the backend creates a coach account you can use:

- **email:** `coach@example.com`
- **password:** `demopassword123`

Signed in as the coach, the dev-mode **Capture** screen is reachable (the
`capture.phone_backend_enabled` flag defaults on in dev builds). Record a clip,
paste a session id (from the coach dashboard at `localhost:5173`), and tap
**Upload to session** — the recording posts to
`/sessions/{id}/recording` tagged `phone_dev`, then the post-session pipeline
can run over it.

## Placeholder assets

`assets/icon.png` / `splash.png` / `adaptive-icon.png` / `favicon.png` are
**1×1 placeholder PNGs**, just there so `expo prebuild` does not error on
missing files. Replace them with real artwork (typically 1024×1024) before any
build that leaves this dev environment.

## What you cannot test locally

| | |
|---|---|
| Live camera on iOS Simulator | Simulators have no camera — use a device. |
| The Hero 13 capture path | Hardware-gated; not implemented yet. |
| On-device ML (pose, diagnostic) | Models aren't bundled into the app yet. |
| WatermelonDB offline sync | `@nozbe/watermelondb` is not installed yet — sync is a pure-TS scaffold. |
| Real parental-consent verification | `/auth/parental-consent` endpoint is not implemented; the screen submits to nothing. |

These are tracked separately and are not part of the local-launch story.
