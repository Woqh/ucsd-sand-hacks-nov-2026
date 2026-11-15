"""Vercel entrypoint.

Vercel's Python runtime looks for a Flask instance named `app` in a root-level
index.py/app.py/server.py/main.py. The real app lives in api/ (see api/app.py);
this file just re-exports it so `api/` can stay a normal package.

Local dev does not use this file: `flask --app api.index run --debug --port 5001`.
"""
from api.index import app  # noqa: F401
