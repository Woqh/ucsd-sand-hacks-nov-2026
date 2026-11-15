#!/usr/bin/env python3
"""Fill the API with a realistic week of fake posture history (needs ENABLE_DEV_ROUTES=1).

  python scripts/seed.py                      # new demo user; prints a dashboard link
  python scripts/seed.py --token <dashboard>  # seed an existing user instead

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default=os.environ.get("SITWISE_BASE", "http://127.0.0.1:5001"),
                   help="API base URL (where Flask is running)")
    p.add_argument("--web", default=None, help="dashboard URL to print in the link (default: Vite dev server, "
                                               "or --base if it's not localhost)")
    p.add_argument("--token", help="existing dashboard token to seed (omit to create a new demo user)")
    p.add_argument("--days", type=int, default=42, help="days of history (42 = six weeks: enough for week-over-week and the pain-vs-slouching view)")
    p.add_argument("--tz", type=int, default=None, help="minutes east of UTC (default: this machine's offset)")
    args = p.parse_args()

    tz = args.tz if args.tz is not None else -int((time.altzone if time.daylight and time.localtime().tm_isdst > 0
                                                   else time.timezone) / 60)
    req = urllib.request.Request(
        args.base.rstrip("/") + "/api/dev/seed", method="POST",
        data=json.dumps({"days": args.days, "tzOffsetMin": tz}).encode(),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {args.token}"} if args.token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')}  (is ENABLE_DEV_ROUTES=1 set on the API?)")
    except urllib.error.URLError as e:
        sys.exit(f"Can't reach {args.base}: {e.reason}")

    print(f"Seeded {out['events']} events over {out['days']} days.")
    if "dashboardToken" in out:
        web = args.web or ("http://localhost:5173" if "localhost" in args.base or "127.0.0.1" in args.base else args.base)
        print(f"\nOpen the dashboard as this demo user:\n  {web.rstrip('/')}/?token={out['dashboardToken']}")
        print(f"\nPairing code for the phone / simulator (10 min):  {out['pairingCode']}")


if __name__ == "__main__":
    main()
