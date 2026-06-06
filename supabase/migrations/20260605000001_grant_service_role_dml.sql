-- Restore Supabase's default service_role privileges on the public schema.
--
-- This project's tenancy migrations granted DML to `authenticated` and revoked
-- `anon`, but never granted to `service_role`. On a default Supabase scaffold,
-- service_role automatically receives full DML across the public schema; that
-- default was omitted here. The E2E core lane provisions/destroys isolated
-- `e2e-` test identities via the service_role key and therefore needs it.
--
-- service_role already bypasses RLS and is a server-only master key, so these
-- grants do not widen the project's exposure beyond Supabase's defaults.

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO service_role;
