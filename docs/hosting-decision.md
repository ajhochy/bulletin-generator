# Hosting Decision — Bulletin Generator

**Date:** 2026-05-08  
**Question:** Should we migrate to Cloudflare Workers + D1/Hyperdrive before investing in workspaces, user accounts, Postgres, or a Flutter rewrite?

---

## Verdict: NO-GO on Cloudflare Workers

Two hard blockers make Workers a non-starter without a major rewrite:

| Blocker | Detail |
|---------|--------|
| **Subprocess calls not supported** | PDF generation spawns headless Chrome via `subprocess.run()` (server.py L1742). Workers run in a WebAssembly sandbox — no OS processes, ever. |
| **No persistent filesystem** | All state lives in JSON files on disk (`projects.json` is 8.7 MB). Workers have no writable filesystem. Atomic `tmpfile → rename` writes are impossible. |

Secondary issues (would need solving even if the above were fixed):

- PDF generation takes 5–45 seconds; Workers default timeout is 30s (paid tier allows 5 min, but Chrome still can't run)
- D1 has 350ms write replication lag — worse than current atomic file writes for conflict detection
- Python Workers (Pyodide/WASM) are beta and strip out subprocess, threading, and most OS-level stdlib

---

## Current Architecture Summary

- **Runtime:** Python stdlib `http.server`, no framework, ~1,500 lines in `server.py`
- **Storage:** JSON files in `data/` — projects, settings, announcements, songs. Lock-protected atomic writes. `projects.json` = 8.7 MB.
- **PDF:** Headless Chrome subprocess, 5–45s per call, 45s timeout
- **Auth:** OAuth tokens stored in `settings.json` (PCO + Google Calendar). Stateless HTTP.
- **Deployment:** Docker + Watchtower auto-update from GHCR. Bind-mount `./data:/app/data`.
- **Conflict detection:** Server-side revision numbers, 409 responses, client tracks `_loadedRevision`

---

## Recommended Path: Stay on Docker Containers

The app is already containerized and working. The lowest-risk hosting upgrade is a container platform that matches the current model:

| Platform | Fit | Notes |
|----------|-----|-------|
| **Fly.io** | ★★★★★ | Persistent volumes, Docker-native, auto-deploy from GHCR, $0–$5/mo for low traffic |
| **Render** | ★★★★☆ | Persistent disk, Docker support, simple deploys, $7/mo for 512 MB RAM |
| **Railway** | ★★★★☆ | Docker + volume mounts, good DX, pay-per-use pricing |
| **Self-hosted (current)** | ★★★★☆ | Synology NAS already running — zero new cost, already proven |

**Recommendation:** If the goal is stability for a small team (10–50 users), the current Synology Docker setup or Fly.io is the right call. No migration needed to unlock workspaces, user accounts, or other features.

---

## Next Architectural Steps (in order)

Before touching Flutter, Postgres, or user accounts, resolve these in sequence:

1. **Lock in the hosting platform** — Decide: Synology (stay) or Fly.io (move). This determines whether you get persistent volumes for free or need to budget for them.

2. **Replace JSON files with SQLite (D1-compatible schema)** — Not for Cloudflare, but for correctness. `projects.json` at 8.7 MB with a threading.Lock is fragile at scale. SQLite gives row-level locking, proper conflict detection, and a path to Postgres later without a rewrite.

3. **Extract PDF generation as a sidecar** — Run a small Puppeteer/Chrome service separately (Docker sidecar or a $0-tier Lambda). This decouples the slow, stateful Chrome dependency from the main API and unblocks any future serverless migration.

4. **Then: workspaces + user accounts** — Once storage is SQL and PDF is decoupled, adding multi-tenancy is a schema change + auth middleware, not a rewrite.

5. **Flutter / mobile — last** — Only makes sense after the backend API is stable and the hosting story is settled.

---

## Summary

Cloudflare Workers is the wrong tool for this app today. The architecture depends on native subprocesses and local file I/O — both incompatible with the Workers sandbox. The existing Docker deployment is solid. Invest in SQLite storage and a PDF sidecar first; those unblock every downstream feature without requiring a platform migration.
