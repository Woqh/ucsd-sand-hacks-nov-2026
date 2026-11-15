"""Shared fixtures. The `store` fixture runs every API test twice: against the in-memory store and,
when TEST_DATABASE_URL is set, against a real Postgres.

    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres pytest api

WARNING: the Postgres run DROPS and recreates the Sitwise tables in that database. It refuses any
non-local host unless ALLOW_REMOTE_TEST_DB=1, so it can't wipe a Tiger Cloud service by accident.
"""
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from api.db_memory import MemoryStore

SCHEMA = (Path(__file__).resolve().parent.parent / "schema.sql").read_text(encoding="utf-8")


def _postgres_store():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to also run against Postgres")
    host = urlparse(url).hostname
    if host not in ("localhost", "127.0.0.1", "::1") and os.environ.get("ALLOW_REMOTE_TEST_DB") != "1":
        pytest.fail(f"Refusing to run destructive tests against non-local host {host!r}. "
                    "Use a local/throwaway database, or set ALLOW_REMOTE_TEST_DB=1 if you are sure.")
    import psycopg

    from api.db import PostgresStore
    with psycopg.connect(url, autocommit=True, prepare_threshold=None) as c:
        c.execute("drop table if exists samples, calibrations, checkins, events, sessions, push_subscriptions, users cascade")
        c.execute(SCHEMA)
    return PostgresStore(url)


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        yield MemoryStore()
        return
    s = _postgres_store()
    yield s
    s.pool.close()


# --- read-only peeks that work for either store (the API itself never needs these) -----------

def _rows(store, sql):
    with store.pool.connection() as c:
        return c.execute(sql).fetchall()


def all_events(store):
    if hasattr(store, "events"):
        return store.events
    return _rows(store, "select id, user_id, session_id, t, kind, from_state, to_state, alert, level, "
                        "reason, deviation from events order by t, id")


def all_users(store):
    if hasattr(store, "users"):
        return list(store.users.values())
    return _rows(store, "select * from users")


def all_samples(store):
    if hasattr(store, "samples"):
        return store.samples
    return _rows(store, "select user_id, t, session_id, state, label, deviation, confidence, neck, torso, head_fwd "
                        "from samples order by t")


def all_subscriptions(store):
    if hasattr(store, "subs"):
        return store.subs
    return _rows(store, "select * from push_subscriptions")
