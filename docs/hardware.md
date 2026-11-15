# Hardware: the chair mount

Sitwise uses an **iPhone mounted on the chair, looking at the user from the side**, so the camera
sees their back and profile (neck, shoulders, torso lean). A side view is what makes forward-head
and rounded-back posture visible; a front-facing webcam mostly can't see it.

> This page is a **starting point to be refined once the real model and a physical mount exist**.
> Distances, angles and the mount choice below are suggestions to try, not measured specs.

## Setup

- **Phone:** any iPhone that runs the app (iOS 16+), **portrait**, with the rear camera facing the user's side.
- **Mount:** something that clamps to the chair (an armrest or backrest post) or sits on the desk edge beside the chair, with an adjustable arm (gooseneck/phone clamp). It needs to hold still: a swaying mount looks like a posture change to the model.
- **Framing:** aim for head, shoulders, back and hips in frame, at roughly desk height, pointing at the user's side. Calibration (the "sit comfortably" flow) records the goal posture **from this exact placement**, so if you move the mount, recalibrate.
- **Power and screen:** keep the phone plugged in. The monitoring screen disables auto-lock (the app holds the camera and must stay in the foreground); expect warmth and battery drain otherwise.
- **Light:** even, front-or-side lighting. A strong backlight (window behind the user) hurts pose estimation.

## Webcam alternative (the real model today)

The teammate's model runs on a computer, not in the iPhone app (`docs/model-bridge.md`). A laptop or USB webcam, or a phone
used as a webcam, clamped to the **side** of the chair and aimed at your profile works the same way: head, shoulders, back
and hips in frame, level (camera tilt is assumed zero), steady, evenly lit, and **only one person in view**. Set `--facing`
to where your nose points in the image. The model abstains rather than guessing if it can't see your torso.

## What leaves the phone

Only numbers: posture features (angles/offsets), a label, a confidence and a timestamp, about once a second (the webcam bridge sends exactly the same, and refuses to send anything else). **Camera frames are processed in memory on the phone and dropped; they are never saved, logged or uploaded.** This holds by construction: the API has no field that could carry an image, and the iOS code never serialises frames.

## Alerts on the hardware

- Phone in the foreground: in-app banner + haptic.
- Phone in the background or locked: an **APNs push** (sent by the server); the system notification provides the vibration. Note the phone is the camera, so it is normally foreground while monitoring; the desktop web push covers the case where the user is looking at their computer instead.

## To measure later

Mount height and distance that work best, minimum lighting, battery/thermal behaviour over a workday, and how much mount wobble the model tolerates.
