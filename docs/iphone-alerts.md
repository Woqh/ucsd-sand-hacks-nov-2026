# External iPhone posture alerts

The computer or sensor sends posture readings. After sustained poor posture (30 seconds by default,
adjustable in Settings), the server sends Web Push to the separately paired iPhone. It respects
the phone alert toggle, quiet hours, focus settings and cooldown. The receiver does not replace the sensor.

## Server setup

Use an HTTPS deployment or HTTPS tunnel reachable from the phone. A computer's localhost URL and
plain HTTP LAN address cannot provide iPhone Web Push. Generate VAPID keys with
`python scripts/gen_vapid.py`, save them privately as `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`
and `VAPID_SUBJECT` (a real contact mailto address) in the API environment, and restart the server.
Never commit the private key. Settings shows whether the keys and receiver registrations are present.

## Phone setup and physical check

1. On iOS 16.4+, open the HTTPS site's `/receive` page in Safari.
2. Add it to the Home Screen, then open **Sitwise Alerts** from that icon before pairing.
3. In desktop Settings, generate a phone setup code. Enter it in the installed phone app.
4. Tap **Enable alerts on this phone** and grant notification permission.
5. Enable notifications for Sitwise and select **Always Play** in Sounds & Haptics → Haptics.
   Check Focus settings if alerts are silenced.
6. In desktop Settings, enable phone alerts and click **Test phone alert**. Confirm vibration on the
   actual phone, including with the screen locked. A push provider accepting a message does not prove delivery.
7. Allow data collection, start the posture sensor, and maintain poor posture past the configured
   duration. Confirm one alert, with no repeated alerts before the cooldown expires.

iOS controls notification vibration. The web app cannot force a custom vibration pattern or override
disabled haptics, Focus, or notification permissions. The service worker's vibration pattern is only
a hint for browsers that support it. No physical iPhone test is performed by the automated API tests.

References: [WebKit's iPhone Web Push requirements](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/),
[Apple's haptic settings](https://support.apple.com/en-us/127222).
