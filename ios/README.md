# Sitwise iOS app

SwiftUI app that sits on a chair mount, runs the posture model **on the phone**, and sends only
numbers to the API. Screens: pairing, calibration, live status, settings.

> **Status: written but not yet built.** This was authored without Xcode (Windows). Expect to fix
> a few compile errors on the first Mac build. It needs a **physical iPhone** (camera) and an
> **Apple Developer account** (push entitlement + a `.p8` APNs key).

## Run it

```bash
brew install xcodegen
cd ios
xcodegen generate          # creates Sitwise.xcodeproj from project.yml
open Sitwise.xcodeproj
```

1. Set your **Team** (Signing & Capabilities) or `DEVELOPMENT_TEAM` in `project.yml`.
2. Set the API host in [`Sitwise/Config.swift`](Sitwise/Config.swift) (`Config.baseURL`): the one place to change it. For local dev use your Mac's LAN address (`http://192.168.x.x:5001`); the Info.plist allows local-network HTTP.
3. Make sure the **bundle ID** (`com.sitwise.app` in `project.yml`) equals `APNS_BUNDLE_ID` on the server.
4. Run on a device. On the **Simulator** the app falls back to synthetic frames, so the stub flow still works end to end (push won't).

## How it fits together

```
FrameSource (camera, or synthetic on Simulator)
   -> PostureModel.analyze(frame:)      <- the seam; StubPostureModel today
   -> PostureSample (numbers only)
   -> APIClient.ingest  (POST /api/posture/ingest, ~1 Hz, Bearer device token from the Keychain)
   <- state + whether an alert was sent -> in-app banner + haptic
```

- Background / locked: the server sends an **APNs push**; the system notification vibrates the phone. Foreground: in-app banner + `UINotificationFeedbackGenerator`.
- Dev builds register **sandbox** APNs tokens (`Config.apnsSandbox`, from `#if DEBUG`); the server uses the matching Apple host per token. TestFlight/App Store builds use production.
- The monitoring screen keeps the display awake (the phone is mounted); camera frames are processed in memory and dropped.

## For the model teammate

Implement `PostureModel` (`Sitwise/Model/PostureModel.swift`) and change **one line** in
[`AppState.swift`](Sitwise/AppState.swift): `let model: PostureModel = OpenCVPostureModel()`.
See [`Model/OpenCV/README.md`](Sitwise/Model/OpenCV/README.md). Confirm angle conventions/units with the interface owner first, since they define the payload. **Open question:** who adds the OpenCV Obj-C++ bridge to the Xcode project? Agree before both people edit it.

## Not done yet

- Real camera preview / "ghost" goal-posture overlay (stretch).
- Time-sensitive notification entitlement (the server already sets `interruption-level: time-sensitive`; without the capability iOS treats it as a normal alert).
- Unit tests; everything has only been checked by reading.
