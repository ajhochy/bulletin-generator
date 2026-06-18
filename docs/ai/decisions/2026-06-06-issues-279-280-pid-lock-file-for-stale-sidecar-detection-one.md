---
date: 2026-06-06
repo: bulletin-generator
tags: [decision, bulletin-generator]
---

# Issues #279 + #280: PID lock file for stale-sidecar detection; onedir for cold-start

**Context.** Issue #279: if the Electron app crashes (bypassing `before-quit`), the Python sidecar stays alive holding port 8765. On next launch, the new sidecar bind fails with a raw OSError traceback → Electron shows "Exit code 1". Issue #280: PyInstaller `--onefile` unpacks the whole runtime to a temp dir on every launch; `--onedir` copies once and stays.

**Decision — #279 server.py:** Catch `OSError` at the `ThreadingHTTPServer(...)` constructor, check `errno.EADDRINUSE` (98 on POSIX) or `WSAEADDRINUSE` (10048 on Windows, obtained via `getattr` so it's safe on non-Windows), print a distinct `[server] FATAL: port <PORT> already in use — another instance or a stale sidecar is running.` to stderr, and exit with code 3. Exit code 3 was chosen as a recognizable sentinel distinct from Python's standard 1 (unhandled exception) and 2 (CLI misuse). All other `OSError` variants re-raise unchanged.

**Decision — #279 electron/main.js:** PID lock file at `os.tmpdir()/bulletin-generator-sidecar.pid`. Written immediately after `spawn()` returns the child PID; removed on `killSidecar()` (clean quit) and on the sidecar's `exit` event. At `app.whenReady`, `reapStaleSidecar()` reads the file, calls `process.kill(pid, 0)` to confirm the process is still alive, sends `SIGTERM` if so, and waits 1500ms for the OS to release the port. **Why PID lock over HTTP probe:** an HTTP probe to 127.0.0.1:8765 cannot distinguish our orphaned sidecar from any other service the user is running on that port (e.g. another app or a previous dev server). The PID lock positively identifies the process we spawned. **Why `os.tmpdir()`:** survives app crashes (not cleaned on crash), writable on both macOS and Windows without special permissions, and distinct from the app bundle location which varies between dev and packaged modes. **PID-reuse risk noted but accepted:** the OS recycles PIDs slowly; a collision between a killed-sidecar PID and an unrelated new process only occurs during crash recovery, not normal launch.

**Decision — #280 PyInstaller onedir:** `--onedir` places all shared libraries alongside the executable in `dist/server/` instead of packing them into a single fat binary that must be re-extracted to a tmp dir on every launch. The `resolveSidecar()` packaged path changes from `<resourcesPath>/server` to `<resourcesPath>/server/server`. The `extraResources` config in `package.json` changes from a single-file filter to copying the entire `dist/server/` directory tree into `<app>/Contents/Resources/server/`. Cold-start speedup (no per-launch unpack) and the executable path change are only verifiable in a packaged build.

**Consequences.**
- `server.py`: cleaner error for the most common desktop crash-recovery scenario.
- `electron/main.js`: ~80 lines of new helpers; app startup adds `reapStaleSidecar()` (≈0ms normally, 1.5s only on crash recovery).
- `release-electron.yml`: both macOS and Windows build steps are `--onedir` now; `ls dist/server/` replaces `ls -lh dist/server` as the post-build check.
- `package.json` extraResources: the glob change means no single-file `server`/`server.exe` at the resource root any more — only the `server/` subdirectory. Old packaged builds will not find `<resourcesPath>/server` (file) but `resolveSidecar()` correctly falls back to dev-mode for that case.
