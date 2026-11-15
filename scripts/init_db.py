#!/usr/bin/env python3
"""Create (or update) the Sitwise schema on the database in DATABASE_URL: Tiger Cloud or any Postgres.

  python scripts/init_db.py                    # uses DATABASE_URL from the environment or ./.env
  python scripts/init_db.py --url postgres://...

Safe to re-run. Prefer Tiger's DIRECT connection string (not the pooler) for this one-off.
Needs psycopg (pip install -r requirements.txt); reads .env only if python-dotenv is installed.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:  # optional convenience: pick up DATABASE_URL from .env like the flask CLI does
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--url", default=os.environ.get("DATABASE_URL"), help="Postgres connection string")
args = p.parse_args()
if not args.url:
    sys.exit("No DATABASE_URL. Set it in .env / the environment, or pass --url.")

import psycopg  # noqa: E402

sql = (ROOT / "api" / "schema.sql").read_text(encoding="utf-8")
try:
    with psycopg.connect(args.url, autocommit=True, prepare_threshold=None, connect_timeout=15) as conn:
        conn.add_notice_handler(lambda d: print(f"  notice: {d.message_primary}"))
        conn.execute(sql)
        tables = [r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema = 'public' "
            "and table_name in ('users','sessions','events','push_subscriptions') order by 1").fetchall()]
        hyper = conn.execute(
            "select exists (select 1 from pg_extension where extname = 'timescaledb')").fetchone()[0] and conn.execute(
            "select exists (select 1 from timescaledb_information.hypertables where hypertable_name = 'events')").fetchone()[0]
except psycopg.OperationalError as e:
    sys.exit(f"Could not connect: {str(e).strip().splitlines()[0]}")

print(f"Schema applied. Tables: {', '.join(tables)}")
print("events is a TimescaleDB hypertable." if hyper else "events is a plain table (TimescaleDB not detected).")
