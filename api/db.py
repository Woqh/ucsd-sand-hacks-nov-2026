"""The ONLY module that talks to the database.

`get_store()` returns an object with the Store interface below. Two implementations:
  * PostgresStore: plain SQL over psycopg 3 to Tiger Cloud (TimescaleDB) or any Postgres, via the
    DATABASE_URL connection string. `events` is a hypertable (see api/schema.sql). Used whenever
    DATABASE_URL is set. Tuned for serverless: a small lazily-opened pool, no prepared statements
    (so it also works through Tiger's pgbouncer *transaction* pooler), autocommit.
  * MemoryStore (api/db_memory.py): local dev / tests only. Refused on Vercel so a missing env var
    fails loudly instead of silently losing data.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from flask import current_app

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

USER_COLS = ("id, dashboard_token_hash, device_token_hash, pairing_code, pairing_expires_at, "
             "settings, calibration")
SESSION_COLS = "id, user_id, started_at, last_t, last_seen_server_ms, state, last_sample"
EVENT_COLS = "id, user_id, session_id, t, kind, from_state, to_state, alert, level, reason, deviation"
SUB_COLS = "id, user_id, kind, endpoint, data"
_USER_UPDATABLE = {"settings", "calibration", "device_token_hash", "pairing_code", "pairing_expires_at"}
_JSON_COLS = {"settings", "calibration"}
_EVENT_INSERT_CHUNK = 200  # rows per INSERT (200 x 11 params, far under Postgres' 65535 limit)


def _ts(ms: int) -> datetime:
    """Exact epoch-ms -> timestamptz (no float rounding)."""
    return _EPOCH + timedelta(milliseconds=int(ms))


class PostgresStore:
    kind = "postgres"

    def __init__(self, dsn: str):
        import psycopg  # lazy: keeps tests / memory mode dependency-light
        from psycopg.rows import dict_row
        from psycopg.types.string import TextLoader
        from psycopg_pool import ConnectionPool

        # Return uuid columns as plain str so ids compare equal to the strings the API uses.
        psycopg.adapters.register_loader("uuid", TextLoader)
        self._psycopg = psycopg
        self.pool = ConnectionPool(
            dsn,
            min_size=0,                                   # open nothing until first use
            max_size=int(os.environ.get("DB_POOL_MAX", "4")),
            open=False,
            timeout=15,
            kwargs={"autocommit": True, "row_factory": dict_row, "connect_timeout": 10,
                    "prepare_threshold": None},           # no server-side prepared statements (pgbouncer)
        )
        self.pool.open()

    # ---- helpers
    def _run(self, fn: Callable[[Any], Any], retry: bool = True) -> Any:
        """Run fn(conn). A dropped connection (idle timeout, pooler restart) is retried once on a
        fresh one; pass retry=False for non-idempotent writes."""
        for attempt in (1, 2):
            try:
                with self.pool.connection() as conn:
                    return fn(conn)
            except self._psycopg.OperationalError:
                if attempt == 2 or not retry:
                    raise

    def _one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        return self._run(lambda c: c.execute(sql, params).fetchone())

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        return self._run(lambda c: c.execute(sql, params).fetchall())

    def _exec(self, sql: str, params: tuple = (), retry: bool = True) -> None:
        self._run(lambda c: c.execute(sql, params), retry=retry)

    def ping(self) -> tuple[bool, Optional[str]]:
        """(ok, coarse problem code). Never returns connection details."""
        try:
            self._all("select 1 from users limit 1")
            return True, None
        except self._psycopg.errors.UndefinedTable:
            return False, "schema_missing"      # run scripts/init_db.py
        except self._psycopg.OperationalError:
            return False, "connect_failed"
        except Exception:
            return False, "error"

    # ---- users
    def create_user(self, dashboard_token_hash: str, pairing_code: str, pairing_expires_at: int,
                    settings: dict) -> dict:
        from psycopg.types.json import Jsonb
        row = self._one(
            f"insert into users (dashboard_token_hash, pairing_code, pairing_expires_at, settings) "
            f"values (%s, %s, %s, %s) returning {USER_COLS}",
            (dashboard_token_hash, pairing_code, pairing_expires_at, Jsonb(settings)))
        return row  # type: ignore[return-value]

    def _user_by(self, col: str, val: str) -> Optional[dict]:
        assert col in ("dashboard_token_hash", "device_token_hash", "pairing_code")
        return self._one(f"select {USER_COLS} from users where {col} = %s limit 1", (val,))

    def get_user_by_dashboard_hash(self, h: str) -> Optional[dict]:
        return self._user_by("dashboard_token_hash", h)

    def get_user_by_device_hash(self, h: str) -> Optional[dict]:
        return self._user_by("device_token_hash", h)

    def get_user_by_pairing_code(self, code: str) -> Optional[dict]:
        return self._user_by("pairing_code", code)

    def update_user(self, user_id: str, fields: dict) -> None:
        from psycopg.types.json import Jsonb
        unknown = set(fields) - _USER_UPDATABLE
        if unknown:
            raise ValueError(f"cannot update user fields: {sorted(unknown)}")
        sets = ", ".join(f"{k} = %s" for k in fields)
        params = [Jsonb(v) if (k in _JSON_COLS and v is not None) else v for k, v in fields.items()]
        self._exec(f"update users set {sets} where id = %s", (*params, user_id))

    # ---- sessions
    def get_session(self, session_id: str) -> Optional[dict]:
        return self._one(f"select {SESSION_COLS} from sessions where id = %s", (session_id,))

    def latest_session(self, user_id: str) -> Optional[dict]:
        return self._one(f"select {SESSION_COLS} from sessions where user_id = %s "
                         f"order by last_seen_server_ms desc limit 1", (user_id,))

    def save_session(self, session: dict) -> None:
        from psycopg.types.json import Jsonb
        self._exec(
            "insert into sessions (id, user_id, started_at, last_t, last_seen_server_ms, state, last_sample) "
            "values (%s, %s, %s, %s, %s, %s, %s) "
            "on conflict (id) do update set last_t = excluded.last_t, "
            "last_seen_server_ms = excluded.last_seen_server_ms, state = excluded.state, "
            "last_sample = excluded.last_sample",
            (session["id"], session["user_id"], session["started_at"], session["last_t"],
             session["last_seen_server_ms"], Jsonb(session["state"]),
             Jsonb(session["last_sample"]) if session.get("last_sample") is not None else None))

    # ---- events (the hypertable)
    def insert_events(self, rows: list[dict]) -> None:
        for i in range(0, len(rows), _EVENT_INSERT_CHUNK):
            chunk = rows[i:i + _EVENT_INSERT_CHUNK]
            params: list[Any] = []
            for r in chunk:
                params += [r["user_id"], r.get("session_id"), _ts(r["t"]), r["t"], r.get("kind", "transition"),
                           r.get("from_state"), r.get("to_state"), bool(r.get("alert", False)),
                           int(r.get("level", 0)), r.get("reason"), r.get("deviation")]
            placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(chunk))
            self._exec("insert into events (user_id, session_id, ts, t, kind, from_state, to_state, "
                       "alert, level, reason, deviation) values " + placeholders, tuple(params), retry=False)

    def list_events(self, user_id: str, since: int, until: int) -> list[dict]:
        # filter on ts (the partition column) so TimescaleDB can skip whole chunks
        return self._all(f"select {EVENT_COLS} from events where user_id = %s and ts >= %s and ts < %s "
                         f"order by t, id", (user_id, _ts(since), _ts(until)))

    def last_event_before(self, user_id: str, t: int) -> Optional[dict]:
        return self._one(f"select {EVENT_COLS} from events where user_id = %s and kind = 'transition' "
                         f"and ts < %s order by ts desc, id desc limit 1", (user_id, _ts(t)))

    def clear_history(self, user_id: str) -> None:
        def go(conn: Any) -> None:
            with conn.transaction():
                conn.execute("delete from events where user_id = %s", (user_id,))
                conn.execute("delete from sessions where user_id = %s", (user_id,))
        self._run(go)

    # ---- push subscriptions
    def save_push_subscription(self, user_id: str, kind: str, endpoint: str, data: dict) -> None:
        from psycopg.types.json import Jsonb
        self._exec("insert into push_subscriptions (user_id, kind, endpoint, data) values (%s, %s, %s, %s) "
                   "on conflict (user_id, kind, endpoint) do update set data = excluded.data",
                   (user_id, kind, endpoint, Jsonb(data)))

    def list_push_subscriptions(self, user_id: str, kind: Optional[str] = None) -> list[dict]:
        if kind:
            return self._all(f"select {SUB_COLS} from push_subscriptions where user_id = %s and kind = %s "
                             f"order by id", (user_id, kind))
        return self._all(f"select {SUB_COLS} from push_subscriptions where user_id = %s order by id", (user_id,))

    def delete_push_subscription(self, user_id: str, kind: str, endpoint: str) -> None:
        self._exec("delete from push_subscriptions where user_id = %s and kind = %s and endpoint = %s",
                   (user_id, kind, endpoint))


_cached: Any = None


def make_store() -> Any:
    url = os.environ.get("DATABASE_URL")
    if url:
        return PostgresStore(url)
    if os.environ.get("VERCEL"):
        raise RuntimeError("DATABASE_URL must be set on Vercel (your Tiger Cloud connection string)")
    from api.db_memory import MemoryStore
    return MemoryStore(path=os.environ.get("DEV_DB_FILE", ".devdb.json"))


def get_store() -> Any:
    """Per-app store (tests inject one via app.config['STORE']); otherwise a lazily-built singleton."""
    global _cached
    injected = current_app.config.get("STORE")
    if injected is not None:
        return injected
    if _cached is None:
        _cached = make_store()
    return _cached
