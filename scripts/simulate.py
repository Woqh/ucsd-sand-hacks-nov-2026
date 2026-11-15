#!/usr/bin/env python3
"""Fake phone: POSTs PostureSamples to /api/posture/ingest (good -> slouch -> recover).

Lets the dashboard and alerts be developed and demoed without a camera or the real model.
Standard library only.

  # pair first (dashboard shows a code), then:
  python scripts/simulate.py --code ABC234 --slouch-after 10 --loop
  # later runs reuse the printed token:
  SITWISE_DEVICE_TOKEN=... python scripts/simulate.py --slouch-after 10

Tip: set the slouch threshold to ~5 s in the dashboard Settings so alerts fire quickly.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid


def call(base: str, path: str, body: dict, token: str | None = None) -> dict:
    req = urllib.request.Request(
        base.rstrip("/") + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        sys.exit(f"HTTP {e.code} from {path}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Can't reach {base}: {e.reason}. Is the API running? (flask --app api.index run --port 5001)")


def make_sample(session_id: str, phase: str) -> dict:
    slouching = phase == "slouch"
    j = random.uniform(-0.04, 0.04)
    return {
        "schema": 1, "sessionId": session_id, "t": int(time.time() * 1000),
        "label": "SLOUCHING" if slouching else "GOOD",
        "deviation": round(max(0.0, (0.72 if slouching else 0.12) + j), 3),
        "confidence": round(random.uniform(0.88, 0.98), 2),
        "features": {
            "neckAngle": round((34 if slouching else 16) + random.uniform(-2, 2), 1),
            "torsoAngle": round((18 if slouching else 5.5) + random.uniform(-1, 1), 1),
            "headForwardOffset": round((0.52 if slouching else 0.19) + random.uniform(-0.02, 0.02), 2),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default=os.environ.get("SITWISE_BASE", "http://127.0.0.1:5001"))
    p.add_argument("--token", default=os.environ.get("SITWISE_DEVICE_TOKEN"), help="device token")
    p.add_argument("--code", help="pairing code shown on the dashboard (claims a device token)")
    p.add_argument("--good-for", type=float, default=10, help="seconds of good posture at the start of each cycle")
    p.add_argument("--slouch-after", type=float, default=None, help="alias for --good-for")
    p.add_argument("--slouch-for", type=float, default=40, help="seconds of slouching")
    p.add_argument("--recover-for", type=float, default=15, help="seconds of good posture after the slouch")
    p.add_argument("--interval", type=float, default=1.0, help="seconds between samples")
    p.add_argument("--loop", action="store_true", help="repeat forever (Ctrl-C to stop)")
    args = p.parse_args()
    good_for = args.slouch_after if args.slouch_after is not None else args.good_for

    token = args.token
    if args.code:
        token = call(args.base, "/api/pair/claim", {"code": args.code})["deviceToken"]
        print(f"Paired. Reuse with:  SITWISE_DEVICE_TOKEN={token}")
    if not token:
        sys.exit("Need --code (first time) or --token / SITWISE_DEVICE_TOKEN")

    session = str(uuid.uuid4())
    plan = [("good", good_for), ("slouch", args.slouch_for), ("good", args.recover_for)]
    print(f"Session {session}  ->  {args.base}")
    try:
        while True:
            for phase, secs in plan:
                end = time.time() + secs
                while time.time() < end:
                    r = call(args.base, "/api/posture/ingest", make_sample(session, phase), token)
                    alert = f"  ALERT level {r['alert']['level']} {json.dumps(r['alert']['channels'])}" if r.get("alert") else ""
                    print(f"[{phase:6}] server state: {r['state']:<10}{alert}")
                    time.sleep(args.interval)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
