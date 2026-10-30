-- JEG-1268. PROPOSED, NOT APPLIED. Applying it needs Jeremy's fresh yes naming
-- this migration (its DROP CONSTRAINT also raises Supabase's confirmation
-- prompt, which only reaches him from the main chat). Follow-up to the applied
-- jeg1195_weekly_fantasypros_20261029.sql, which stays as it ran.
--
-- The bug: weekly_fantasypros_pages_shown was
--     (shown_count is null and total_count is null)
--     or (shown_count = total_count and rows_expected = shown_count)
-- When exactly one count is null, the first arm is false and the second is
-- NULL, so the whole check is NULL, and a CHECK constraint passes on NULL.
-- A page could land with (shown NULL, total 100, rows 60) or
-- (shown 60, total NULL, rows 60): "showing X of Y" read half-way, list not
-- proven complete.
--
-- The fix: both counts or neither, said as a plain boolean equality that is
-- never NULL, and the equality arm only runs on two non-null counts. Every
-- combination of values now gives true or false, never unknown
-- (tests/test_weekly_fantasypros_contract.py checks all of them).
--
-- Safe on live data: one ALTER TABLE statement drops and re-adds the
-- constraint, so there is no moment without it. If a page already stored
-- breaks the new rule, the check below stops the migration and nothing
-- changes; that page is then a finding to report, not one to repair here.

do $$
declare
    v_bad integer;
begin
    select count(*) into v_bad from public.weekly_fantasypros_pages
     where (shown_count is null) <> (total_count is null);
    if v_bad > 0 then
        raise exception 'jeg1268: % stored page(s) have only one of shown_count/total_count; nothing changed', v_bad;
    end if;
end;
$$;

alter table public.weekly_fantasypros_pages
    drop constraint weekly_fantasypros_pages_shown,
    add constraint weekly_fantasypros_pages_shown check (
        (shown_count is null) = (total_count is null)
        and (shown_count is null
             or (shown_count is not null and total_count is not null
                 and shown_count = total_count and rows_expected = shown_count)));

comment on constraint weekly_fantasypros_pages_shown on public.weekly_fantasypros_pages is
    'JEG-1268: "showing X of Y" counts are both present or both absent; when present, every player is shown and every row read. Null-safe: never unknown.';
