# Safe Public Repo Baseline

This release prepares the project for safe public GitHub distribution.

## Changes

- moved Planning Center credential handling to server-side environment variables
- removed browser-stored PCO secrets
- added `.gitignore` and `.dockerignore` rules for secrets, local data, exports, and machine artifacts
- replaced committed live data with sanitized `*.example.json` files
- added `.env.example` and documented local setup
- updated startup flow so local working data is created from example files
- documented which files are public and which must remain local

## Notes

- local `data/*.json`, `.env`, debug exports, and song database exports remain intentionally untracked
- existing local private data was not pushed to GitHub
