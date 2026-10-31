-- JEG-1351: four verified aliases for Sleeper spellings of players the
-- table already holds under another name.
--
-- NOT APPLIED. Needs Jeremy's yes before it runs on production
-- (iskiybsimubiujwuchsl). Data only, no DDL. The same four rows are in the
-- jeg438_alias_table_curated.sql seed and data/inputs/player_aliases.json
-- (tests/test_player_alias_table.py pins the seed to the JSON). Until this
-- runs, lib/player_aliases.load() reads the 13 curated rows from Supabase and
-- production resolvers do not see these four; reconcile_player_identity.py
-- reports the drift.
--
-- Each tie is Sleeper id -> gsis (data/inputs/sleeper_projection_idmap.csv,
-- status matched) -> the row carrying that gsis_id (read-only SQL,
-- 2026-10-29 23:30 UTC).

insert into public.player_name_aliases
    (source, source_player_name, norm_name, position, player_key, status, method,
     confidence, verified_at, verified_by, notes)
select '*', v.alias, v.norm_name, v.pos, v.player_key, 'verified', 'curated',
       1, now(), 'jeg1351-curated', v.verified
from (values
    ('Nyheim Miller-Hines', 'nyheim millerhines', 'RB', 2785, '2026-10-29 JEG-1351: Sleeper 5347 -> gsis 00-0034367 = 2785 Nyheim Hines'),
    ('Jody Fortson', 'jody fortson', 'TE', 437, '2026-10-29 JEG-1351: Sleeper 6665 -> gsis 00-0035547 = 437 Joseph Fortson'),
    ('Mitch Tinsley', 'mitch tinsley', 'WR', 4363, '2026-10-29 JEG-1351: Sleeper 11068 -> gsis 00-0038839 = 4363 Mitchell Tinsley'),
    ('Tyron Billy-Johnson', 'tyron billyjohnson', 'WR', 423, '2026-10-29 JEG-1351: Sleeper 6063 -> gsis 00-0035457 = 423 Tyron Johnson')
) as v(alias, norm_name, pos, player_key, verified)
on conflict (source, norm_name, position) do update set
    source_player_name = excluded.source_player_name,
    player_key = excluded.player_key,
    status = 'verified',
    method = 'curated',
    confidence = 1,
    candidate_keys = null,
    verified_at = excluded.verified_at,
    verified_by = excluded.verified_by,
    notes = excluded.notes,
    last_seen_at = now();
