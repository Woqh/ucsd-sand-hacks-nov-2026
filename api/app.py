"""Flask app factory. All routes live under /api. JSON in, JSON out."""
from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify

from api import util
from api.errors import ApiError
from api.routes import (calibration, checkins, dev, export, metrics, model_stubs, pair, posture, push,
                        settings, status)

log = logging.getLogger("sitwise")


def create_app(store: Any = None) -> Flask:
    # static_folder=None: on Vercel static files come from /public (the Vite build), not Flask.
    app = Flask(__name__, static_folder=None)
    if store is not None:
        app.config["STORE"] = store  # tests inject a MemoryStore

    for module in (pair, posture, status, settings, calibration, metrics, checkins, export, push, model_stubs, dev):
        app.register_blueprint(module.bp, url_prefix="/api")

    @app.get("/api/health")
    def health():
        # Deliberately unauthenticated and non-sensitive: lets the dashboard show a demo-data
        # button only when dev routes are on, and tells you which store you're talking to and
        # whether it works. `problem` is a coarse code (never connection details):
        # schema_missing | connect_failed | error.
        from api.db import get_store
        store = get_store()
        db_ok, problem = store.ping()
        return {"schema": util.SCHEMA, "ok": db_ok, "devRoutes": util.dev_routes_enabled(),
                "store": getattr(store, "kind", "unknown"), "db": {"ok": db_ok, "problem": problem}}

    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return jsonify({"error": {"code": e.code, "message": e.message, **e.extra}}), e.status

    @app.errorhandler(404)
    def _not_found(_e):
        return jsonify({"error": {"code": "not_found", "message": "Not found"}}), 404

    @app.errorhandler(405)
    def _bad_method(_e):
        return jsonify({"error": {"code": "method_not_allowed", "message": "Method not allowed"}}), 405

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        log.exception("unhandled error")  # never log request bodies
        return jsonify({"error": {"code": "internal", "message": "Internal server error"}}), 500

    return app
