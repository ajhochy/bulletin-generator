# 014: Electron packaging, auto-update, and macOS/Windows signing

**Milestone:** M4  ·  **Plan ref:** issue 18
**Depends on:** 011, 012, 013

## Context

Decision D4: `electron-updater` (via `electron-builder`) replaces Watchtower/zip-download for the desktop distribution. The existing `bulletin-generator.spec` (PyInstaller) + GitHub release workflow builds a macOS `.app`; this issue adds an Electron wrapper around it, produces notarized macOS `.dmg` + Windows `.exe` installers, publishes them to GitHub Releases, and wires `electron-updater` for in-app auto-update. `launcher.py` is retired from this distribution (the Electron main process takes over its sidecar-spawn role from issue 011).

## Acceptance criteria

- [ ] `electron-builder` config (in `package.json` or `electron-builder.yml`) produces: macOS `.dmg` (signed + notarized), Windows NSIS `.exe` installer.
- [ ] The PyInstaller `server` binary is included as an `extraResource` in the packaged app (path: `resources/server/server` on macOS; `resources/server/server.exe` on Windows).
- [ ] `electron-updater` (`autoUpdater`) is wired in `electron/main.js`: checks GitHub Releases for a newer version on startup; prompts the user with a dialog when an update is available; downloads and installs on user confirmation. `update_server` field in `package.json` points to the GitHub Releases feed for this repo.
- [ ] CI workflow (`.github/workflows/release.yml` or a new `electron-release.yml`): triggers on `v*` tag push; runs PyInstaller to build the server binary; runs `electron-builder` to package; uploads the `.dmg` and `.exe` to the GitHub Release.
- [ ] macOS notarization: `electron-builder` notarize config uses `APPLE_ID`, `APPLE_ID_PASSWORD`, `APPLE_TEAM_ID` GitHub secrets (must be added; document in `MANUAL-STEPS.md`).
- [ ] `launcher.py` is NOT deleted in this issue (it remains for the Docker/server distribution); a comment is added noting it is superseded by the Electron main process for the desktop distribution.
- [ ] `MANUAL-STEPS.md` documents the new release process for the Electron build.
- [ ] Manual smoke: download the packaged `.dmg`, install, open — app launches, loads the UI, connects to Supabase, PDF works. Auto-update: bump the version, publish a new release, confirm the running app detects and installs the update.

## Likely files

- `package.json` (modify — electron-builder config, electron-updater dependency, version)
- `electron-builder.yml` (new or merged into package.json)
- `electron/main.js` (modify — `autoUpdater` wiring)
- `.github/workflows/release.yml` or `.github/workflows/electron-release.yml` (modify/new)
- `MANUAL-STEPS.md` (modify — release process, Apple signing secrets)
- `bulletin-generator.spec` (modify — output path for Electron resource packaging)

## Tests / validation

```bash
# Local packaging test (macOS):
npm run dist
# → produces dist/*.dmg; open and verify app launches.

# CI:
# Tag a pre-release version (e.g. v2.0.0-alpha.1) → confirm CI builds artifacts.
```

Manual smoke:
1. Install `.dmg` on macOS — app opens, loads bulletin UI, connects to Supabase.
2. All M4 features work: login (issue 013), PDF (issue 012), tabs/editing (existing UI).
3. Publish a newer version to GitHub Releases — running app shows update dialog, installs update, reopens at new version.
4. Windows `.exe`: install, open, confirm basic functionality (login, PDF, tabs).

## Data-safety / out of scope

- Apple signing credentials (`APPLE_ID_PASSWORD`) and `APPLE_TEAM_ID` must be stored as GitHub Secrets only; never committed.
- The Supabase anon key (safe to ship) is the only Supabase credential that should appear in the packaged Electron app.
- `service_role` key must never be included in the Electron bundle.
- Out of scope: Linux packaging — macOS + Windows are the v1 targets.
- Out of scope: Microsoft code signing — unsigned Windows builds are acceptable for v1 (users may see SmartScreen warnings); add signing as a follow-up.
