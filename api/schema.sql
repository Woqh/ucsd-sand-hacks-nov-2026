-- Sitwise schema for Supabase (Postgres). Run once in the Supabase SQL editor.
-- All timestamps from the phone are epoch milliseconds (bigint). Only the Flask API (service-role
-- key) touches these tables. Row Level Security is ENABLED on every table below with NO policies, so
-- the public (publishable/anon) key can read and write nothing, while the service-role key bypasses
-- RLS and keeps working. (Supabase exposes public-schema tables to the Data API, so leaving RLS off
-- would make them reachable with the publishable key.) There are no policies to wire up.

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

-- State transitions (and escalation alerts). Durations and every metric derive from these.
create table if not exists events (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references users(id) on delete cascade,
  session_id  uuid,
  t           bigint not null,
  kind        text not null default 'transition',  -- transition | alert
  from_state  text,
  to_state    text,
  alert       boolean not null default false,
  level       int not null default 0,
  reason      text,
  deviation   real
);
create index if not exists events_user_t on events (user_id, t);

create table if not exists push_subscriptions (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references users(id) on delete cascade,
  kind        text not null,                       -- web | apns
  endpoint    text not null,                       -- web: push endpoint URL, apns: device token
  data        jsonb not null default '{}'::jsonb,  -- web: {keys:{p256dh,auth}}, apns: {sandbox:bool}
  created_at  timestamptz not null default now(),
  unique (user_id, kind, endpoint)
);

-- Lock the tables to the service role (safe to re-run).
alter table users              enable row level security;
alter table sessions           enable row level security;
alter table events             enable row level security;
alter table push_subscriptions enable row level security;
