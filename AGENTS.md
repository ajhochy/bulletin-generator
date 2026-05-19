# AGENTS.md

Operating contract for AI agents working in this repo. Pair with `CLAUDE.md` (the full architectural reference) and `docs/ai/*` (planning + state memory).

## First files to read

1. `CLAUDE.md` — what the app is, key files, data flow, deployment modes, common gotchas.
2. `docs/ai/project-state.md` — current focus, recent work, open risks.
3. `docs/ai/architecture.md` — boundaries between server, frontend modules, and the two deployment modes.
4. `docs/ai/repo-map.md` — directory layout and where to grep first.
5. `docs/ai/testing-guide.md` — how to run the app, what to verify, what is manual-only.
6. The most recent commits on `main` (`git log --oneline -20`).

## Data-safety rules

- Treat `data/projects.json`, `data/announcements.json`, `data/settings.json`, and `data/song_database.json` as user data. Never delete, never commit, never overwrite. They live in `./data/` (Docker bind mount) or `~/Library/Application Support/BulletinGenerator/` (desktop).
- Only the `*.example.json` siblings under `data/` are checked in. `_initialize_local_file()` in `server.py` copies them on first run; never modify that contract.
- Atomic writes only: all JSON writes go through `_write_json()` in `server.py`. Never write a JSON file directly.
- Migrations are tracked in `data/migrations.json` via `run_migrations()`. Keep them idempotent and additive.

## Testing rules

- This repo has no automated test suite. Validation is:
  1. `python3 -c 'import server'` and `node --check src/js/<file>.js` for syntax sanity.
  2. Manual smoke via `python3 server.py` (or the launch.json preview server on port 8766) — load the app, exercise the changed surface.
  3. Browser DevTools console must be free of new errors after the change.
- Changes that touch the Template Designer, preview render, or PDF generation require a manual click-through. Build/launch verification alone is insufficient.

## Git + manual-merge rules

- Always work on a feature branch — never on `main`.
- One focused branch per concern. Don't mix bug fixes with refactors or doc bootstrapping.
- Commit messages use Conventional Commits (`fix(scope): …`, `feat(scope): …`, `chore: …`).
- Open draft PRs; **merge is always manual**. Do not auto-merge.
- Never use `--no-verify` or `git push --force` to `main`.

## Memory-update rules

- After any non-trivial change, update `docs/ai/project-state.md`.
- After an architectural decision (deployment mode shift, new dependency, new data file, schema change), append to `docs/ai/decisions.md`.
- Keep memory factual and concise. If you don't know a fact, mark it `Unknown` rather than inventing.
