-- post_queue: draft -> approve -> post pipeline for the disagreement Twitter account
-- Run this in the Supabase SQL editor (same as the v1 schema).

create table if not exists post_queue (
  id uuid primary key default gen_random_uuid(),
  -- references signals(id); kept constraint-free so this file runs standalone
  signal_id uuid,
  post_type text not null check (post_type in ('new', 'widening', 'closing', 'final_call', 'scorecard', 'thread', 'gameday')),
  post_text text not null,
  status text not null default 'draft'
    check (status in ('draft', 'approved', 'rejected', 'posted', 'failed')),
  scheduled_for timestamptz,
  posted_at timestamptz,
  platform_post_id text,
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_post_queue_status_sched
  on post_queue (status, scheduled_for);

create index if not exists idx_post_queue_signal
  on post_queue (signal_id);
