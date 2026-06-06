-- Storage buckets for project assets (cover/logo images) and workspace fonts.
-- Objects are stored at <workspace_id>/<filename>; RLS enforces workspace membership
-- via the private.is_workspace_member() SECURITY DEFINER helper from migration 001.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'project-assets',
  'project-assets',
  false,
  10485760,
  ARRAY['image/jpeg','image/png','image/gif','image/webp','image/svg+xml']
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'workspace-fonts',
  'workspace-fonts',
  false,
  5242880,
  ARRAY['font/ttf','font/otf','font/woff','font/woff2','application/octet-stream']
)
ON CONFLICT (id) DO NOTHING;

-- project-assets RLS
CREATE POLICY "project_assets_select" ON storage.objects
  FOR SELECT TO authenticated
  USING (bucket_id = 'project-assets' AND private.is_workspace_member(split_part(name, '/', 1)::uuid));

CREATE POLICY "project_assets_insert" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'project-assets' AND private.is_workspace_member(split_part(name, '/', 1)::uuid));

CREATE POLICY "project_assets_update" ON storage.objects
  FOR UPDATE TO authenticated
  USING (bucket_id = 'project-assets' AND private.is_workspace_member(split_part(name, '/', 1)::uuid))
  WITH CHECK (bucket_id = 'project-assets' AND private.is_workspace_member(split_part(name, '/', 1)::uuid));

CREATE POLICY "project_assets_delete" ON storage.objects
  FOR DELETE TO authenticated
  USING (bucket_id = 'project-assets' AND private.is_workspace_member(split_part(name, '/', 1)::uuid));

-- workspace-fonts RLS
CREATE POLICY "workspace_fonts_select" ON storage.objects
  FOR SELECT TO authenticated
  USING (bucket_id = 'workspace-fonts' AND private.is_workspace_member(split_part(name, '/', 1)::uuid));

CREATE POLICY "workspace_fonts_insert" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'workspace-fonts' AND private.is_workspace_member(split_part(name, '/', 1)::uuid));

CREATE POLICY "workspace_fonts_update" ON storage.objects
  FOR UPDATE TO authenticated
  USING (bucket_id = 'workspace-fonts' AND private.is_workspace_member(split_part(name, '/', 1)::uuid))
  WITH CHECK (bucket_id = 'workspace-fonts' AND private.is_workspace_member(split_part(name, '/', 1)::uuid));

CREATE POLICY "workspace_fonts_delete" ON storage.objects
  FOR DELETE TO authenticated
  USING (bucket_id = 'workspace-fonts' AND private.is_workspace_member(split_part(name, '/', 1)::uuid));

-- Explicit anon deny (belt-and-suspenders; public=false already blocks)
CREATE POLICY "project_assets_deny_anon" ON storage.objects
  FOR ALL TO anon USING (bucket_id != 'project-assets');

CREATE POLICY "workspace_fonts_deny_anon" ON storage.objects
  FOR ALL TO anon USING (bucket_id != 'workspace-fonts');
