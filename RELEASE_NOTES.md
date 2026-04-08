# Release Notes

## v1.10.1 — Collaboration, Calendar, and Projects Fixes

- fixed false stale/conflict save warnings caused by overlapping project saves
- moved ProPresenter and Google Drive exports into Projects bulk actions
- fixed Google Calendar selection persistence and refresh behavior
- fixed calendar and serving preview page-break controls
- fixed text-section paragraph/superscript rendering edge cases
- fixed Planning Center service-time imports for volunteers assigned to multiple services

## v1.09 — Phase 1 Bug Fixes

- fixed staff page rendering issues
- fixed conflict banner display in server mode
- fixed calendar token handling

## v1.08 — Volunteer Page Breaks, PDF & Calendar Improvements

- added page break support for volunteer/schedule sections
- fixed PDF font rendering in headless Chrome
- extended calendar event window to 8 days to prevent edge-case Sunday omissions
- UI improvements to calendar section

## v1.07 — OAuth Error Surfacing & SSL Fix

- surfaced OAuth token exchange error details in the UI for both Planning Center and Google
- bundled `certifi` CA certificates in packaged app to fix SSL verification failures

## v1.06 — Desktop App & Menu Bar

- added persistent macOS menu bar icon via `launcher.py`
- implemented single-instance detection and clean server lifecycle management
- server now auto-restarts when a version mismatch is detected between the running build and current app
- added pre-built `.icns` icon and SVG source for the macOS app bundle
- added code signing and notarization to the CI release pipeline
- dynamic `APP_VERSION` injected from CI release tag

## v1.05 — In-App Updates, Editor Identity & PCO OAuth Improvements

- added in-app update system: progress bar, version-aware polling, Watchtower integration for Docker
- added migration framework for safe schema changes across data files
- editor identity now stored per-client in server mode (fixes shared-editor attribution)
- PCO OAuth connect button now uses the OAuth flow in all deployment modes
- fixed PCO login to always prompt for account selection
- added customizable Welcome section to the booklet editor

## v1.04 — Song Database & Collaboration

- ProPresenter song database import (merges duplicate slides into one section)
- sticky search/sort controls in the song database UI (only the list scrolls)
- server-mode collaboration: revision-aware saves, editor attribution, stale document detection
- Google Calendar OAuth sign-in for desktop mode
- Google Calendar OAuth support in server/Docker mode

## v1.03 — PCO Fixes & Page Sizes

- fixed Planning Center service times not populating correctly
- fixed ProPresenter 7 import compatibility
- added configurable page size presets

## v1.02 — Desktop Packaging & PCO OAuth

- added desktop packaging via PyInstaller
- added Planning Center OAuth sign-in flow
- added `APP_MODE` config for desktop vs server deployment

## v1.01 — Core Features

- ProPresenter song database import
- PCO plan notes import mapped to bulletin items
- global document size template with configurable page sizes
- volunteer/serving schedule import from Planning Center

## Safe Public Repo Baseline

This release prepared the project for safe public GitHub distribution.

- moved Planning Center credential handling to server-side environment variables
- removed browser-stored PCO secrets
- added `.gitignore` and `.dockerignore` rules for secrets, local data, exports, and machine artifacts
- replaced committed live data with sanitized `*.example.json` files
- added `.env.example` and documented local setup
- updated startup flow so local working data is created from example files
- documented which files are public and which must remain local

### Notes

- local `data/*.json`, `.env`, debug exports, and song database exports remain intentionally untracked
- existing local private data was not pushed to GitHub
