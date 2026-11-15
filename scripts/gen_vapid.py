#!/usr/bin/env python3
"""Generate a VAPID key pair for Web Push. Prints env lines; paste them into .env / Vercel.
Needs the project requirements installed (py-vapid ships with pywebpush)."""
import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


v = Vapid()
v.generate_keys()
public = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
private = v.private_key.private_numbers().private_value.to_bytes(32, "big")

print(f"VAPID_PUBLIC_KEY={b64url(public)}")
print(f"VAPID_PRIVATE_KEY={b64url(private)}")
print("VAPID_SUBJECT=mailto:you@example.com   # change to a real contact address")
