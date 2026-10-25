do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'businex_owner') then
    create role businex_owner login password 'businex_owner' nosuperuser nocreatedb nocreaterole;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'businex_app') then
    create role businex_app login password 'businex_app' nosuperuser nocreatedb nocreaterole;
  end if;
end $$;

grant connect on database businex to businex_owner, businex_app;
grant usage, create on schema public to businex_owner;
grant usage on schema public to businex_app;
