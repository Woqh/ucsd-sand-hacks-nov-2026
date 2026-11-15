"""Tiny HTTP client for the Sitwise API, standard library only (the bridge runs in the model's Python 3.12
environment, which has no `requests`/`httpx`). Sends numbers and labels only; see adapter.validate_outgoing."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from bridge.adapter import validate_outgoing

DEFAULT_BASE = "http://127.0.0.1:5001"
STORE_PATH = Path.home() / ".sitwise" / "bridge.json"


class BridgeError(Exception):
    """An API or network failure. `status` 0 = couldn't reach the server."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Api:
    def __init__(self, base: str, token: Optional[str] = None, timeout: float = 4.0):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _call(self, method: str, path: str, body: Optional[dict[str, Any]] = None, auth: bool = True) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None if body is None else json.dumps(body, allow_nan=False).encode()
        req = urllib.request.Request(self.base + "/api" + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode()).get("error", {})
            except (ValueError, AttributeError):
                err = {}
            raise BridgeError(e.code, err.get("code", "error"), err.get("message", f"HTTP {e.code}"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise BridgeError(0, "network", f"Can't reach {self.base}: {getattr(e, 'reason', e)}")

    def claim(self, code: str) -> str:
        """Exchange the dashboard's pairing code for a device token (replaces any previously paired phone)."""
        out = self._call("POST", "/pair/claim", {"code": code.strip().upper()}, auth=False)
        self.token = out["deviceToken"]
        return self.token

    def ingest(self, sample: dict[str, Any]) -> dict[str, Any]:
        return self._call("POST", "/posture/ingest", validate_outgoing(sample))

    def goal_torso_angle(self) -> Optional[float]:
        """The user's calibrated goal back angle, or None if they haven't calibrated."""
        baseline = self._call("GET", "/calibration").get("baseline") or {}
        v = (baseline.get("goal") or {}).get("torsoAngle")
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def load_saved(path: Path = STORE_PATH) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(v, str)}
    except (OSError, ValueError):
        return {}


def save_token(base: str, token: str, path: Path = STORE_PATH) -> None:
    """Remember the device token in the user's home folder (never in the repo)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"base": base, "deviceToken": token}), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
