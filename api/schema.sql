-- Sitwise schema for Postgres, built for Tiger Cloud (TimescaleDB). Safe to re-run.
--   python scripts/init_db.py        applies this file to DATABASE_URL
-- or paste it into the Tiger Console SQL editor.
--
-- Only the Flask API connects (with the database credentials), so there is no row-level security to
-- wire up. All timestamps from the phone are epoch milliseconds (bigint, `t`); `events` also carries
-- the same instant as `ts` (timestamptz) because that is its hypertable partition column.
-- On plain Postgres (no TimescaleDB) the same file works and `events` is an ordinary table.

create table if not exists users (
  id                    uuid primary key default gen_random_uuid(),
  created_at            timestamptz not null default now(),
  dashboard_token_hash  text unique not null,
  device_token_hash     text unique,
  pairing_code          text unique,
  pairing_expires_at    bigint,
  settings              jsonb not null default '{}'::jsonb,
  calibration           jsonb
);

-- One row per monitoring session (a sessionId minted by the phone). `state` is the persisted
-- state-machine state; the state machine is stateless per request, so this is loaded on every ingest.
create table if not exists sessions (
  id                   uuid primary key,
  user_id              uuid not null references users(id) on delete cascade,
  started_at           bigint not null,
  last_t               bigint not null,           -- last sample time (phone clock)
  last_seen_server_ms  bigint not null,           -- server receive time (used for stale/AWAY detection)
  state                jsonb not null,
  last_sample          jsonb
);
create index if not exists sessions_user_seen on sessions (user_id, last_seen_server_ms desc);

-- State transitions (and escalation alerts): the time series. Durations and every metric derive from
-- these. No primary key on purpose: a hypertable's unique indexes must include the partition column.
create table if not exists events (
  id          bigint generated always as identity,
  user_id     uuid not null references users(id) on delete cascade,
  session_id  uuid,
  ts          timestamptz not null,                -- same instant as t (hypertable partition column)
  t           bigint not null,                     -- epoch ms, phone clock
  kind        text not null default 'transition',  -- transition | alert
  from_state  text,
  to_state    text,
  alert       boolean not null default false,
  level       int not null default 0,
  reason      text,
  deviation   double precision
);
create index if not exists events_user_ts on events (user_id, ts desc);

create table if not exists push_subscriptions (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references users(id) on delete cascade,
  kind        text not null,                       -- web | apns
  endpoint    text not null,                       -- web: push endpoint URL, apns: device token
  data        jsonb not null default '{}'::jsonb,  -- web: {keys:{p256dh,auth}}, apns: {sandbox:bool}
  created_at  timestamptz not null default now(),
  unique (user_id, kind, endpoint)
);

-- Weekly pain check-ins (0-10, optional body area). Compared against the user's OWN slouch exposure
-- in /api/insights/pain. Never used to predict anything; see docs/health-claims.md.
create table if not exists checkins (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references users(id) on delete cascade,
  created_at  timestamptz not null default now(),
  t           bigint not null,                      -- epoch ms (server time)
  pain        smallint not null check (pain between 0 and 10),
  area        text                                  -- neck | upper_back | lower_back | shoulders | other | null
);
create index if not exists checkins_user_t on checkins (user_id, t desc);

-- Downsampled posture readings (at most one per ~5 s while someone is seated). Events say WHEN the
-- state changed; samples say HOW: the three features behind the "slouch fingerprint", posture drift
-- and the setup hints. `state` is the state machine's state at that moment. Time series: hypertable.
create table if not exists samples (
  user_id     uuid not null references users(id) on delete cascade,
  ts          timestamptz not null,                 -- same instant as t (hypertable partition column)
  t           bigint not null,                      -- epoch ms, phone clock
  session_id  uuid,
  state       text,                                 -- GOOD | DEVIATING | SLOUCHING | AWAY
  label       text,
  deviation   double precision,
  confidence  double precision,
  neck        double precision,                     -- features.neckAngle
  torso       double precision,                     -- features.torsoAngle (spine/back angle)
  head_fwd    double precision                      -- features.headForwardOffset
);
create index if not exists samples_user_ts on samples (user_id, ts desc);

-- Every goal posture the user has saved, so we can see how it changes over time (posture drift).
create table if not exists calibrations (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references users(id) on delete cascade,
  t           bigint not null,                      -- epoch ms (server time)
  baseline    jsonb not null
);
create index if not exists calibrations_user_t on calibrations (user_id, t desc);

-- Tiger Cloud / TimescaleDB: make the time series hypertables, compress old chunks, expire old
-- samples, and keep an hourly rollup of samples current as data arrives (a continuous aggregate).
-- Skipped automatically where the extension isn't available (plain Postgres keeps ordinary tables).
-- Everything past create_hypertable is best-effort dynamic SQL: TimescaleDB renamed these APIs across
-- versions, so a failure in one step only prints a notice and the rest still runs.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'timescaledb') then
    create extension if not exists timescaledb;
    perform create_hypertable('events', 'ts', chunk_time_interval => interval '7 days',
                              if_not_exists => true, migrate_data => true);
    perform create_hypertable('samples', 'ts', chunk_time_interval => interval '1 day',
                              if_not_exists => true, migrate_data => true);
    begin
      execute 'alter table events set (timescaledb.enable_columnstore = true, timescaledb.segmentby = ''user_id'', timescaledb.orderby = ''ts desc'')';
      execute 'call add_columnstore_policy(''events'', after => interval ''14 days'', if_not_exists => true)';
    exception when others then
      raise notice 'events is a hypertable but compression was not configured: %', sqlerrm;
    end;
    begin
      execute 'alter table samples set (timescaledb.enable_columnstore = true, timescaledb.segmentby = ''user_id'', timescaledb.orderby = ''ts desc'')';
      execute 'call add_columnstore_policy(''samples'', after => interval ''3 days'', if_not_exists => true)';
    exception when others then
      raise notice 'samples is a hypertable but compression was not configured: %', sqlerrm;
    end;
    begin
      execute 'select add_retention_policy(''samples'', interval ''90 days'', if_not_exists => true)';
    exception when others then
      raise notice 'samples retention policy was not configured: %', sqlerrm;
    end;
    begin
      execute $cagg$
        create materialized view if not exists samples_hourly with (timescaledb.continuous) as
        select user_id, state, time_bucket('1 hour', ts) as hour, count(*) as n,
               avg(deviation) as avg_dev, avg(neck) as avg_neck, avg(torso) as avg_torso,
               avg(head_fwd) as avg_head_fwd
        from samples group by user_id, state, time_bucket('1 hour', ts)
        with no data
      $cagg$;
      execute 'select add_continuous_aggregate_policy(''samples_hourly'', start_offset => interval ''3 days'', end_offset => interval ''1 hour'', schedule_interval => interval ''30 minutes'', if_not_exists => true)';
    exception when others then
      raise notice 'samples_hourly continuous aggregate was not configured: %', sqlerrm;
    end;
  else
    raise notice 'timescaledb not available: events and samples are plain tables';
  end if;
end $$;
