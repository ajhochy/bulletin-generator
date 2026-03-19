# GitHub Issue Draft: Package the app as a simple installer with user-friendly account sign-in

## Title

Package Bulletin Generator as a desktop installer and replace manual API setup with guided account sign-in

## Summary

The app currently runs as a local Python web server and expects each machine to be configured manually with local environment values such as `PCO_APP_ID`, `PCO_SECRET`, and calendar iCal feed URLs.

That is workable for local development, but it is not a good testing or onboarding experience for non-technical users. We need a simple installer that can be sent to testers, plus a setup flow where users can connect their own Planning Center and Google Calendar accounts without having to figure out API keys, secrets, or raw feed URLs.

## Problem

- The current install flow assumes Python or Docker setup and manual `.env` editing.
- Planning Center access is currently server-side Basic auth using local credentials.
- Calendar sync is currently based on pasted iCal feed URLs rather than a real account connection.
- Test users cannot realistically self-serve setup on their own machines.

## Goal

- Ship the app as an installable desktop app for macOS first, with room for Windows later.
- Let a user launch the app, click "Connect Planning Center" and "Connect Google Calendar", sign in, and start syncing.
- Keep local data local to that machine unless we explicitly add cloud sync later.
- Minimize support burden and avoid requiring end users to create their own developer credentials.

## Proposed Direction

### Packaging

Wrap the existing local web app as a desktop application instead of asking testers to run Python manually.

Practical first option:

- Keep `server.py` as the local backend.
- Bundle Python, the HTML app, and static files into a desktop installer.
- Start the local server automatically on launch.
- Open the UI in an embedded webview or the user's default browser.

Most realistic implementation paths:

- `PyInstaller` for the fastest path to a macOS app bundle using the current Python codebase.
- `Briefcase` if we want a more native app structure, but it is a larger packaging shift.
- Avoid Electron/Tauri unless we decide the app needs a larger desktop shell, auto-update system, or deeper native integrations.

### Account connection model

Replace "bring your own secret" setup with app-owned OAuth where possible, and store per-user tokens locally.

- Planning Center:
  Use a single app registration owned by this project, then sign users in with OAuth 2 instead of asking each tester for a personal token or API secret.
- Google Calendar:
  Move from pasted iCal feed URLs to Google OAuth and read calendars through the Calendar API.

## Why this is viable

Planning Center's published developer docs distinguish between:

- single-user auth with personal access tokens and Basic auth
- multi-user auth with OAuth 2 for apps that log in on behalf of other users

Source: [Planning Center developer support](https://github.com/planningcenter/developers)

Google's Calendar docs support local installed-app OAuth flows and explicitly document desktop app client credentials and local token storage patterns.

Sources:

- [Google Calendar Python quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python)
- [Google OAuth consent and scopes guide](https://developers.google.com/workspace/guides/configure-oauth-consent)

## Recommended scope for this issue

This issue should cover the architecture and first implementation pass, not a perfect cross-platform release.

Suggested scope:

- macOS installer first
- local token storage
- Planning Center OAuth connection
- Google Calendar OAuth connection
- updated onboarding/settings UI

Out of scope for the first pass:

- cloud-hosted sync
- multi-device account sync
- auto-update infrastructure
- Windows code signing and notarization polish
- admin dashboards or organization-wide deployment tooling

## Implementation Outline

### 1. Introduce an installable desktop wrapper

- Add a packaging target that bundles `server.py`, `worship-booklet.html`, `data/*.example.json`, and runtime dependencies.
- On app launch:
  - create an app-data directory for machine-local files
  - initialize `projects.json`, `announcements.json`, and `settings.json` there
  - start the local server on an available localhost port
  - open the UI automatically
- Move data paths away from repo-relative assumptions so installed builds do not write into the app bundle.

Likely code changes:

- Refactor file path handling in [server.py](/Users/ajhochhalter/Documents/Bulletin Generator - 1.04/server.py)
- Add a launcher entrypoint for packaged mode
- Add a build script for app packaging

### 2. Replace env-based Planning Center auth with OAuth

- Add routes like:
  - `GET /auth/pco/start`
  - `GET /auth/pco/callback`
  - `POST /auth/pco/logout`
  - `GET /api/integrations/pco/status`
- Store per-user access and refresh tokens locally on the machine.
- Update `/pco-proxy/*` to use the signed-in user's bearer token instead of a single shared Basic auth credential.
- Update the Settings UI to show:
  - connected account
  - reconnect
  - disconnect
  - sync status / last successful sync

Notes:

- This is the cleanest way to let testers log in with their own Planning Center accounts.
- It avoids asking users to generate personal access tokens manually.

### 3. Replace iCal URL sync with Google Calendar OAuth

- Add routes like:
  - `GET /auth/google/start`
  - `GET /auth/google/callback`
  - `POST /auth/google/logout`
  - `GET /api/integrations/google-calendars`
  - `POST /api/integrations/google-calendars/selection`
- After sign-in:
  - fetch the user's available calendars
  - let them select one or more calendars in Settings
  - store selected calendar IDs locally
  - fetch upcoming events through the Calendar API instead of downloading `.ics` URLs
- Keep the existing event filtering model for excluded titles, but apply it to API results instead of iCal text parsing.

Notes:

- This is a better UX than asking users to find and paste secret-ish private feed URLs.
- Use minimum scopes where possible, ideally read-only calendar access.

### 4. Add a migration-safe settings model

- Extend local settings to support:
  - integration connection states
  - selected Google calendars
  - token metadata
  - last sync timestamps
- Keep old env and iCal settings temporarily as a fallback during migration.
- If no OAuth connection exists, show the current manual configuration path only as an advanced fallback.

### 5. Improve onboarding in the UI

Add a simple first-run checklist on the Settings page:

- Step 1: Connect Planning Center
- Step 2: Connect Google Calendar
- Step 3: Choose calendars to include
- Step 4: Import a service / sync this week

The UI should make it obvious when setup is incomplete and what the next action is.

## Suggested milestones

### Milestone 1: Packaging groundwork

- refactor data storage paths
- define packaged app runtime behavior
- produce a local macOS app build for testing

### Milestone 2: Planning Center sign-in

- OAuth routes
- local token persistence
- PCO proxy changes
- UI connection state

### Milestone 3: Google Calendar sign-in

- OAuth routes
- calendar picker UI
- event fetch via Google API
- migrate away from iCal-only sync

### Milestone 4: Installer polish

- app icon
- first-run experience
- basic error handling
- signed test build / notarization if needed

## Acceptance Criteria

- A tester can install the app without manually installing Python.
- A tester can launch the app from a normal application icon or installer flow.
- A tester can connect their own Planning Center account from the app UI.
- A tester can connect their own Google account from the app UI.
- A tester can select calendars without manually pasting iCal URLs.
- Existing local project data remains machine-local and does not require cloud infrastructure.

## Risks / Open Questions

- Planning Center app registration and OAuth callback handling need to be verified against the exact API app setup we want to use.
- Google OAuth for external users may require test-user configuration or app verification depending on scopes and audience.
- Packaged apps need a clean strategy for local token encryption or at least OS-keychain-backed secret storage.
- If the app continues opening a browser against `localhost`, we should decide whether that is acceptable or whether we want an embedded webview.

## Recommended follow-up tasks

- Create a small spike branch for packaged macOS builds.
- Confirm Planning Center OAuth callback flow and token refresh behavior.
- Confirm Google Calendar read-only scopes and test-user limits for external testers.
- Decide whether secrets live in:
  - macOS Keychain plus a local settings file
  - or an encrypted local token store managed by the app

