-- Execute as the non-owner application role after migration and seed.
begin;
select set_config('app.institution_id', '11111111-1111-1111-1111-111111111111', true);
select set_config('app.user_id', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', true);

do $$
begin
  if exists (
    select 1
    from institution_memberships
    where institution_id = '22222222-2222-2222-2222-222222222222'
  ) then
    raise exception 'RLS failure: institution A can read institution B membership';
  end if;
end $$;

rollback;
