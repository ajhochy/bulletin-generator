#!/usr/bin/env bash
# Create the GitHub issues for the Supabase + multi-tenant + Electron migration
# from the local files in docs/ai/generated-issues/.
#
# Safe to re-run: skips any issue whose exact "NNN: title" already exists
# (matched by title within the supabase-migration label).
#
# Usage:  bash scripts/create_migration_issues.sh
# Requires: gh CLI authenticated (gh auth status).

set -euo pipefail
cd "$(dirname "$0")/.."

R="ajhochy/bulletin-generator"
MS="Supabase + Multi-tenant + Electron"
LABEL="supabase-migration"

echo "Repo: $(gh repo view "$R" --json nameWithOwner -q .nameWithOwner)"

# Milestone (idempotent)
gh api -X POST "repos/$R/milestones" \
  -f title="$MS" \
  -f description="Re-platform to Supabase (Postgres + Auth + RLS), multi-tenant Workspaces, and an Electron desktop client. Plan: docs/ai/current-plan.md. Foundation (merge, project, connection, tenancy schema+RLS) already done." \
  >/dev/null 2>&1 && echo "milestone created" || echo "milestone already exists"

# Label (idempotent)
gh label create "$LABEL" -R "$R" --color 1D76DB \
  --description "Supabase + multi-tenant + Electron migration" \
  >/dev/null 2>&1 && echo "label created" || echo "label already exists"

# Existing titles under the label (to avoid duplicates on re-run)
existing="$(gh issue list -R "$R" --label "$LABEL" --state all --limit 200 --json title -q '.[].title' 2>/dev/null || true)"

for f in $(ls docs/ai/generated-issues/[0-9]*.md | sort); do
  title="$(head -1 "$f" | sed 's/^#\{1,\} *//')"
  if grep -Fxq "$title" <<<"$existing"; then
    echo "skip (exists): $title"
    continue
  fi
  url="$(gh issue create -R "$R" --title "$title" --body-file "$f" --milestone "$MS" --label "$LABEL")"
  echo "created: $title -> $url"
done

echo "Done. View: gh issue list -R $R --label $LABEL --milestone \"$MS\""
