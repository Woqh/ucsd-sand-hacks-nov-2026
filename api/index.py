"""Entrypoint exporting `app`.

Local:  flask --app api.index run --debug --port 5001
Vercel: the root-level index.py re-exports this (see vercel.json / docs/deploy notes in README).
"""
from api.app import create_app

app = create_app()
